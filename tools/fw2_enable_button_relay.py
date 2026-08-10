#!/usr/bin/env python3
"""Enable Main's host-event gate without using the CM0 Display channel."""

from __future__ import annotations

import argparse
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser(description="Enable FW2 Main button-event relay")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.1) as port:
        port.reset_input_buffer()
        # h\\a\\e is a Main-host gate.  It is deliberately sent on Main USB,
        # not WaveRider's CM0 OP_CONSOLE stream where v07 never acknowledges it.
        port.write(b"\x02h\\a\\e 1\n")
        port.flush()
        deadline = time.monotonic() + 8.0
        pending = bytearray()
        while time.monotonic() < deadline:
            data = port.read(4096)
            if not data:
                continue
            pending.extend(data)
            start = pending.find(b"[h\\a\\e ")
            if start < 0:
                continue
            end = pending.find(b"]", start)
            if end < 0:
                continue
            frame = bytes(pending[start : end + 1]).strip()
            if not frame.endswith(b" 1]"):
                raise RuntimeError(frame.decode(errors="replace"))
            print("Main button-event relay enabled: " + frame.decode(errors="replace"))
            return 0
    raise RuntimeError(f"Main did not acknowledge button relay: {bytes(pending)!r}")


if __name__ == "__main__":
    raise SystemExit(main())
