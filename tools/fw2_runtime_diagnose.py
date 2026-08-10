#!/usr/bin/env python3
"""Collect bounded WaveRider failure evidence over FW2's small routed console."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import (
        detach_shell,
        open_shell,
        read_remote_line_file,
        read_status,
        shell_ok,
        shell_readonly,
    )
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import (
        detach_shell,
        open_shell,
        read_remote_line_file,
        read_status,
        shell_ok,
        shell_readonly,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read compact WaveRider service, process, status, and failure evidence"
    )
    parser.add_argument("--port", required=True, help="FreeWili Main USB serial port")
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            service = shell_readonly(
                port,
                "systemctl show freewili-foxhunt.service --property=ActiveState "
                "--property=SubState --property=MainPID --property=ExecMainStatus | "
                "tr '\\n' ' ' | cut -c1-180",
            )
            print(service.strip(), flush=True)
            shell_ok(
                port,
                "journalctl -u freewili-foxhunt.service -n 200 --no-pager > /tmp/wrlog",
                timeout=30.0,
            )
            shell_ok(
                port,
                "grep -Ei 'display|panel|splash|bridge|reconnect|unavailable|warning|"
                "error|traceback|exception|timeout|unexpected|failed|push' "
                "/tmp/wrlog > /tmp/wrerr || true",
            )
            shell_ok(
                port,
                "tail -n 20 /tmp/wrerr | cut -c1-240 | tr '\\n' '~' > /tmp/wrerrflat",
            )
            shell_ok(
                port,
                "tail -n 5 /tmp/wrlog | cut -c1-240 | tr '\\n' '~' > /tmp/wrtailflat",
            )
            print(
                "FAILURES|" + read_remote_line_file(port, "/tmp/wrerrflat", max_bytes=5200),
                flush=True,
            )
            print(
                "JOURNAL_TAIL|" + read_remote_line_file(port, "/tmp/wrtailflat", max_bytes=1600),
                flush=True,
            )
            present = shell_readonly(
                port,
                "test -f /run/freewili-foxhunt/status.json && echo STATUS_PRESENT "
                "|| echo STATUS_MISSING",
            )
            if "STATUS_PRESENT" in present:
                status = read_status(port)
                print(status, flush=True)
                age = shell_readonly(
                    port,
                    "stat -c %Y /run/freewili-foxhunt/status.json",
                )
                print("STATUS_MTIME|" + age.strip(), flush=True)
            else:
                print("STATUS_MISSING", flush=True)
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
