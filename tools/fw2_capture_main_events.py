#!/usr/bin/env python3
"""Capture bounded raw Main USB events while WaveRider remains live."""

from __future__ import annotations

import argparse
import sys
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture FW2 Main input events")
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        port.reset_input_buffer()
        port.write(b"\x02h\\a\\e 1\n")
        port.flush()
        time.sleep(0.25)
        port.reset_input_buffer()
        print("READY: press Down, Check, Green now", flush=True)
        deadline = time.monotonic() + max(3.0, args.seconds)
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            data = port.read(4096)
            if data:
                chunks.append(data)
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
    print("\nRAW_REPR=" + repr(b"".join(chunks)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
