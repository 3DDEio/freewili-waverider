#!/usr/bin/env python3
"""Read the installed CM0 OneWili panel API without changing device state."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import open_shell, shell_ok, shell_readonly


QUERIES = (
    "grep -R -n -E 'def (add|remove|delete|clear|show).*panel|class .*Panel' "
    "/opt/onewili/python /opt/onewili/cm0/python 2>/dev/null | head -n 40",
    "grep -R -n -E '\\\\c\\\\[a-z]|panels\\.' /opt/onewili/cm0/README.md "
    "/opt/onewili/python /opt/onewili/cm0/python 2>/dev/null | head -n 60",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect installed OneWili panel methods")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            for index, query in enumerate(QUERIES, start=1):
                print(f"QUERY {index}")
                print(shell_readonly(port, query, timeout=30.0))
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
