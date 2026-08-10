#!/usr/bin/env python3
"""Enable WaveRider and start it only after Main's routed shell detaches."""

from __future__ import annotations

import argparse
import time

import serial

try:
    from .fw2_deploy_live_fix import open_shell, shell_ok
    from .serial_put import read_until_quiet
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import open_shell, shell_ok
    from serial_put import read_until_quiet


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable and start WaveRider after detaching the Main shell"
    )
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "sudo systemctl enable freewili-foxhunt.service")
        shell_ok(port, "sudo systemctl stop freewili-foxhunt.service")
        shell_ok(
            port,
            "nohup sh -c 'sleep 3; sudo systemctl start freewili-foxhunt.service' "
            "</dev/null >/tmp/waverider-detached-start.log 2>&1 & true",
        )
        # Main v07 stops acknowledging GUI-console commands while its routed
        # Linux shell is attached.  Exiting the login shell reports SHELL_EXIT
        # to Main; the delayed service start then owns the independent console
        # channel without host contention.
        port.write(b"exit\r")
        port.flush()
        read_until_quiet(port, quiet=0.3, timeout=3.0)

    time.sleep(8.0)
    print("WaveRider enabled and started with the Main shell detached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
