#!/usr/bin/env python3
"""Inspect installed Main scripting/button API surfaces, then resume WaveRider."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly


QUERIES = (
    "grep -n -i -E '\"name\"[^,]*(button|event|script)|button[^,]*\"name\"' "
    "/opt/onewili/python/onewili/api_manifest.json | head -n 180",
    "grep -n '^    def ' /opt/onewili/python/onewili/menus/scripting.py; "
    "sed -n '1,300p' /opt/onewili/python/onewili/menus/scripting.py",
    "find /opt /usr/local/share -maxdepth 5 -type f "
    "\\( -iname '*.rthon' -o -iname '*.wasm' -o -iname '*script*' \\) "
    "2>/dev/null | head -n 180",
    "grep -R -n -i -E 'get.*button|button.*event|read.*button' "
    "/opt/onewili /opt/freewilicm0 /usr/local/share 2>/dev/null | head -n 180",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Main script/button API")
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
            try:
                shell_ok(
                    port,
                    "sudo systemd-run --unit=waverider-script-inspect-resume --on-active=2s "
                    "/bin/systemctl restart freewili-foxhunt.service",
                )
            finally:
                detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
