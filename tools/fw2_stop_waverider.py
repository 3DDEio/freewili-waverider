#!/usr/bin/env python3
"""Open one CM0 shell and stop only WaveRider maintenance traffic."""

from __future__ import annotations

import argparse
import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop WaveRider through the CM0 shell")
    parser.add_argument("--port", required=True, help="Main USB serial port")
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        try:
            shell_ok(port, "stty -echo")
            shell_ok(
                port,
                "sudo systemctl stop freewili-foxhunt.service",
                timeout=30.0,
            )
        finally:
            try:
                shell_ok(port, "stty echo")
            finally:
                # Main v07 stops servicing its ordinary command channel while
                # a routed Linux login remains attached. Always end the shell
                # transaction, including after a failed service command.
                detach_shell(port)
        print("WaveRider service stopped; CM0 maintenance shell is quiet.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
