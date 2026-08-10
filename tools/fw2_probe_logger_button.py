#!/usr/bin/env python3
"""Test whether Main's logger can observe a full-keyboard button."""

from __future__ import annotations

import argparse
import sys
import time

import serial


BUTTONS = {
    # Logger's Trigger Button setting uses the option index, not the public
    # owGUIButton injection value (whose navigation keys begin at 33).
    "up": 5,
    "down": 6,
    "left": 7,
    "right": 8,
    "center": 9,
    "check": 10,
    "cancel": 11,
    "home": 12,
    "page": 13,
}


def call(port: serial.Serial, command: str, timeout: float = 3.0) -> bytes:
    """Submit one quiet-mode command and return its correlated response."""

    path = command.split(" ", 1)[0].encode("ascii")
    marker = b"[" + path + b" "
    port.reset_input_buffer()
    port.write(b"\x02" + command.encode("ascii") + b"\n")
    port.flush()
    deadline = time.monotonic() + timeout
    pending = bytearray()
    while time.monotonic() < deadline:
        data = port.read(4096)
        if not data:
            continue
        pending.extend(data)
        start = pending.find(marker)
        if start < 0:
            continue
        end = pending.find(b"]", start)
        if end >= 0:
            frame = bytes(pending[start : end + 1])
            if not frame.endswith(b" 1]"):
                raise RuntimeError(f"Main rejected {command!r}: {frame!r}")
            return frame
    raise TimeoutError(f"no correlated response for {command!r}: {bytes(pending)!r}")


def restore_defaults(port: serial.Serial) -> None:
    """Return the otherwise-unused fourth logger instance to stock defaults."""

    for command in (
        "r\\n 3",
        "r\\e",
        "r\\m 0",
        "r\\b 0",
        "r\\p 1000",
        "r\\o 5000",
        "r\\v gpioReport",
        "r\\n 0",
    ):
        try:
            call(port, command)
        except (OSError, RuntimeError, TimeoutError) as error:
            print(f"cleanup warning: {error}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--button", choices=tuple(BUTTONS), default="down")
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")

    button_code = BUTTONS[args.button]
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        try:
            # Instance 3 is idle on the test unit.  Capture no data and finish
            # one millisecond after a trigger; we only need its protocol event.
            for command in (
                "h\\a\\e 1",
                "r\\n 3",
                "r\\e",
                "r\\v none",
                "r\\p 0",
                "r\\o 1",
                "r\\m 1",
                f"r\\b {button_code}",
                "r\\s",
            ):
                print(call(port, command).decode(errors="replace"), flush=True)

            print(
                f"READY: press and hold physical {args.button.upper()} for two seconds",
                flush=True,
            )
            deadline = time.monotonic() + args.seconds
            pending = bytearray()
            triggered = False
            while time.monotonic() < deadline:
                data = port.read(4096)
                if not data:
                    continue
                pending.extend(data)
                if b"[*logger " in data or b"[*logger " in pending:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                if b" 3 triggered" in pending:
                    triggered = True
                    break
            print("\nRESULT: " + ("TRIGGERED" if triggered else "NO TRIGGER"), flush=True)
            return 0 if triggered else 1
        finally:
            restore_defaults(port)


if __name__ == "__main__":
    raise SystemExit(main())
