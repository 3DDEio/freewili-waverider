#!/usr/bin/env python3
"""Read one compact WaveRider status snapshot and detach the routed shell."""

from __future__ import annotations

import argparse
import json

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, read_status, shell_ok
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, read_status, shell_ok


FIELDS = (
    "state",
    "frequency_hz",
    "rssi_dbfs",
    "peak_offset_hz",
    "display_connected",
    "display_message",
    "waterfall_raw_min_dbfs",
    "waterfall_raw_max_dbfs",
    "waterfall_floor_dbfs",
    "waterfall_ceiling_dbfs",
    "waterfall_encoded_min",
    "waterfall_encoded_max",
    "waterfall_encoded_unique",
    "waterfall_row_rate_hz",
    "display_push_ms",
    "sdr_queue_depth",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read compact live WaveRider status")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            status = read_status(port)
            print(json.dumps({field: status.get(field) for field in FIELDS}, sort_keys=True))
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
