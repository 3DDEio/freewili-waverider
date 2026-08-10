#!/usr/bin/env python3
"""Collect bounded diagnostics for the stock fwcm0 bridge daemon."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import open_shell, read_remote_line_file, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import open_shell, read_remote_line_file, shell_ok, shell_readonly


BRIDGE_FAILURE_MARKERS = (
    "router timeout",
    "failed with result",
    "start request repeated too quickly",
)


def require_healthy_bridge(state: str, journal: str) -> None:
    """Reject an inactive bridge or failures after its most recent start."""

    normalized_state = " ".join(state.split())
    required = ("ActiveState=active", "SubState=running", "ExecMainStatus=0")
    missing = [field for field in required if field not in normalized_state]
    restart_match = next(
        (
            part
            for part in normalized_state.split()
            if part.startswith("NRestarts=")
        ),
        "NRestarts=unknown",
    )
    if missing:
        raise RuntimeError(
            f"fwcm0 bridge is not healthy ({', '.join(missing)}; {restart_match}): "
            f"{normalized_state}"
        )
    # A Main-only reset can recover the FPGA router without rebooting Linux, so
    # the current boot's journal may legitimately contain failures belonging to
    # an older bridge instance. Judge only the segment after the latest start;
    # the state above proves that instance is still the active process.
    latest_start = journal.casefold().rfind("started fwcm0-bridge.service")
    current_instance = journal[latest_start:] if latest_start >= 0 else journal
    failures = [
        marker for marker in BRIDGE_FAILURE_MARKERS if marker in current_instance.casefold()
    ]
    if failures:
        raise RuntimeError(
            "fwcm0 bridge failed after its most recent start "
            f"({', '.join(failures)}): {current_instance}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            state = shell_readonly(
                port,
                "systemctl show fwcm0-bridge.service -p ActiveState -p SubState "
                "-p MainPID -p ExecMainStatus -p NRestarts | tr '\\n' ' ' | cut -c1-220",
            )
            print(state.strip(), flush=True)
            shell_ok(
                port,
                "journalctl -b -u fwcm0-bridge.service -n 30 --no-pager | "
                "cut -c1-220 | tr '\\n' '~' > /tmp/wrbridgeflat",
                timeout=30.0,
            )
            journal = read_remote_line_file(port, "/tmp/wrbridgeflat", max_bytes=6600)
            print("BRIDGE_JOURNAL|" + journal, flush=True)
            require_healthy_bridge(state, journal)
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
    print("PASS: fwcm0 bridge is active and has no current-boot router failure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
