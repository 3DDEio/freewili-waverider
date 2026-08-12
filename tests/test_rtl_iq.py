from __future__ import annotations

import math
import queue
import threading
import unittest
from types import SimpleNamespace

from freewili_foxhunt.rtl_iq import (
    FFT_SIZE,
    RtlIqStream,
    analyze_iq,
    carrier_margin_db,
)


class RtlIqTests(unittest.TestCase):
    def test_disabling_cw_resets_decoder_and_discards_pending_messages(self) -> None:
        stream = object.__new__(RtlIqStream)
        stream.cw_enabled = True
        stream.messages = __import__("queue").Queue(maxsize=4)
        stream.messages.put_nowait(SimpleNamespace(text="PENDING"))
        resets = []
        stream.morse_decoder = SimpleNamespace(reset=lambda: resets.append(True))

        stream.set_cw_enabled(False)

        self.assertFalse(stream.cw_enabled)
        self.assertEqual(resets, [True])
        self.assertTrue(stream.messages.empty())

        stream.set_cw_enabled(False)
        self.assertEqual(resets, [True])

    def test_sample_rates_cover_supported_spans(self) -> None:
        self.assertEqual(RtlIqStream.sample_rate_for(200_000), 240_000)
        self.assertEqual(RtlIqStream.sample_rate_for(500_000), 1_024_000)
        self.assertEqual(RtlIqStream.sample_rate_for(2_000_000), 2_400_000)

    def test_realtime_ratio_compares_processed_iq_to_wall_time(self) -> None:
        stream = object.__new__(RtlIqStream)
        stream.capture_started_monotonic = __import__("time").monotonic() - 2.0
        stream.processed_iq_seconds = 1.0

        self.assertAlmostEqual(stream.realtime_ratio, 0.5, delta=0.02)

    def test_processor_accounts_for_each_queued_iq_block(self) -> None:
        stream = object.__new__(RtlIqStream)
        stream.entry = SimpleNamespace(frequency_hz=147_500_000, span_hz=200_000)
        stream.tuner_center_hz = 147_550_000
        stream.sample_rate_hz = 240_000
        stream.stop_event = threading.Event()
        stream.stop_event.set()
        stream.iq_blocks = queue.Queue(maxsize=4)
        stream.iq_blocks.put_nowait(bytes([128, 128]) * (FFT_SIZE * 8))
        stream.rows = queue.Queue(maxsize=2)
        stream.messages = queue.Queue(maxsize=4)
        stream.cw_enabled = False
        stream.processed_iq_seconds = 0.0
        stream.last_processing_ms = 0.0
        stream.carrier_active = False
        stream.carrier_margin_db = 0.0
        stream._carrier_release_blocks = 0

        stream._process_loop()

        self.assertAlmostEqual(
            stream.processed_iq_seconds,
            (FFT_SIZE * 8) / 240_000,
        )
        self.assertFalse(stream.rows.empty())

    def test_analyze_iq_finds_tone_inside_requested_span(self) -> None:
        sample_rate = 240_000
        tuner_center = 145_315_000
        target_center = 145_265_000
        tone_hz = 145_275_000
        offset = tone_hz - tuner_center
        samples = bytearray()
        for index in range(FFT_SIZE * 8):
            phase = 2.0 * math.pi * offset * index / sample_rate
            samples.extend((round(127.5 + 90.0 * math.cos(phase)), round(127.5 + 90.0 * math.sin(phase))))
        row = analyze_iq(bytes(samples), tuner_center, target_center, sample_rate, 200_000)
        self.assertAlmostEqual(row.peak_frequency_hz, tone_hz, delta=row.bin_hz)
        self.assertGreater(row.peak_dbfs, -10.0)

    def test_analyze_iq_suppresses_tuner_dc_spike_without_hiding_center_signal(self) -> None:
        sample_rate = 240_000
        target_center = 147_495_000
        tuner_center = target_center + 25_000
        samples = bytearray()
        for index in range(FFT_SIZE * 8):
            phase = -2.0 * math.pi * 25_000 * index / sample_rate
            # Constant I/Q bias creates a strong synthetic tuner-center DC
            # artifact; the smaller rotating component is the real fox at the
            # requested center frequency.
            i_value = round(127.5 + 55.0 + 28.0 * math.cos(phase))
            q_value = round(127.5 + 40.0 + 28.0 * math.sin(phase))
            samples.extend((max(0, min(255, i_value)), max(0, min(255, q_value))))

        row = analyze_iq(
            bytes(samples), tuner_center, target_center, sample_rate, 100_000
        )

        self.assertAlmostEqual(row.peak_frequency_hz, target_center, delta=row.bin_hz)
        self.assertGreater(abs(row.peak_frequency_hz - tuner_center), 10_000)

    def test_carrier_margin_uses_target_channel_over_band_median(self) -> None:
        row = SimpleNamespace(
            low_hz=147_450_000,
            bin_hz=10_000,
            powers_dbfs=[-70.0, -69.0, -70.0, -68.0, -66.0, -40.0, -67.0],
        )

        self.assertGreater(carrier_margin_db(row, 147_500_000), 20.0)
        self.assertLess(carrier_margin_db(row, 147_460_000), 5.0)


if __name__ == "__main__":
    unittest.main()
