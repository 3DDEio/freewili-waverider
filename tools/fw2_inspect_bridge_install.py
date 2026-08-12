#!/usr/bin/env python3
"""Read the installed FW2 CM0 bridge configuration without changing it."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly


QUERIES = (
    "systemctl cat fwcm0-bridge.service | head -n 100",
    "command -v fwcm0; fwcm0 --help 2>&1 | head -n 120",
    "ps -eo pid,ppid,user,stat,args --forest | "
    "grep -E 'fwcm0 bridge|/bin/login|-bash|bash --' | grep -v grep | head -n 80",
    "find /opt/onewili /opt/freewilicm0 /usr/local -maxdepth 4 -type f "
    "\\( -iname '*README*' -o -iname '*bridge*' -o -name 'fwcm0' \\) 2>/dev/null | head -n 100",
    "sed -n '1,260p' /opt/onewili/cm0/README.md",
    "sed -n '1,260p' /opt/freewilicm0/include/fwcm0/bridge_proto.h",
    "sed -n '1,360p' /opt/freewilicm0/src/bridge_daemon.cpp",
    "sed -n '1,320p' /opt/freewilicm0/include/fwcm0/shell_server.h; "
    "sed -n '1,420p' /opt/freewilicm0/src/shell_server.cpp",
    "grep -R -n -E 'send_shell_exit|SHELL_ATTACH|SHELL_DETACH|shell.*detach|detach.*shell' "
    "/opt/freewilicm0 2>/dev/null | head -n 200",
    "grep -R -n -E 'OP_CONSOLE|TYPE_CONSOLE|TYPE_SHELL|bridge.sock|connect_cm0' "
    "/opt/freewilicm0 /opt/onewili/cm0 /opt/onewili/python 2>/dev/null | head -n 160",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect installed fwcm0 bridge")
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
            detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
