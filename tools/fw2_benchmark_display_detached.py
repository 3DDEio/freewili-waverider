#!/usr/bin/env python3
"""Run one display benchmark only after detaching Main's routed shell."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
    from .serial_put import put_file
    from .serial_put import read_until_quiet
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
    from serial_put import put_file, read_until_quiet


REMOTE_BENCHMARK = "/tmp/wr-display-benchmark.py"
REMOTE_LOG = "/tmp/wr-display-detached.log"
SOURCE = Path(__file__).with_name("benchmark_display_batch.py")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Display with the Main-routed shell detached"
    )
    parser.add_argument("--port", required=True)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--rows", type=int, default=1)
    parser.add_argument("--wait", type=float, default=18.0)
    args = parser.parse_args()
    if min(args.batch, args.rows) <= 0:
        parser.error("batch and rows must be positive")

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "sudo systemctl stop freewili-foxhunt.service")
        put_file(port, SOURCE, REMOTE_BENCHMARK)
        shell_ok(port, f"printf '' > {REMOTE_LOG}")
        shell_ok(
            port,
            "nohup sh -c 'sleep 3; python3 "
            f"{REMOTE_BENCHMARK} --batch {args.batch} --rows {args.rows} "
            f"> {REMOTE_LOG} 2>&1' "
            # shell_ok appends its status-marker command with a semicolon.  A
            # bare trailing ampersand would therefore become the invalid `&;`.
            "</dev/null >/dev/null 2>&1 & true",
        )
        # Exiting the login shell makes BashPty report SHELL_EXIT to Main.  The
        # delayed benchmark then owns only the independent console channel.
        port.write(b"exit\r")
        port.flush()
        read_until_quiet(port, quiet=0.3, timeout=3.0)

    time.sleep(max(8.0, args.wait))

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        try:
            output = shell_readonly(port, f"sed -n '1,160p' {REMOTE_LOG}", timeout=30.0)
        finally:
            detach_shell(port)
    print(output)
    if f"PASS rows={args.rows}" not in output:
        raise RuntimeError("detached Display benchmark did not pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
