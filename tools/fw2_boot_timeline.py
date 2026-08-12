#!/usr/bin/env python3
"""Collect a bounded CM0/bridge/SDR boot timeline, then detach cleanly."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly


QUERIES = (
    "systemd-analyze time; systemd-analyze blame | head -n 25",
    "systemctl show fwcm0-bridge.service freewili-foxhunt.service "
    "--property=Id --property=ActiveState --property=SubState "
    "--property=ExecMainStartTimestampMonotonic "
    "--property=ActiveEnterTimestampMonotonic --property=MainPID",
    "journalctl -b -u fwcm0-bridge.service -u freewili-foxhunt.service "
    "-o short-monotonic --no-pager | tail -n 120",
    "journalctl -b -k -o short-monotonic --no-pager | "
    "grep -Ei 'usb|rtl|dvb|dwc|xhci' | tail -n 100",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        try:
            shell_ok(port, "stty -echo")
            for index, query in enumerate(QUERIES, start=1):
                print(f"TIMELINE {index}")
                print(shell_readonly(port, query, timeout=30.0))
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
