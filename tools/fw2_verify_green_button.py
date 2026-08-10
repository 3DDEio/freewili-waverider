#!/usr/bin/env python3
"""Prove that a physical Green press retunes a live WaveRider instance."""

from __future__ import annotations

import argparse
import json
import time

import serial

try:
    from .fw2_deploy_live_fix import (
        detach_shell,
        open_shell,
        read_status,
        shell_ok,
        shell_readonly,
    )
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import (
        detach_shell,
        open_shell,
        read_status,
        shell_ok,
        shell_readonly,
    )


def selection_changed(before: dict[str, object], after: dict[str, object]) -> bool:
    """Return true only when both the selected row and tuned frequency move."""

    return (
        after.get("state") == "live"
        and after.get("display_connected") is True
        and after.get("selected") != before.get("selected")
        and after.get("frequency_hz") != before.get("frequency_hz")
    )


def take_snapshot(port_name: str, *, include_journal: bool = False):
    """Read status in one bounded shell session and detach before returning."""

    with serial.Serial(port_name, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            status = read_status(port)
            journal = ""
            if include_journal:
                journal = shell_readonly(
                    port,
                    "journalctl -u freewili-foxhunt.service --since '-2 minutes' "
                    "--no-pager | grep -F 'button action: green' | tail -n 5 || true",
                    timeout=30.0,
                )
            return status, journal
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait for Green and prove that WaveRider selects and tunes the next frequency"
    )
    parser.add_argument("--port", required=True, help="FreeWili Main USB serial port")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    before, _ = take_snapshot(args.port)
    if before.get("state") != "live" or not before.get("display_connected"):
        raise RuntimeError(f"WaveRider is not ready for a button proof: {before}")
    print(
        "READY: press the physical GREEN button once now "
        f"(baseline {before.get('frequency_hz')} Hz); Main shell is detached",
        flush=True,
    )
    # Leave Main completely unowned during the input window. FW2 v07 suppresses
    # app-signal acknowledgements whenever TYPE_SHELL is attached, so polling
    # status here would invalidate the test it claims to perform.
    time.sleep(args.timeout)
    after, journal = take_snapshot(args.port, include_journal=True)
    if not selection_changed(before, after):
        raise RuntimeError(
            "physical Green did not change both selected row and frequency within "
            f"{args.timeout:.1f} seconds; before={before}, after={after}"
        )
    if "button action: green" not in journal.casefold():
        raise RuntimeError(
            "frequency changed but no Green action was recorded in the journal:\n"
            f"{journal}"
        )
    print("PASS: physical Green selected and tuned the next frequency")
    print(json.dumps({"before": before, "after": after}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
