#!/usr/bin/env python3
"""Verify the Main firmware app-signal mailbox without leaving test state."""

from __future__ import annotations

import argparse
import time

import serial


def call(port: serial.Serial, command: str, timeout: float = 3.0) -> str:
    port.reset_input_buffer()
    port.write(b"\x02" + command.encode("ascii") + b"\n")
    port.flush()
    deadline = time.monotonic() + timeout
    pending = bytearray()
    while time.monotonic() < deadline:
        pending.extend(port.read(4096))
        if b"]" in pending:
            return pending.decode("utf-8", errors="replace").strip()
    raise TimeoutError(f"no response to {command!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    name = "wr_probe"
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        try:
            print(call(port, f"s\\i\\a {name}"))
            print(call(port, f"s\\i\\s {name} 123.5"))
            response = call(port, f"s\\i\\g {name}")
            print(response)
            if name not in response or "123.5" not in response:
                return 1
        finally:
            try:
                print(call(port, f"s\\i\\x {name}"))
            except (OSError, TimeoutError):
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
