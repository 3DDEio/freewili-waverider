#!/usr/bin/env python3
"""Enable the FreeWili FPGA and CM0 Linux power zones over Main USB."""

from __future__ import annotations

import argparse
import time

import serial


def call(port: serial.Serial, inputs: tuple[bytes, ...], expected: bytes, description: str) -> bytes:
    port.reset_input_buffer()
    # Match the official host library: Ctrl-B disables the human-readable menu
    # while leaving menu-path commands available.  Submit the complete path and
    # arguments in one write so concurrent CM0 GUI commands cannot be consumed
    # as a prompted value between menu levels.  Enabling the interactive menu
    # here (Ctrl-C) can strand v07 in a prompt after the USB host reconnects.
    payload = bytearray(b"\x02")
    for value in inputs:
        payload.extend(value + b"\n")
    port.write(payload)
    port.flush()
    deadline = time.monotonic() + 12.0
    pending = bytearray()
    while time.monotonic() < deadline:
        data = port.read(4096)
        if not data:
            continue
        pending.extend(data)
        # Some successful v07 frames contain a human-readable newline before
        # their final ``Ok 1]`` status (notably l\a). Parse the complete bracket
        # frame rather than treating its first line as an immediate failure.
        start = pending.find(expected)
        if start < 0:
            continue
        end = pending.find(b"]", start)
        if end < 0:
            continue
        frame = bytes(pending[start : end + 1]).strip()
        if not frame.endswith(b" 1]"):
            raise SystemExit(f"{description}: {frame.decode(errors='replace')}")
        return frame
    if not pending:
        raise SystemExit(f"No response while {description}")
    raise SystemExit(f"No matching {expected.decode(errors='replace')} response while {description}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enable FreeWili CM0 Linux")
    parser.add_argument("--port", required=True, help="Main USB serial port")
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.1) as port:
        commands = (
            ((b"h", b"p", b"s", b"6 1"), b"[h\\p\\s ", "enabling FPGA zone 6"),
            ((b"h", b"p", b"s", b"17 1"), b"[h\\p\\s ", "enabling CM0 zone 17"),
            ((b"h", b"p", b"c", b"1"), b"[h\\p\\c ", "releasing the CM0 run line"),
            ((b"l", b"a"), b"[l\\a ", "enabling CM0 Linux"),
        )
        for inputs, expected, description in commands:
            response = call(port, inputs, expected, description)
            print(f"{description}: {response.decode(errors='replace').strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
