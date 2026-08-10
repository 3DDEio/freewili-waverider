#!/usr/bin/env python3
"""Copy one file to the FreeWili CM0 through its USB serial shell."""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import time
from pathlib import Path

import serial


def read_until_quiet(
    port: serial.Serial,
    *,
    quiet: float = 0.2,
    timeout: float = 10.0,
) -> str:
    deadline = time.monotonic() + timeout
    quiet_deadline = time.monotonic() + quiet
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        data = port.read(4096)
        if data:
            chunks.append(data)
            quiet_deadline = time.monotonic() + quiet
        elif chunks and time.monotonic() >= quiet_deadline:
            break
    return b"".join(chunks).decode("utf-8", errors="replace")


def command(port: serial.Serial, value: str, *, timeout: float = 10.0) -> str:
    marker = f"__WAVERIDER_{time.monotonic_ns()}__"
    wire = f"{value}; printf '{marker}:%s\\n' $?\r".encode("ascii")
    port.write(wire)
    port.flush()
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    marker_pattern = re.compile(re.escape(marker.encode("ascii")) + rb":([0-9]+)")
    while time.monotonic() < deadline:
        data = port.read(4096)
        if data:
            chunks.append(data)
            joined = b"".join(chunks)
            match = marker_pattern.search(joined)
            if match:
                output = joined.decode("utf-8", errors="replace")
                status = int(match.group(1))
                if status == 0:
                    return output
                raise RuntimeError(
                    f"CM0 command failed with exit status {status}: {value[:80]}\n{output}"
                )
    output = b"".join(chunks).decode("utf-8", errors="replace")
    raise TimeoutError(f"CM0 did not acknowledge command: {value[:80]}\n{output}")


def put_file(
    port: serial.Serial,
    source: Path,
    destination: str,
    *,
    chunk_size: int = 384,
) -> None:
    content = source.read_bytes()
    encoded = base64.b64encode(content).decode("ascii")
    digest = hashlib.sha256(content).hexdigest()
    staging = f"{destination}.b64"
    candidate = f"{destination}.new"

    # Preserve the installed file until the complete replacement has decoded
    # and passed its checksum. A dropped mailbox chunk can then leave only a
    # disposable .new file, never a half-written runtime module.
    command(port, f"rm -f {staging} {candidate}")
    for offset in range(0, len(encoded), chunk_size):
        chunk = encoded[offset : offset + chunk_size]
        command(port, f"printf %s '{chunk}' >> {staging}")
    output = command(
        port,
        f"base64 -d {staging} > {candidate} && rm -f {staging} && sha256sum {candidate}",
    )
    if digest not in output:
        raise RuntimeError(
            f"checksum mismatch for {source}\nExpected {digest}\nDevice output:\n{output}"
        )
    command(port, f"mv -f {candidate} {destination}")
    print(f"verified {source} -> {destination} ({len(content)} bytes, {digest})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination")
    args = parser.parse_args()

    with serial.Serial(args.port, 115200, timeout=0.05) as port:
        port.write(b"\r")
        port.flush()
        read_until_quiet(port)
        command(port, "stty -echo")
        try:
            put_file(port, args.source, args.destination)
        finally:
            command(port, "stty echo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
