from __future__ import annotations

import unittest

from freewili_foxhunt.spectrum import (
    WaterfallScale,
    encode_waterfall_bins,
    parse_rtl_power_csv,
    quantize_bins,
    reduce_bins,
    smooth_spectrum_bins,
    waterfall_range,
)


class SpectrumTests(unittest.TestCase):
    def test_parse_row(self) -> None:
        row = parse_rtl_power_csv(
            "2026-08-08, 12:00:00, 145000000, 145100000, 25000, 64, -70.0, -40.0, -60.0"
        )
        self.assertEqual(row.peak_dbfs, -40.0)
        self.assertEqual(row.peak_frequency_hz, 145_025_000)

    def test_reduce_uses_peak_when_downsampling(self) -> None:
        self.assertEqual(reduce_bins([1.0, 8.0, 2.0, 3.0], 2), [8.0, 3.0])

    def test_reduce_interpolates_when_upsampling(self) -> None:
        self.assertEqual(reduce_bins([0.0, 10.0], 3), [0.0, 5.0, 10.0])

    def test_smoothing_draws_a_hot_carrier_with_cooling_shoulders(self) -> None:
        shaped = smooth_spectrum_bins([-70.0, -70.0, -30.0, -70.0, -70.0])

        self.assertGreater(shaped[2], shaped[1])
        self.assertGreater(shaped[1], shaped[0])
        self.assertAlmostEqual(shaped[1], shaped[3])
        self.assertAlmostEqual(shaped[0], shaped[4])

    def test_smoothing_preserves_a_real_off_center_peak(self) -> None:
        shaped = smooth_spectrum_bins([-70.0, -25.0, -70.0, -70.0, -70.0])

        self.assertEqual(max(range(len(shaped)), key=shaped.__getitem__), 1)

    def test_quantize_clamps(self) -> None:
        self.assertEqual(quantize_bins([-100.0, -60.0, -20.0], -90.0, -30.0), [0, 128, 255])

    def test_waterfall_encoder_matches_fw2_zero_to_one_hundred_scale(self) -> None:
        self.assertEqual(
            encode_waterfall_bins([-100.0, -60.0, -20.0], -90.0, -30.0),
            [0, 50, 100],
        )

    def test_waterfall_range_preserves_a_usable_saved_scale(self) -> None:
        self.assertEqual(waterfall_range([-80.0, -60.0, -40.0], -90.0, -30.0), (-90.0, -30.0))

    def test_waterfall_range_recovers_from_saturation(self) -> None:
        floor, ceiling = waterfall_range([-12.0, -11.0, -10.0, -9.0], -90.0, -30.0)
        self.assertEqual(floor, -13.0)
        self.assertEqual(ceiling, -4.0)

    def test_waterfall_scale_freezes_after_calibration(self) -> None:
        scale = WaterfallScale(-90.0, -30.0, calibration_rows=2)
        first = scale.update([-30.0, -28.0, -11.0])
        scale.update([-29.0, -27.0, -10.0])
        frozen = scale.update([-28.0, -26.0, -9.0])
        self.assertNotEqual(first, frozen)
        self.assertEqual(scale.update([-50.0, -45.0, -40.0]), frozen)
        self.assertAlmostEqual(frozen[1] - frozen[0], 24.0)

    def test_waterfall_scale_recovers_from_full_band_startup_saturation(self) -> None:
        scale = WaterfallScale(-90.0, -30.0, calibration_rows=2, recovery_rows=2)
        scale.update([-120.0, -119.0, -118.0])
        startup_range = scale.update([-120.0, -119.0, -118.0])

        scale.update([-56.0, -55.0, -54.0])
        recovered = scale.update([-56.0, -55.0, -54.0])

        self.assertNotEqual(startup_range, recovered)
        self.assertEqual(recovered, (-59.0, -35.0))

    def test_waterfall_scale_anchors_noise_near_cold_end_and_preserves_peak(self) -> None:
        scale = WaterfallScale(-90.0, -30.0, calibration_rows=1)
        floor, ceiling = scale.update([-67.0, -66.0, -65.0, -55.0])

        encoded = encode_waterfall_bins([-67.0, -66.0, -65.0, -55.0], floor, ceiling)

        self.assertEqual((floor, ceiling), (-69.0, -45.0))
        self.assertLessEqual(max(encoded[:3]), 17)
        self.assertGreater(encoded[-1], 50)

    def test_waterfall_scale_does_not_recenter_for_a_narrow_peak(self) -> None:
        scale = WaterfallScale(-90.0, -30.0, calibration_rows=1, recovery_rows=2)
        frozen = scale.update([-70.0] * 11 + [-20.0])

        for _ in range(5):
            self.assertEqual(scale.update([-70.0] * 11 + [-10.0]), frozen)


if __name__ == "__main__":
    unittest.main()
