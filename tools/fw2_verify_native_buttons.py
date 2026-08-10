#!/usr/bin/env python3
"""Prove native WaveRider button commands and SDR retunes without a shell."""

from __future__ import annotations

import argparse
import json
import time

import serial


SIGNALS = ("wr_ready", "wr_count", "wr_sel", "wr_freq", "wr_cmd")


def query_signal(port: serial.Serial, name: str, timeout: float = 3.0) -> float:
    """Read one correlated app-signal response amid WaveRider bridge traffic."""

    command = f"s\\i\\g {name}".encode("ascii")
    port.reset_input_buffer()
    port.write(b"\x02" + command + b"\n")
    port.flush()
    deadline = time.monotonic() + timeout
    pending = bytearray()
    marker = f" {name} ".encode("ascii")
    while time.monotonic() < deadline:
        data = port.read(4096)
        if not data:
            continue
        pending.extend(data)
        while b"\n" in pending:
            raw, _, remainder = pending.partition(b"\n")
            pending[:] = remainder
            line = raw.strip()
            if not line.startswith(b"[s\\i\\g ") or marker not in line:
                continue
            fields = line.rstrip(b"]").split()
            try:
                index = fields.index(name.encode("ascii"))
                value = float(fields[index + 1])
                success = int(fields[-1])
            except (IndexError, ValueError) as error:
                raise RuntimeError(f"malformed {name} response: {line!r}") from error
            if success != 1:
                raise RuntimeError(f"Main rejected {name} query: {line!r}")
            return value
    raise TimeoutError(f"no correlated response for app signal {name}")


def take_snapshot(port_name: str) -> dict[str, int]:
    """Take a bounded mailbox snapshot, then release Main completely."""

    with serial.Serial(port_name, 1_000_000, timeout=0.05) as port:
        return {name: int(round(query_signal(port, name))) for name in SIGNALS}


def command_fields(raw: int) -> tuple[int, int, int]:
    """Return sequence, opcode, and argument from a packed native command."""

    return raw >> 8, (raw >> 4) & 0xF, raw & 0xF


def prove_change(before: dict[str, int], after: dict[str, int], opcode: int) -> None:
    if after["wr_ready"] != 1:
        raise RuntimeError(f"native Display bridge is not ready: {after}")
    if after["wr_sel"] == before["wr_sel"]:
        raise RuntimeError(f"selected row did not change: before={before}, after={after}")
    if after["wr_freq"] == before["wr_freq"]:
        raise RuntimeError(f"receiver frequency did not change: before={before}, after={after}")
    before_seq, _, _ = command_fields(before["wr_cmd"])
    after_seq, after_opcode, after_argument = command_fields(after["wr_cmd"])
    if after_seq == before_seq or after_opcode != opcode:
        raise RuntimeError(
            f"expected a new native opcode {opcode}: before={before}, after={after}"
        )
    if opcode == 6 and after_argument != after["wr_sel"]:
        raise RuntimeError(
            "Check command argument does not match the applied selection: "
            f"before={before}, after={after}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--button", choices=("green", "dpad", "check"), required=True)
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    before = take_snapshot(args.port)
    if before["wr_ready"] != 1 or before["wr_count"] < 2 or before["wr_freq"] <= 0:
        raise RuntimeError(f"WaveRider native bridge is not ready: {before}")
    if args.button == "green":
        instruction = "press the physical GREEN button once now"
        # Green emits the same absolute-selection command as Check. This is
        # retry-safe and needs no second Apply press on v07.
        opcode = 6
    elif args.button == "dpad":
        instruction = "press DPAD DOWN once now"
        # D-pad movement is an immediate absolute tune. It is the reliable
        # hardware path on units whose context-key firmware does not report
        # GREEN/CHECK edges to a display app.
        opcode = 6
    else:
        instruction = "press the physical CHECK button once now"
        opcode = 6
    print(
        f"READY: {instruction}; baseline={before['wr_freq']} Hz. "
        "The Main connection is now fully released.",
        flush=True,
    )
    time.sleep(args.timeout)
    after = take_snapshot(args.port)
    prove_change(before, after, opcode)
    outcome = "produced a native command and retuned the SDR"
    print(f"PASS: {args.button.upper()} {outcome}")
    print(json.dumps({"before": before, "after": after}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
