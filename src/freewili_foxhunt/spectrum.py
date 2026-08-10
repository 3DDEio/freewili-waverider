"""RTL power-row parsing and display-bin reduction."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass


@dataclass(slots=True)
class SpectrumRow:
    low_hz: float
    high_hz: float
    bin_hz: float
    samples: int
    powers_dbfs: list[float]

    @property
    def peak_dbfs(self) -> float:
        return max(self.powers_dbfs)

    @property
    def peak_frequency_hz(self) -> float:
        index = max(range(len(self.powers_dbfs)), key=self.powers_dbfs.__getitem__)
        return self.low_hz + index * self.bin_hz


def parse_rtl_power_csv(line: str) -> SpectrumRow:
    fields = next(csv.reader([line], skipinitialspace=True))
    if len(fields) < 7:
        raise ValueError("rtl_power row has fewer than seven fields")
    powers = [float(value) for value in fields[6:] if value.strip()]
    if not powers:
        raise ValueError("rtl_power row contains no FFT bins")
    return SpectrumRow(
        low_hz=float(fields[2]),
        high_hz=float(fields[3]),
        bin_hz=float(fields[4]),
        samples=int(fields[5]),
        powers_dbfs=powers,
    )


def reduce_bins(values: list[float], width: int) -> list[float]:
    if width <= 0:
        raise ValueError("width must be positive")
    if not values:
        return [0.0] * width
    if len(values) == width:
        return values.copy()
    if len(values) > width:
        result: list[float] = []
        for index in range(width):
            start = index * len(values) // width
            stop = max(start + 1, (index + 1) * len(values) // width)
            result.append(max(values[start:stop]))
        return result
    if len(values) == 1:
        return [values[0]] * width

    result = []
    for index in range(width):
        position = index * (len(values) - 1) / max(1, width - 1)
        lower = int(math.floor(position))
        upper = min(len(values) - 1, lower + 1)
        fraction = position - lower
        result.append(values[lower] * (1.0 - fraction) + values[upper] * fraction)
    return result


def smooth_spectrum_bins(values: list[float]) -> list[float]:
    """Apply a small frequency-domain anti-blocking filter in linear power.

    Peak-preserving reduction is useful for finding a narrow carrier, but a
    twelve-bin display can make one noisy FFT bucket look like an unrelated
    rectangular slab. This three-tap kernel keeps the measured peak at its
    real frequency while producing the expected hot-core/cool-shoulder shape.
    It deliberately does not mirror bins around center: doing that would hide
    an off-frequency transmitter or real adjacent-channel interference.
    """

    if len(values) < 2:
        return values.copy()
    powers = [10.0 ** (value / 10.0) for value in values]
    result: list[float] = []
    for index, here in enumerate(powers):
        left = powers[index - 1] if index > 0 else here
        right = powers[index + 1] if index + 1 < len(powers) else here
        smoothed = left * 0.2 + here * 0.6 + right * 0.2
        result.append(10.0 * math.log10(max(smoothed, 1e-15)))
    return result


def quantize_bins(values: list[float], floor_dbfs: float, ceiling_dbfs: float) -> list[int]:
    if floor_dbfs >= ceiling_dbfs:
        raise ValueError("floor_dbfs must be below ceiling_dbfs")
    scale = 255.0 / (ceiling_dbfs - floor_dbfs)
    return [max(0, min(255, round((value - floor_dbfs) * scale))) for value in values]


def encode_waterfall_bins(
    values: list[float], floor_dbfs: float, ceiling_dbfs: float
) -> list[int]:
    """Encode dBFS values for FW2's documented 0..100 waterfall scale.

    ``set_plot_data`` is shared by native plots and waterfalls. FW2's own
    sensor application rescales both controls to 0..100: zero is the cold
    dark-blue end and 100 is the hot yellow end. Values above 100 are rejected
    as ``Invalid`` by v07, which leaves a partially staged row on screen and
    makes the waterfall look like a static yellow block.
    """

    return [round(value * 100 / 255) for value in quantize_bins(values, floor_dbfs, ceiling_dbfs)]


def waterfall_range(
    values: list[float], configured_floor_dbfs: float, configured_ceiling_dbfs: float
) -> tuple[float, float]:
    """Return the saved color range, or a relative range when it is saturated."""
    if not values:
        return configured_floor_dbfs, configured_ceiling_dbfs
    clipped = sum(
        value <= configured_floor_dbfs or value >= configured_ceiling_dbfs for value in values
    )
    if clipped <= len(values) // 10:
        return configured_floor_dbfs, configured_ceiling_dbfs

    ordered = sorted(values)
    median = ordered[len(ordered) // 2]
    peak = ordered[-1]
    floor_dbfs = median - 3.0
    ceiling_dbfs = max(median + 6.0, peak + 1.0)
    return floor_dbfs, ceiling_dbfs


@dataclass(slots=True)
class WaterfallScale:
    """Calibrate briefly, then preserve color meaning across movement."""

    configured_floor_dbfs: float
    configured_ceiling_dbfs: float
    calibration_rows: int = 12
    recovery_rows: int = 4
    floor_dbfs: float | None = None
    ceiling_dbfs: float | None = None
    rows_seen: int = 0
    saturation_streak: int = 0

    def reset(self) -> None:
        self.floor_dbfs = None
        self.ceiling_dbfs = None
        self.rows_seen = 0
        self.saturation_streak = 0

    def _target(self, values: list[float]) -> tuple[float, float]:
        if not values:
            return self.configured_floor_dbfs, self.configured_ceiling_dbfs
        ordered = sorted(values)
        noise_median = ordered[len(ordered) // 2]
        # The waterfall is a relative hunting view: its cold end belongs just
        # below the measured band noise, not at a distant absolute -90 dBFS.
        # A robust median ignores a narrow fox peak.  Keeping a fixed 24 dB
        # window after startup makes background bins blue while a clean carrier
        # becomes a stable vertical warm/hot ridge as the hunter moves.
        floor_dbfs = max(-120.0, noise_median - 4.0)
        ceiling_dbfs = min(0.0, floor_dbfs + 24.0)
        floor_dbfs = ceiling_dbfs - 24.0
        return floor_dbfs, ceiling_dbfs

    def update(self, values: list[float]) -> tuple[float, float]:
        target_floor, target_ceiling = self._target(values)
        if self.floor_dbfs is None or self.ceiling_dbfs is None:
            self.floor_dbfs = target_floor
            self.ceiling_dbfs = target_ceiling
        elif self.rows_seen < self.calibration_rows:
            alpha = 0.25
            self.floor_dbfs += alpha * (target_floor - self.floor_dbfs)
            self.ceiling_dbfs += alpha * (target_ceiling - self.ceiling_dbfs)
        elif values:
            # RTL-SDR startup can briefly publish a near-silent full-band row
            # while the tuner PLL settles.  Freezing that transient makes every
            # later live bin hit the same hot color.  Recover only when most of
            # the whole band remains outside the active window for several
            # consecutive rows; a narrow fox peak cannot move the scale.
            clipped = sum(
                value <= self.floor_dbfs or value >= self.ceiling_dbfs
                for value in values
            )
            if clipped * 4 >= len(values) * 3:
                self.saturation_streak += 1
            else:
                self.saturation_streak = 0
            if self.saturation_streak >= self.recovery_rows:
                self.floor_dbfs = target_floor
                self.ceiling_dbfs = target_ceiling
                self.rows_seen = 0
                self.saturation_streak = 0
        self.rows_seen += 1
        return self.floor_dbfs, self.ceiling_dbfs
