#!/usr/bin/env python3
"""Resize artwork and build the FreeWili RGB565 WaveRider splash asset."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps
from freewili.image import convert


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--png",
        type=Path,
        default=Path("assets/splash/waverider-splash-480x320.png"),
    )
    parser.add_argument(
        "--fwi",
        type=Path,
        default=Path("assets/splash/WAVERIDR.FWI"),
    )
    args = parser.parse_args()

    with Image.open(args.source) as source:
        rendered = ImageOps.fit(
            source.convert("RGB"),
            (480, 320),
            method=Image.Resampling.LANCZOS,
        )
        args.png.parent.mkdir(parents=True, exist_ok=True)
        rendered.save(args.png, optimize=True)

    result = convert(args.png, args.fwi)
    if result.is_err():
        raise SystemExit(result.err_value)
    print(result.ok_value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
