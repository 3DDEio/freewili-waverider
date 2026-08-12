#!/usr/bin/env python3
"""Read compact live CW diagnostics without transferring the full status line."""

from __future__ import annotations

import argparse
import json

import serial

try:
    from .fw2_deploy_live_fix import (
        detach_shell,
        open_shell,
        shell_ok,
        shell_readonly,
    )
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import (
        detach_shell,
        open_shell,
        shell_ok,
        shell_readonly,
    )


FIELDS = (
    "state",
    "frequency_hz",
    "rssi_dbfs",
    "morse_message",
    "morse_confidence",
    "morse_history_count",
    "morse_candidate_count",
    "morse_candidate",
    "morse_candidate_confidence",
    "morse_attempt",
    "morse_attempt_confidence",
    "morse_attempt_timing_confidence",
    "morse_attempt_signal_confidence",
    "morse_attempt_known_confidence",
    "morse_attempt_rejection",
    "morse_attempt_mark_count",
    "morse_attempt_gap_count",
    "morse_attempt_mark_range_ms",
    "morse_attempt_gap_range_ms",
    "morse_attempt_unit_ms",
    "morse_unit_ms",
    "morse_tone_hz",
    "cw_decoder_enabled",
    "audio_monitor_available",
)


def read_field(port: serial.Serial, field: str) -> object:
    command = (
        "sudo python3 -c \"import json;"
        "d=json.load(open('/run/freewili-foxhunt/status.json'));"
        f"print('WRVALUE|'+json.dumps(d.get({field!r})))\""
    )
    output = shell_readonly(port, command, timeout=10.0, attempts=3)
    for line in output.splitlines():
        if "WRVALUE|" in line:
            return json.loads(line.split("WRVALUE|", 1)[1].strip())
    raise RuntimeError(f"WaveRider field {field!r} returned no value:\n{output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read live WaveRider CW diagnostics")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        try:
            shell_ok(port, "stty -echo")
            print(json.dumps({field: read_field(port, field) for field in FIELDS}, sort_keys=True))
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
