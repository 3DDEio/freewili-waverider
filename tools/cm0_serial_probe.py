#!/usr/bin/env python3
"""Read a FreeWili CM0 USB gadget console and optionally run one command."""

import os
import select
import sys
import termios
import time


def read_available(fd: int, seconds: float) -> bytes:
    end = time.monotonic() + seconds
    chunks: list[bytes] = []
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], min(0.25, end - time.monotonic()))
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            continue
        if chunk:
            chunks.append(chunk)
    return b"".join(chunks)


def main() -> int:
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} /dev/cu.usbmodemNNNNN [command]", file=sys.stderr)
        return 2

    device = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else None
    fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)

        output = read_available(fd, 1.0)
        os.write(fd, b"\r")
        output += read_available(fd, 1.5)
        if command:
            os.write(fd, command.encode("utf-8") + b"\r")
            output += read_available(fd, 7.0)
        sys.stdout.buffer.write(output)
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
