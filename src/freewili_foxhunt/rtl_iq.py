"""Low-latency RTL-SDR IQ capture using the installed librtlsdr runtime."""

from __future__ import annotations

import ctypes
import ctypes.util
import math
import queue
import threading
import time

from .models import FrequencyEntry
from .morse import DecodedMessage, NfmMorseDecoder
from .rtl_power import GAIN_DB_BY_PROFILE
from .spectrum import SpectrumRow


FFT_SIZE = 256
AVERAGE_WINDOWS = 8
TARGET_PERIOD_SECONDS = 0.1
DC_NOTCH_HALF_WIDTH_BINS = 3


def _fft(values: list[complex]) -> None:
    """In-place radix-2 FFT, small enough for the dependency-free CM0 path."""
    count = len(values)
    target = 0
    for index in range(1, count):
        bit = count >> 1
        while target & bit:
            target ^= bit
            bit >>= 1
        target ^= bit
        if index < target:
            values[index], values[target] = values[target], values[index]
    length = 2
    while length <= count:
        root = complex(math.cos(-2.0 * math.pi / length), math.sin(-2.0 * math.pi / length))
        half = length // 2
        for offset in range(0, count, length):
            twiddle = 1.0 + 0.0j
            for inner in range(half):
                even = values[offset + inner]
                odd = values[offset + inner + half] * twiddle
                values[offset + inner] = even + odd
                values[offset + inner + half] = even - odd
                twiddle *= root
        length <<= 1


