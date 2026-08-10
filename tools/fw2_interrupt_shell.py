#!/usr/bin/env python3
"""Interrupt only the foreground process in an existing routed CM0 shell."""

from __future__ import annotations

import argparse
import time

import serial

try:
    from .fw2_deploy_live_fix import has_shell_prompt
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import has_shell_prompt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        port.reset_input_buffer()
        port.write(b"\x03")
        port.flush()
        deadline = time.monotonic() + 8.0
        output = bytearray()
        while time.monotonic() < deadline:
            data = port.read(4096)
            if data:
                output.extend(data)
                if has_shell_prompt(bytes(output)):
                    print("Foreground CM0 shell process interrupted; prompt recovered.")
                    return 0
    print(repr(bytes(output)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
