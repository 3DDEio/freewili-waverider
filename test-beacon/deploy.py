#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Atomically deploy and verify the optional CircuitPython test beacon."""

from __future__ import annotations

import argparse
import ast
import base64
import time
from pathlib import Path

import serial


def read_until(port: serial.Serial, marker: bytes, timeout: float = 8.0) -> bytes:
    deadline = time.monotonic() + timeout
    received = bytearray()
    while time.monotonic() < deadline:
        data = port.read(4096)
        if data:
            received.extend(data)
            if marker in received:
                return bytes(received)
    raise TimeoutError(f"timed out waiting for {marker!r}: {bytes(received)!r}")


def enter_raw_repl(port: serial.Serial) -> None:
    port.write(b"\r\x03\x03")
    port.flush()
    time.sleep(0.5)
    port.reset_input_buffer()
    port.write(b"\r\x01")
    port.flush()
    read_until(port, b"raw REPL; CTRL-B to exit\r\n>")


def raw_exec(port: serial.Serial, command: str, timeout: float = 8.0) -> bytes:
    port.write(command.encode("utf-8") + b"\x04")
    port.flush()
    response = read_until(port, b"\x04>", timeout=timeout)
    if not response.startswith(b"OK"):
        raise RuntimeError(f"raw REPL rejected command: {response!r}")
    stdout, separator, stderr_and_prompt = response[2:].partition(b"\x04")
    if not separator:
        raise RuntimeError(f"malformed raw REPL response: {response!r}")
    stderr = stderr_and_prompt.removesuffix(b"\x04>")
    if stderr:
        raise RuntimeError(stderr.decode("utf-8", errors="replace"))
    return stdout


def deploy(port_name: str, source: Path) -> None:
    content = source.read_bytes()
    encoded = base64.b64encode(content).decode("ascii")
    with serial.Serial(port_name, 115200, timeout=0.05) as port:
        enter_raw_repl(port)
        raw_exec(port, "import supervisor; supervisor.runtime.autoreload=False")
        raw_exec(port, "f=open('/code.py.new','wb'); f.close()")
        for offset in range(0, len(encoded), 384):
            chunk = encoded[offset : offset + 384]
            raw_exec(
                port,
                "import binascii; f=open('/code.py.new','ab'); "
                f"f.write(binascii.a2b_base64('{chunk}')); f.close()",
            )
        readback = ast.literal_eval(
            raw_exec(port, "print(repr(open('/code.py.new','rb').read()))")
            .decode("utf-8")
            .strip()
        )
        if readback != content:
            raw_exec(port, "import os; os.remove('/code.py.new')")
            raise RuntimeError("read-back failed; active code.py was preserved")
        raw_exec(
            port,
            "import os\n"
            "try:\n"
            " os.remove('/code.py.last')\n"
            "except OSError:\n"
            " pass\n"
            "os.rename('/code.py','/code.py.last')\n"
            "os.rename('/code.py.new','/code.py')",
        )
        print(f"verified {len(content)} bytes and activated {source}")
        port.write(b"\x02")
        port.flush()
        time.sleep(0.25)
        port.write(b"\x04")
        port.flush()
        deadline = time.monotonic() + 7.0
        startup = bytearray()
        while time.monotonic() < deadline:
            startup.extend(port.read(4096))
        print(startup.decode("utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).with_name("code.py"),
    )
    args = parser.parse_args()
    deploy(args.port, args.source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
