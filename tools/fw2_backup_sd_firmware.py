#!/usr/bin/env python3
"""Back up the stock FW2 firmware images from Main SD without changing them."""

from __future__ import annotations

import argparse
import hashlib
import re
import time
import zlib
from pathlib import Path

import serial


FIRMWARE_IMAGES = ("FW2Main.uf2", "FW2Display.uf2")
FINAL_FRAME = re.compile(
    rb"\[(?:h\\x\\u|u)[^\]]*?success\s+(\d+)\s+bytes\s+(\d+)\s+crc\s+1\]\r?\n"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_verified_payload(received: bytearray) -> bytes | None:
    """Return the payload immediately preceding a size/CRC frame, if valid."""

    for match in FINAL_FRAME.finditer(received):
        sent_size, sent_crc = map(int, match.groups())
        start = match.start() - sent_size
        if start < 0:
            continue
        payload = bytes(received[start : match.start()])
        if zlib.crc32(payload) == sent_crc:
            return payload
    return None


def download_file(port: serial.Serial, source: str, target: Path) -> None:
    """Download one firmware image through FW2 v07's raw Main file protocol."""

    port.reset_input_buffer()
    port.write(b"q\nq\n\x03\nh\nx\nu\n" + source.encode("ascii") + b" \n")
    port.flush()
    received = bytearray()
    last_data = time.monotonic()
    next_progress = 1024 * 1024
    try:
        while time.monotonic() - last_data < 12.0:
            data = port.read(8192)
            if not data:
                continue
            last_data = time.monotonic()
            received.extend(data)
            if len(received) >= next_progress:
                print(f"receiving {source}: at least {len(received)} bytes")
                next_progress += 1024 * 1024
            payload = extract_verified_payload(received)
            if payload is not None:
                with target.open("xb") as output:
                    output.write(payload)
                print(f"verified {source}: {len(payload)} bytes with firmware CRC")
                return
        raise RuntimeError(
            f"timed out before a valid size/CRC trailer for {source}; "
            f"received {len(received)} bytes, tail={bytes(received[-160:])!r}"
        )
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Back up FW2Main.uf2 and FW2Display.uf2 from Main SD"
    )
    parser.add_argument("--port", required=True, help="Main serial port")
    parser.add_argument("--output", type=Path, required=True, help="new backup directory")
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing path: {args.output}")
    args.output.mkdir(parents=True)

    with serial.Serial(args.port, 1_000_000, timeout=8.0) as port:
        for name in FIRMWARE_IMAGES:
            target = args.output / name
            download_file(port, f"1:/firmware/{name}", target)
            print(f"{name}: {target.stat().st_size} bytes sha256={sha256(target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
