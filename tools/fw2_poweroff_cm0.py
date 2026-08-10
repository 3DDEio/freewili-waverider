#!/usr/bin/env python3
"""Request a clean CM0 Linux shutdown before a full device power cycle."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import open_shell, shell_ok
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import open_shell, shell_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanly power off only CM0 Linux")
    parser.add_argument("--port", required=True)
    parser.add_argument("--confirm-cm0-poweroff", action="store_true")
    args = parser.parse_args()
    if not args.confirm_cm0_poweroff:
        raise SystemExit("Refusing without --confirm-cm0-poweroff")

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        shell_ok(port, "sudo systemctl poweroff", timeout=10.0)
    print("CM0 Linux clean shutdown requested; SD writes have been flushed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
