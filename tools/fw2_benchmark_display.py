#!/usr/bin/env python3
"""Upload and run one bounded Display batch benchmark on a quiet FW2 CM0."""

from __future__ import annotations

import argparse
from pathlib import Path

import serial

try:
    from .fw2_deploy_live_fix import open_shell, shell_ok
    from .serial_put import put_file
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import open_shell, shell_ok
    from serial_put import put_file


SOURCE = Path(__file__).with_name("benchmark_display_batch.py")
REMOTE = "/tmp/wr-display-benchmark.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--reuse-panel", action="store_true")
    args = parser.parse_args()
    if min(args.batch, args.rows) <= 0:
        parser.error("batch and rows must be positive")

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            put_file(port, SOURCE, REMOTE)
            reuse = " --reuse-panel" if args.reuse_panel else ""
            output = shell_ok(
                port,
                f"python3 {REMOTE} --batch {args.batch} --rows {args.rows}{reuse}",
                timeout=max(180.0, args.rows * 20.0),
            )
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
    pass_line = next(
        (line for line in output.splitlines() if line.startswith("PASS ")),
        "",
    )
    if not pass_line:
        raise RuntimeError(f"Display benchmark returned no PASS record:\n{output}")
    print(pass_line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
