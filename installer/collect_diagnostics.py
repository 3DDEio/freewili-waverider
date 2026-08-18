#!/usr/bin/env python3
"""Create a WaveRider support bundle without opening the graphical installer."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from installer.diagnostics import collect_support_bundle, default_log_directory


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parser = argparse.ArgumentParser(description="Create a WaveRider support ZIP")
    parser.add_argument("--port", help="FreeWili 2 Main serial port; omit for local logs only")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / f"WaveRider-Support-{stamp}.zip",
    )
    parser.add_argument(
        "--session-log",
        type=Path,
        help="installer session log; defaults to the newest persistent log",
    )
    args = parser.parse_args()

    session_log = args.session_log
    if session_log is None:
        candidates = sorted(default_log_directory().glob("installer-*.log"))
        session_log = candidates[-1] if candidates else None
    result = collect_support_bundle(
        ROOT,
        args.output,
        port_name=args.port,
        session_log=session_log,
        progress=lambda value, message: print(f"[{value:3d}%] {message}"),
    )
    print(result.path)
    if result.warnings:
        print("The bundle was created with captured warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
