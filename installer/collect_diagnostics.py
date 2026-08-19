#!/usr/bin/env python3
"""Create a WaveRider support bundle without opening the graphical installer."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from installer.diagnostics import SessionLog, collect_support_bundle, redact_text


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
        help="optional prior installer session log to append as context",
    )
    args = parser.parse_args()

    session = SessionLog()
    session.write("SUPPORT", f"Diagnostics requested for {args.port or 'no selected port'}")
    if args.session_log is not None:
        try:
            prior = redact_text(args.session_log.read_text(encoding="utf-8"))
        except OSError as error:
            session.write("PRIOR_LOG", f"Could not read prior log: {error}")
        else:
            session.write("PRIOR_LOG", prior)

    def progress(value: int, message: str) -> None:
        session.write("PROGRESS", f"{value}% {message}")
        print(f"[{value:3d}%] {message}")

    result = collect_support_bundle(
        ROOT,
        args.output,
        port_name=args.port,
        session_log=session.path,
        progress=progress,
    )
    print(result.path)
    if result.warnings:
        print("The bundle was created with captured warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
