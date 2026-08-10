#!/usr/bin/env python3
"""Cross-platform release installer over the CM0 USB serial console."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import os
import tarfile
import time
from pathlib import Path

import serial


def make_archive(root: Path) -> bytes:
    excluded = {".git", "build", "dist", "__pycache__", ".pytest_cache"}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for path in sorted(root.rglob("*")):
            if any(part in excluded for part in path.parts):
                continue
            relative = path.relative_to(root)
            # Splash assets belong to Main SD and are installed by the separate
            # checksummed firmware uploader. Never send them through the much
            # slower CM0 mailbox tunnel; public release archives still include
            # the complete source PNG and native FWI files.
            if relative.parts and relative.parts[0] == "assets":
                continue
            archive.add(
                path,
                arcname=Path("freewili-foxhunt") / path.relative_to(root),
                recursive=False,
            )
    return stream.getvalue()


def read_until_quiet(port: serial.Serial, quiet: float = 0.3, limit: float = 20.0) -> str:
    deadline = time.monotonic() + limit
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


def command(port: serial.Serial, value: str, limit: float = 20.0) -> str:
    port.write(value.encode("utf-8") + b"\r")
    port.flush()
    return read_until_quiet(port, limit=limit)


def write_paced(
    port: serial.Serial,
    payload: bytes,
    chunk_size: int = 128,
    pause_seconds: float = 0.05,
) -> None:
    """Drain bounded chunks so the Main-to-CM0 mailbox cannot drop a burst."""

    for offset in range(0, len(payload), chunk_size):
        port.write(payload[offset : offset + chunk_size])
        port.flush()
        time.sleep(pause_seconds)


def upload_archive(
    port: serial.Serial,
    archive: bytes,
    remote_archive: str,
    *,
    chunk_size: int = 384,
) -> None:
    """Upload without leaving the shell inside a multiline construct.

    FW2 v07 can drop a sustained Main-to-CM0 mailbox burst.  Each short base64
    append is therefore a complete shell command and must return to the prompt
    before the next one is sent.  An interrupted transfer leaves only ordinary
    temporary files; it can never strand the user at a continuation prompt.
    """

    encoded = base64.b64encode(archive).decode("ascii")
    staging = f"{remote_archive}.b64"
    command(port, f"rm -f {staging} {remote_archive}")
    for offset in range(0, len(encoded), chunk_size):
        chunk = encoded[offset : offset + chunk_size]
        command(port, f"printf %s '{chunk}' >> {staging}")
    command(port, f"base64 -d {staging} > {remote_archive} && rm -f {staging}")


def checked_command(port: serial.Serial, value: str, limit: float = 120.0) -> str:
    marker = f"__FOXHUNT_DONE_{time.monotonic_ns()}__"
    command(port, "stty -echo")
    port.write(
        (value + f"; status=$?; printf '\\n{marker}:%s\\n' \"$status\"\r").encode("utf-8")
    )
    port.flush()
    deadline = time.monotonic() + limit
    chunks: list[bytes] = []
    encoded_marker = marker.encode("ascii")
    while time.monotonic() < deadline:
        data = port.read(4096)
        if data:
            chunks.append(data)
            if encoded_marker in b"".join(chunks):
                break
    else:
        command(port, "stty echo")
        raise TimeoutError(f"timed out waiting for device command: {value}")
    output = b"".join(chunks).decode("utf-8", errors="replace")
    command(port, "stty echo")
    if f"{marker}:0" not in output:
        raise RuntimeError(f"device command failed:\n{output}")
    return output.split(marker, 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="CM0 console, such as /dev/cu.usbmodem1701 or COM7")
    parser.add_argument("--activate", action="store_true", help="select USB-host mode and reboot after install")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    archive = make_archive(root)
    digest = hashlib.sha256(archive).hexdigest()
    remote_archive = "/tmp/freewili-foxhunt.tar.gz"

    with serial.Serial(args.port, 115200, timeout=0.1) as port:
        # FreeWili Main reserves Ctrl-C for leaving its CM0 shell tunnel, so a
        # normal carriage return is the safe way to wake and confirm this prompt.
        port.write(b"\r")
        read_until_quiet(port)
        command(port, "stty -echo")
        upload_archive(port, archive, remote_archive)
        command(port, "stty echo")
        output = command(
            port,
            f"wc -c {remote_archive}; sha256sum {remote_archive}",
        )
        if digest not in output:
            raise SystemExit(
                "Upload checksum verification failed\n"
                f"Expected SHA-256: {digest}\n"
                f"Device reported:\n{output.strip()}"
            )
        output = checked_command(
            port,
            "rm -rf /tmp/freewili-foxhunt-install && mkdir /tmp/freewili-foxhunt-install && "
            f"tar --warning=no-timestamp -xzf {remote_archive} -C /tmp/freewili-foxhunt-install && "
            "sudo sh /tmp/freewili-foxhunt-install/freewili-foxhunt/install.sh",
            limit=180,
        )
        print(output)
        if args.activate:
            print(command(port, "sudo foxhuntctl host --reboot", limit=10))
            print("The CM0 is rebooting into RTL-SDR host mode; this serial port will disconnect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
