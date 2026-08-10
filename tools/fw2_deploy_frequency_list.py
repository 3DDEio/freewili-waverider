#!/usr/bin/env python3
"""Install one validated WaveRider list and restart after shell detach."""

from __future__ import annotations

import argparse
from pathlib import Path

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok
    from .serial_put import put_file
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok
    from serial_put import put_file


STATE_LISTS = "/var/lib/freewili-foxhunt/lists"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy a WaveRider frequency list")
    parser.add_argument("--port", required=True)
    parser.add_argument("source", type=Path)
    parser.add_argument("--filename", default="00-ham-village-contest.json")
    args = parser.parse_args()
    if "/" in args.filename or not args.filename.endswith(".json"):
        parser.error("--filename must be one JSON basename")

    destination = f"{STATE_LISTS}/{args.filename}"
    upload = "/tmp/waverider-frequency-list.json"
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            shell_ok(port, "sudo systemctl stop freewili-foxhunt.service")
            shell_ok(port, f"sudo install -d -m 0755 {STATE_LISTS}")
            shell_ok(
                port,
                f"test ! -f {destination} || sudo cp -a {destination} {destination}.bak",
            )
            put_file(port, args.source, upload)
            shell_ok(port, f"python3 -m json.tool {upload} >/dev/null")
            shell_ok(port, f"sudo install -m 0644 {upload} {destination}")
            shell_ok(port, f"rm -f {upload}")
            shell_ok(port, "sudo systemctl enable freewili-foxhunt.service")
            shell_ok(
                port,
                "nohup sh -c 'sleep 3; sudo systemctl start freewili-foxhunt.service' "
                "</dev/null >/tmp/waverider-list-start.log 2>&1 & true",
            )
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)

    print(f"Installed active-first WaveRider list: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
