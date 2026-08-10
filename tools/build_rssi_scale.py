#!/usr/bin/env python3
"""Build the continuous FreeWili RGB565 RSSI scale used by WaveRider."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from freewili.image import convert


STOPS = (
    (0.00, (8, 70, 168)),
    (0.25, (8, 125, 218)),
    (0.50, (155, 91, 165)),
    (0.72, (255, 90, 54)),
    (1.00, (255, 228, 91)),
)


def color_at(position: float) -> tuple[int, int, int]:
    for index in range(1, len(STOPS)):
        right_position, right_color = STOPS[index]
        if position <= right_position:
            left_position, left_color = STOPS[index - 1]
            amount = (position - left_position) / (right_position - left_position)
            return tuple(
                round(left + (right - left) * amount)
                for left, right in zip(left_color, right_color, strict=True)
            )
    return STOPS[-1][1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", type=Path, default=Path("assets/ui/rssi-scale-264x10.png"))
    parser.add_argument("--fwi", type=Path, default=Path("assets/ui/RSSISCL.FWI"))
    args = parser.parse_args()

    image = Image.new("RGB", (264, 10))
    pixels = image.load()
    for x in range(image.width):
        color = color_at(x / (image.width - 1))
        for y in range(image.height):
            pixels[x, y] = color

    args.png.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.png, optimize=True)
    result = convert(args.png, args.fwi)
    if result.is_err():
        raise SystemExit(result.err_value)
    print(result.ok_value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
