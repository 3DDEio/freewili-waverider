#!/usr/bin/env python3
"""Probe an already-routed FW2 CM0 shell without executing a command."""

from __future__ import annotations

import argparse
import time

import serial

try:
    from .fw2_deploy_live_fix import has_shell_prompt
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import has_shell_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe an existing Main-routed CM0 shell")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        port.reset_input_buffer()
        port.write(b"\r")
        port.flush()
        deadline = time.monotonic() + 5.0
        output = bytearray()
        while time.monotonic() < deadline:
            data = port.read(4096)
            if data:
                output.extend(data)
                if has_shell_prompt(bytes(output)):
                    break
    print(repr(bytes(output)))
    return 0 if has_shell_prompt(bytes(output)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
