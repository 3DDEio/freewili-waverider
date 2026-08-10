#!/usr/bin/env python3
"""Perform a bounded raw-wire probe of the FreeWili Main command port."""

from __future__ import annotations

import argparse
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe one FreeWili Main command")
    parser.add_argument("--port", required=True, help="Main USB serial port")
    parser.add_argument(
        "--command",
        default="h\\t",
        help=r"quiet-mode command path and arguments (default: h\t RTC read)",
    )
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.1) as port:
        port.reset_input_buffer()
        # Ctrl-B resets the firmware parser to root/quiet.  Keeping this as a
        # single bounded call makes it useful for read-only discovery without
        # leaving Main's interactive menu or CM0 shell attached.
        port.write(b"\x02" + args.command.encode("ascii") + b"\n")
        port.flush()
        deadline = time.monotonic() + 5.0
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            data = port.read(4096)
            if data:
                chunks.append(data)
                if b"]" in data:
                    break

    response = b"".join(chunks)
    print(repr(response))
    return 0 if response else 1


if __name__ == "__main__":
    raise SystemExit(main())