def analyze_iq(
    data: bytes,
    tuner_center_hz: int,
    target_center_hz: int,
    sample_rate_hz: int,
    span_hz: int,
) -> SpectrumRow:
    sample_count = len(data) // 2
    if sample_count < FFT_SIZE:
        raise ValueError("not enough IQ samples for one FFT")
    window = [0.5 - 0.5 * math.cos(2.0 * math.pi * index / (FFT_SIZE - 1)) for index in range(FFT_SIZE)]
    window_sum = sum(window)
    windows = min(AVERAGE_WINDOWS, sample_count // FFT_SIZE)
    accumulated = [0.0] * FFT_SIZE
    usable = sample_count - FFT_SIZE
    for frame in range(windows):
        start = 0 if windows == 1 else frame * usable // (windows - 1)
        values = [
            complex((data[2 * (start + index)] - 127.5) / 127.5,
                    (data[2 * (start + index) + 1] - 127.5) / 127.5)
            * window[index]
            for index in range(FFT_SIZE)
        ]
        _fft(values)
        for index, value in enumerate(values):
            accumulated[index] += value.real * value.real + value.imag * value.imag

    shifted = accumulated[FFT_SIZE // 2 :] + accumulated[: FFT_SIZE // 2]
    normalization = windows * window_sum * window_sum
    powers = [10.0 * math.log10(max(value / normalization, 1e-12)) for value in shifted]
    bin_hz = sample_rate_hz / FFT_SIZE
    capture_low_hz = tuner_center_hz - sample_rate_hz / 2.0
    # RTL2832-class receivers commonly produce a large, stationary DC spike at
    # the tuner center. WaveRider intentionally offsets that center from the
    # selected fox frequency, then replaces the narrow artifact with the local
    # noise estimate before peak detection and display. Otherwise the fake
    # ridge dominates RSSI and appears at exactly +offset in every waterfall.
    dc_index = round((tuner_center_hz - capture_low_hz) / bin_hz)
    notch_start = max(0, dc_index - DC_NOTCH_HALF_WIDTH_BINS)
    notch_stop = min(FFT_SIZE - 1, dc_index + DC_NOTCH_HALF_WIDTH_BINS)
    reference = (
        powers[max(0, notch_start - 4) : notch_start]
        + powers[notch_stop + 1 : min(FFT_SIZE, notch_stop + 5)]
    )
    if reference:
        ordered_reference = sorted(reference)
        replacement = ordered_reference[len(ordered_reference) // 2]
        for index in range(notch_start, notch_stop + 1):
            powers[index] = replacement
    wanted_low = target_center_hz - span_hz / 2.0
    wanted_high = target_center_hz + span_hz / 2.0
    selected = [
        index
        for index in range(FFT_SIZE)
        if wanted_low <= capture_low_hz + index * bin_hz <= wanted_high
    ]
    if not selected:
        raise ValueError("configured span does not overlap the IQ capture")
    first = selected[0]
    last = selected[-1]
    return SpectrumRow(
        low_hz=capture_low_hz + first * bin_hz,
        high_hz=capture_low_hz + last * bin_hz,
        bin_hz=bin_hz,
        samples=windows * FFT_SIZE,
        powers_dbfs=powers[first : last + 1],
    )


class RtlIqStream:
    """Continuously publishes latest-only FFT rows at a 10 Hz target."""

    def __init__(self, library: ctypes.CDLL | None = None) -> None:
        if library is None:
            name = ctypes.util.find_library("rtlsdr") or "librtlsdr.so.0"
            library = ctypes.CDLL(name)
        self.library = library
        self._configure_api()
        self.rows: queue.Queue[SpectrumRow | Exception] = queue.Queue(maxsize=2)
        self.messages: queue.Queue[DecodedMessage] = queue.Queue(maxsize=4)
        self.morse_decoder = NfmMorseDecoder()
        self.reader: threading.Thread | None = None
        self.device = ctypes.c_void_p()
        self.stop_event = threading.Event()
        self.entry: FrequencyEntry | None = None
        self.sample_rate_hz = 0
        self.tuner_center_hz = 0
        self.read_bytes = 0

    def _configure_api(self) -> None:
        api = self.library
        api.rtlsdr_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32]
        api.rtlsdr_open.restype = ctypes.c_int
        api.rtlsdr_close.argtypes = [ctypes.c_void_p]
        api.rtlsdr_close.restype = ctypes.c_int
        api.rtlsdr_set_center_freq.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        api.rtlsdr_set_center_freq.restype = ctypes.c_int
        api.rtlsdr_set_sample_rate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        api.rtlsdr_set_sample_rate.restype = ctypes.c_int
        api.rtlsdr_set_tuner_gain_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        api.rtlsdr_set_tuner_gain_mode.restype = ctypes.c_int
        api.rtlsdr_set_tuner_gain.argtypes = [ctypes.c_void_p, ctypes.c_int]
        api.rtlsdr_set_tuner_gain.restype = ctypes.c_int
        api.rtlsdr_reset_buffer.argtypes = [ctypes.c_void_p]
        api.rtlsdr_reset_buffer.restype = ctypes.c_int
        api.rtlsdr_read_sync.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        api.rtlsdr_read_sync.restype = ctypes.c_int

    @staticmethod
    def sample_rate_for(span_hz: int) -> int:
        if span_hz <= 200_000:
            return 240_000
        if span_hz <= 1_000_000:
            return 1_024_000
        return 2_400_000

    @staticmethod
    def _check(code: int, operation: str) -> None:
        if code < 0:
            raise RuntimeError(f"librtlsdr {operation} failed: {code}")

    def start(self, entry: FrequencyEntry) -> None:
        self.stop()
        while not self.rows.empty():
            self.rows.get_nowait()
        while not self.messages.empty():
            self.messages.get_nowait()
        self.morse_decoder.reset()
        entry.validate()
        self.entry = entry
        self.sample_rate_hz = self.sample_rate_for(entry.span_hz)
        # Consume a complete 100 ms of IQ per read. Sleeping after a smaller
        # fixed block would consume fewer samples than the dongle produces and
        # let progressively older USB-buffered data reach the display.
        period_bytes = math.ceil(self.sample_rate_hz * 2 * TARGET_PERIOD_SECONDS)
        self.read_bytes = math.ceil(period_bytes / 512) * 512
        offset = min(50_000, max(6_250, entry.span_hz // 4))
        self.tuner_center_hz = entry.frequency_hz + offset
        self.device = ctypes.c_void_p()
        self._check(self.library.rtlsdr_open(ctypes.byref(self.device), 0), "open")
        try:
            self._check(self.library.rtlsdr_set_sample_rate(self.device, self.sample_rate_hz), "set sample rate")
            self._check(self.library.rtlsdr_set_center_freq(self.device, self.tuner_center_hz), "set center frequency")
            gain = GAIN_DB_BY_PROFILE[entry.gain_profile]
            self._check(self.library.rtlsdr_set_tuner_gain_mode(self.device, 0 if gain is None else 1), "set gain mode")
            if gain is not None:
                self._check(self.library.rtlsdr_set_tuner_gain(self.device, round(gain * 10)), "set gain")
            self._check(self.library.rtlsdr_reset_buffer(self.device), "reset buffer")
        except Exception:
            self.library.rtlsdr_close(self.device)
            self.device = ctypes.c_void_p()
            raise
        self.stop_event.clear()
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()

    def _publish(self, item: SpectrumRow | Exception) -> None:
        if self.rows.full():
            self.rows.get_nowait()
        self.rows.put_nowait(item)

    def _publish_message(self, item: DecodedMessage) -> None:
        if self.messages.full():
            self.messages.get_nowait()
        self.messages.put_nowait(item)

    def _read_loop(self) -> None:
        assert self.entry is not None
        buffer = ctypes.create_string_buffer(self.read_bytes)
        read = ctypes.c_int()
        try:
            while not self.stop_event.is_set():
                started = time.monotonic()
                self._check(
                    self.library.rtlsdr_read_sync(
                        self.device, buffer, self.read_bytes, ctypes.byref(read)
                    ),
                    "read",
                )
                if read.value < FFT_SIZE * 2:
                    continue
                payload = buffer.raw[: read.value]
                self._publish(
                    analyze_iq(
                        payload,
                        self.tuner_center_hz,
                        self.entry.frequency_hz,
                        self.sample_rate_hz,
                        self.entry.span_hz,
                    )
                )
                for message in self.morse_decoder.feed_iq(
                    payload,
                    self.sample_rate_hz,
                    self.tuner_center_hz,
                    self.entry.frequency_hz,
                ):
                    self._publish_message(message)
                remaining = TARGET_PERIOD_SECONDS - (time.monotonic() - started)
                if remaining > 0:
                    self.stop_event.wait(remaining)
        except Exception as error:
            if not self.stop_event.is_set():
                self._publish(error)

    def stop(self) -> None:
        self.stop_event.set()
        if self.reader is not None:
            self.reader.join(timeout=1.0)
            self.reader = None
        if self.device.value:
            self.library.rtlsdr_close(self.device)
            self.device = ctypes.c_void_p()

    def close(self) -> None:
        self.stop()
