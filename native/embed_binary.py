#!/usr/bin/env python3
"""Turn a binary release artifact into a small linkable C translation unit."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("symbol")
    parser.add_argument(
        "--xor",
        dest="xor_key",
        type=lambda value: int(value, 0),
        default=0,
        help="XOR every embedded byte with this 0..255 key",
    )
    args = parser.parse_args()

    if not 0 <= args.xor_key <= 0xFF:
        parser.error("--xor must be in the range 0..255")

    data = bytes(value ^ args.xor_key for value in args.source.read_bytes())
    rows = []
    for offset in range(0, len(data), 12):
        values = ", ".join(f"0x{value:02x}" for value in data[offset : offset + 12])
        rows.append(f"    {values},")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "#include <stddef.h>\n#include <stdint.h>\n\n"
        f"const uint8_t {args.symbol}[] = {{\n"
        + "\n".join(rows)
        + "\n};\n"
        f"const size_t {args.symbol}_len = sizeof {args.symbol};\n"
        f"const uint8_t {args.symbol}_xor = 0x{args.xor_key:02x};\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
