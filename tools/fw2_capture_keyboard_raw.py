#!/usr/bin/env python3
"""Capture WaveRider's raw keyboard-frame changes through RTT channel 0."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import subprocess
import time


ROOT = Path(__file__).resolve().parent.parent
OPENOCD = ROOT / "research/openocd-mac/openocd"
SCRIPTS = ROOT / "research/openocd-mac/scripts"
CONFIG = ROOT / "native/freewili2-openocd.cfg"
RTT_PORT = 9090


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    command = [
        str(OPENOCD),
        "-s",
        str(SCRIPTS),
        "-f",
        str(CONFIG),
        "-c",
        "init",
        "-c",
        'rtt setup 0x20000000 0x82000 "SEGGER RTT"',
        "-c",
        "rtt start",
        "-c",
        f"rtt server start {RTT_PORT} 0",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    stream: socket.socket | None = None
    try:
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("OpenOCD exited before the RTT server opened")
            try:
                stream = socket.create_connection(("127.0.0.1", RTT_PORT), timeout=0.5)
                break
            except OSError:
                time.sleep(0.2)
        if stream is None:
            raise RuntimeError("RTT diagnostics did not open")
        stream.settimeout(0.25)
        print(
            "READY: press DPAD DOWN once, then CHECK once; raw capture is active",
            flush=True,
        )
        deadline = time.monotonic() + args.timeout
        buffered = b""
        records: list[str] = []
        while time.monotonic() < deadline:
            try:
                data = stream.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            buffered += data
            while b"\n" in buffered:
                raw, buffered = buffered.split(b"\n", 1)
                line = raw.decode("ascii", errors="replace").strip()
                if "waverider: kbd raw=" in line:
                    records.append(line)
                    print(line, flush=True)
        if not records:
            raise RuntimeError("no keyboard-frame changes were captured")
        print(f"Captured {len(records)} raw keyboard change(s).")
    finally:
        if stream is not None:
            stream.close()
        process.terminate()
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
