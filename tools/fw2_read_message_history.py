#!/usr/bin/env python3
"""Read bounded WaveRider CW history and detach the routed shell."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly


def main() -> int:
    parser = argparse.ArgumentParser(description="Read recent WaveRider CW messages")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    command = (
        "sudo python3 -c \"import json;"
        "d=json.load(open('/var/lib/freewili-foxhunt/messages.json'));"
        "[print('WRMSG|%d|%d|%.2f|%d|%d|%.2f|%d|%s' % "
        "(i,x['frequency_hz'],x['confidence'],x['repeat_count'],"
        "x.get('evidence_count',0),x.get('agreement',0.0),"
        "1 if x.get('verified',False) else 0,x['text'])) "
        "for i,x in enumerate(d['messages'][-16:])]\""
    )
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        try:
            shell_ok(port, "stty -echo")
            output = shell_readonly(port, command, timeout=30.0)
            for line in output.splitlines():
                if line.startswith("WRMSG|"):
                    print(line)
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
