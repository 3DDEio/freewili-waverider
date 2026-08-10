#!/usr/bin/env python3
"""Restart only the stock CM0 mailbox bridge after WaveRider is stopped."""

from __future__ import annotations

import argparse
import time

import serial

try:
    from .fw2_deploy_live_fix import open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import open_shell, shell_ok, shell_readonly


def main() -> int:
    parser = argparse.ArgumentParser(description="Restart the stock fwcm0 bridge service")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            shell_ok(port, "sudo systemctl restart fwcm0-bridge.service", timeout=30.0)
            time.sleep(5.0)
            state = shell_readonly(
                port,
                "systemctl show fwcm0-bridge.service -p ActiveState -p SubState "
                "-p MainPID -p ExecMainStatus | tr '\\n' ' '",
            )
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
    normalized = " ".join(state.split())
    if "ActiveState=active" not in normalized or "SubState=running" not in normalized:
        raise RuntimeError(f"fwcm0 bridge did not restart cleanly: {normalized}")
    print(normalized)
    print("Stock fwcm0 bridge restarted; WaveRider remains stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
