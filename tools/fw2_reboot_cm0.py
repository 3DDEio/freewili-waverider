#!/usr/bin/env python3
"""Request a clean CM0 Linux reboot through an existing Main-routed shell."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import open_shell, shell_ok
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import open_shell, shell_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanly reboot only the FreeWili CM0 Linux OS")
    parser.add_argument("--port", required=True, help="FreeWili Main USB serial port")
    parser.add_argument(
        "--confirm-cm0-reboot",
        action="store_true",
        help="confirm that WaveRider is stopped and a CM0-only reboot is intended",
    )
    parser.add_argument(
        "--keep-waverider-stopped",
        action="store_true",
        help="disable WaveRider autostart before rebooting for bridge maintenance",
    )
    args = parser.parse_args()
    if not args.confirm_cm0_reboot:
        raise SystemExit("Refusing without --confirm-cm0-reboot")

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        if args.keep_waverider_stopped:
            shell_ok(
                port,
                "sudo systemctl disable --now freewili-foxhunt.service",
                timeout=30.0,
            )
        # systemctl returns after queuing the reboot; Main and Display remain
        # powered. The routed shell may disappear immediately afterward.
        shell_ok(port, "sudo systemctl reboot", timeout=10.0)
    message = "CM0 Linux reboot requested; Main and Display were not reset."
    if args.keep_waverider_stopped:
        message += " WaveRider autostart is disabled until validation completes."
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
