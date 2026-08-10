#!/usr/bin/env python3
"""Reveal WaveRider's persistent dynamic panel through Main USB."""

from __future__ import annotations

import argparse
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser(description="Show WaveRider panel 0")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.1) as port:
        port.reset_input_buffer()
        # Ctrl-B selects Main's quiet OneWili command parser.  This does not
        # attach TYPE_SHELL, so CM0 display updates remain live.
        port.write(b"\x02g\\c\\c 0\n")
        port.flush()
        deadline = time.monotonic() + 8.0
        pending = bytearray()
        while time.monotonic() < deadline:
            data = port.read(4096)
            if not data:
                continue
            pending.extend(data)
            start = pending.find(b"[g\\c\\c ")
            if start < 0:
                continue
            end = pending.find(b"]", start)
            if end < 0:
                continue
            frame = bytes(pending[start : end + 1]).strip()
            if not frame.endswith(b" 1]"):
                raise RuntimeError(frame.decode(errors="replace"))
            print("WaveRider panel revealed: " + frame.decode(errors="replace"))
            return 0
    raise RuntimeError(f"Main did not acknowledge WaveRider panel: {bytes(pending)!r}")


if __name__ == "__main__":
    raise SystemExit(main())
