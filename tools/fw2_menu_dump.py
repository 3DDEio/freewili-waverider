#!/usr/bin/env python3
"""Inspect a FreeWili v07 interactive-menu path for maintainer diagnostics."""

from __future__ import annotations

import argparse
import time

import serial


def read_until_quiet(port: serial.Serial, quiet: float = 0.4, limit: float = 4.0) -> bytes:
    deadline = time.monotonic() + limit
    quiet_deadline = time.monotonic() + quiet
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        data = port.read(4096)
        if data:
            chunks.append(data)
            quiet_deadline = time.monotonic() + quiet
        elif chunks and time.monotonic() >= quiet_deadline:
            break
    return b"".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump FreeWili interactive menus")
    parser.add_argument("--port", required=True, help="Main USB serial port")
    parser.add_argument(
        "--path",
        default="",
        help="menu letters to visit after root; paths that execute actions can change device state",
    )
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.1) as port:
        port.reset_input_buffer()
        # Match the official host library: unwind two possible submenus, then
        # enable the interactive root menu with Ctrl-C and a line ending. Send
        # the requested path in the same burst so active CM0 GUI traffic cannot
        # reset the parser between menu levels.
        payload = bytearray(b"q\nq\n\x03\n")
        for key in args.path:
            payload.extend(key.encode("ascii") + b"\n")
        port.write(payload)
        port.flush()
        print(read_until_quiet(port).decode(errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
