#!/usr/bin/env python3
"""Open the FreeWili Main-routed CM0 Linux shell over USB."""

from __future__ import annotations

import argparse
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser(description="Open the FreeWili CM0 Linux shell")
    parser.add_argument("--port", required=True, help="Main USB serial port")
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.1) as port:
        # Use quiet command mode directly.  Enabling the interactive Main menu
        # first can strand v07 after a USB host reconnect.
        port.reset_input_buffer()
        port.write(b"\x02l\\b\n")
        port.flush()
        deadline = time.monotonic() + 12.0
        pending = bytearray()
        while time.monotonic() < deadline:
            data = port.read(4096)
            if not data:
                continue
            pending.extend(data)
            while b"\n" in pending:
                raw_line, _, remainder = pending.partition(b"\n")
                pending[:] = remainder
                line = raw_line.strip()
                if not line.startswith(b"[l\\b "):
                    continue
                if b" 1]" not in line:
                    raise SystemExit(line.decode(errors="replace"))
                time.sleep(0.5)
                print(f"CM0 Linux shell requested: {line.decode(errors='replace')}")
                return 0
    raise SystemExit("No correlated Linux-shell response")


if __name__ == "__main__":
    raise SystemExit(main())
