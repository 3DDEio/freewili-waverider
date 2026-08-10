#!/usr/bin/env python3
"""Atomically deploy the WaveRider live-path fix through the Main-routed shell."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import serial

try:
    from .serial_put import command, put_file, read_until_quiet
except ImportError:  # direct script execution
    from serial_put import command, put_file, read_until_quiet


ROOT = Path(__file__).resolve().parent.parent
INSTALL_ROOT = "/opt/freewili-foxhunt/src/freewili_foxhunt"
SERVICE_SOURCE = ROOT / "deploy/freewili-foxhunt.service"
SERVICE_DESTINATION = "/etc/systemd/system/freewili-foxhunt.service"
SERVICE_STAGING = "/tmp/freewili-foxhunt.service.waverider-new"
MODULES = (
    "cm0_transport.py",
    "display.py",
    "app.py",
    "store.py",
    "rtl_iq.py",
    "spectrum.py",
    "status.py",
)
DEFAULT_MIN_ROW_RATE_HZ = 3.0
STATUS_FIELDS = (
    "state",
    "sdr_connected",
    "display_connected",
    "frequency_hz",
    "selected",
    "waterfall_row_rate_hz",
    "display_push_ms",
    "sdr_queue_depth",
)
ANSI_ESCAPE_RE = re.compile(
    rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))"
)


def has_shell_prompt(value: bytes) -> bool:
    """Recognize plain and ANSI-colored interactive shell prompts."""

    plain = ANSI_ESCAPE_RE.sub(b"", value)
    return plain.rstrip().endswith((b"$", b"#"))


def open_shell(port: serial.Serial) -> None:
    """Open one fresh routed shell and require Main's correlated acknowledgement."""

    # FW2 keeps a routed Linux shell alive across a host serial reconnect. Reuse
    # it when present; Ctrl-C would otherwise tear down a perfectly good route
    # and can leave v07's parser silent during the immediate reopen attempt.
    port.reset_input_buffer()
    port.write(b"\r")
    port.flush()
    deadline = time.monotonic() + 2.0
    existing = bytearray()
    while time.monotonic() < deadline:
        data = port.read(4096)
        if data:
            existing.extend(data)
            if has_shell_prompt(bytes(existing)):
                return

    # A fresh host connection is already outside the routed shell.  Do not
    # enable the interactive Main menu with Ctrl-C before opening the route;
    # v07 can remain stuck at that prompt and stop answering subsequent quiet
    # commands.  Ctrl-B both selects quiet command mode and prefixes the
    # correlated Linux-shell request.
    port.reset_input_buffer()
    port.write(b"\x02l\\b\n")
    port.flush()
    deadline = time.monotonic() + 15.0
    pending = bytearray()
    while time.monotonic() < deadline:
        data = port.read(4096)
        if not data:
            continue
        pending.extend(data)
        while b"\n" in pending:
            raw_line, _, remainder = pending.partition(b"\n")
            pending[:] = remainder
            line = raw_line.strip()
            if line.startswith(b"[l\\b ") and line.endswith(b" 1]"):
                time.sleep(0.5)
                port.write(b"\r")
                port.flush()
                read_until_quiet(port)
                return
    raise RuntimeError("Main did not open a correlated CM0 shell")


def detach_shell(port: serial.Serial) -> None:
    """Exit the routed login shell so Main can service GUI-console traffic."""

    port.write(b"exit\r")
    port.flush()
    read_until_quiet(port, quiet=0.3, timeout=3.0)


def shell_ok(port: serial.Serial, value: str, *, timeout: float = 20.0) -> str:
    """Run a shell command and require its marker-backed zero exit status."""

    return command(port, value, timeout=timeout)


def shell_readonly(
    port: serial.Serial,
    value: str,
    *,
    timeout: float = 20.0,
    attempts: int = 3,
) -> str:
    """Retry a read-only shell query after a lost routed-serial response."""

    last_error: TimeoutError | None = None
    for attempt in range(attempts):
        try:
            return shell_ok(port, value, timeout=timeout)
        except TimeoutError as error:
            last_error = error
            if attempt + 1 >= attempts:
                break
            # A routed response can be dropped even though the shell remains
            # healthy. Return it to a known prompt before retrying the safe
            # read-only command.
            port.write(b"\x03\r")
            port.flush()
            time.sleep(0.25)
            read_until_quiet(port, quiet=0.1, timeout=1.0)
    assert last_error is not None
    raise last_error


def parse_status(status_text: str) -> dict[str, object]:
    """Extract the status JSON from marker-wrapped shell output."""

    status_line = next(
        (line for line in status_text.splitlines() if line.lstrip().startswith("{")),
        "",
    )
    if not status_line:
        raise RuntimeError(f"WaveRider did not publish runtime status:\n{status_text}")
    return json.loads(status_line)


def parse_compact_status(status_text: str) -> dict[str, object]:
    """Decode the deliberately small status record used on the routed console."""

    record = next(
        (line.strip() for line in status_text.splitlines() if line.startswith("WRSTATUS|")),
        "",
    )
    if not record:
        raise RuntimeError(f"WaveRider did not publish compact runtime status:\n{status_text}")
    values = record.split("|")[1:]
    if len(values) != len(STATUS_FIELDS):
        raise RuntimeError(f"Malformed WaveRider compact status: {record}")
    raw = dict(zip(STATUS_FIELDS, values, strict=True))
    return {
        "state": raw["state"],
        "sdr_connected": raw["sdr_connected"] == "1",
        "display_connected": raw["display_connected"] == "1",
        "frequency_hz": int(raw["frequency_hz"]),
        "selected": int(raw["selected"]),
        "waterfall_row_rate_hz": float(raw["waterfall_row_rate_hz"]),
        "display_push_ms": float(raw["display_push_ms"]),
        "sdr_queue_depth": int(raw["sdr_queue_depth"]),
    }


def parse_scalar_output(output: str) -> str:
    """Extract one short scalar from marker-wrapped, echo-suppressed output."""

    candidates = []
    for raw_line in output.splitlines():
        line = ANSI_ESCAPE_RE.sub(b"", raw_line.encode("utf-8")).decode(
            "utf-8", errors="replace"
        ).strip()
        if not line or line.startswith("__WAVERIDER_"):
            continue
        if line.endswith(("$", "#")):
            continue
        candidates.append(line)
    if not candidates:
        raise RuntimeError(f"WaveRider scalar query returned no value:\n{output}")
    return candidates[-1]


def parse_status_chunk(output: str) -> str:
    """Extract a status-file slice while preserving its JSON whitespace."""

    plain = ANSI_ESCAPE_RE.sub(b"", output.encode("utf-8")).decode(
        "utf-8", errors="replace"
    )
    for line in plain.splitlines():
        if line.startswith("WRCHUNK|"):
            return line.removeprefix("WRCHUNK|")
    raise RuntimeError(f"WaveRider status chunk returned no value:\n{output}")


def read_remote_line_file(
    port: serial.Serial,
    path: str,
    *,
    max_bytes: int = 1280,
) -> str:
    """Read one bounded remote line through small routed-console slices."""

    chunk_size = 80
    chunks: list[str] = []
    for offset in range(0, max_bytes, chunk_size):
        command_text = (
            "printf 'WRCHUNK|'; "
            f"cut -c{offset + 1}-{offset + chunk_size} "
            f"{path}"
        )
        chunk = parse_status_chunk(
            shell_readonly(port, command_text, timeout=10.0, attempts=2)
        )
        chunks.append(chunk)
        if len(chunk) < chunk_size:
            break
    else:
        raise RuntimeError(f"Remote line exceeded the bounded {max_bytes}-byte reader")
    return "".join(chunks)


def read_status(port: serial.Serial) -> dict[str, object]:
    """Read the runtime status in small slices that fit FW2's routed console."""

    status = json.loads(
        read_remote_line_file(port, "/run/freewili-foxhunt/status.json")
    )
    if not isinstance(status, dict):
        raise RuntimeError(f"WaveRider status is not an object: {status!r}")
    return status


def require_live_runtime(status: dict[str, object], min_row_rate_hz: float) -> None:
    """Require evidence for both the receiver and the live Display pipeline."""

    if status.get("state") != "live" or not status.get("sdr_connected"):
        raise RuntimeError(f"WaveRider did not reach live SDR state: {status}")
    if not status.get("display_connected"):
        raise RuntimeError(f"WaveRider did not reach live display state: {status}")
    row_rate = float(status.get("waterfall_row_rate_hz") or 0.0)
    if row_rate < min_row_rate_hz:
        raise RuntimeError(
            "WaveRider waterfall is live but below the field cadence gate: "
            f"{row_rate:.2f} Hz < {min_row_rate_hz:.2f} Hz; status={status}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy the correlated waterfall and button-event fix to a running FW2 CM0"
    )
    parser.add_argument("--port", required=True, help="FreeWili Main USB serial port")
    parser.add_argument(
        "--min-row-rate",
        type=float,
        default=DEFAULT_MIN_ROW_RATE_HZ,
        help="minimum measured waterfall rows/second required after deployment",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="inspect the already-installed runtime without transferring files",
    )
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="install and compile the corrected modules but leave WaveRider stopped",
    )
    args = parser.parse_args()
    if args.min_row_rate <= 0:
        parser.error("--min-row-rate must be positive")
    if args.verify_only and args.stage_only:
        parser.error("--verify-only and --stage-only are mutually exclusive")

    destinations = {name: f"{INSTALL_ROOT}/{name}" for name in MODULES}
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        # Keep echo off for the complete transaction. On FW2 v07, echoing a
        # full status command plus its output can exceed the routed console's
        # small burst capacity and discard the completion marker.
        shell_ok(port, "stty -echo")
        try:
            if not args.verify_only:
                shell_ok(port, "sudo systemctl stop freewili-foxhunt.service", timeout=30.0)
                try:
                    for destination in destinations.values():
                        # These Python modules are ordinary pi-owned files.
                        # GNU cp -a can return status 1 while trying to preserve
                        # nonessential metadata over the routed v07 shell even
                        # though the byte copy succeeds. Rollback needs exact
                        # content, not archive metadata, so use a plain forced
                        # file copy and retain the destination's safe path.
                        shell_ok(port, f"cp -f {destination} {destination}.waverider-prev")
                    shell_ok(
                        port,
                        f"sudo cp -a {SERVICE_DESTINATION} "
                        f"{SERVICE_DESTINATION}.waverider-prev",
                    )
                    for name, destination in destinations.items():
                        put_file(port, ROOT / "src/freewili_foxhunt" / name, destination)
                    put_file(port, SERVICE_SOURCE, SERVICE_STAGING)
                    shell_ok(
                        port,
                        f"sudo install -m 0644 {SERVICE_STAGING} {SERVICE_DESTINATION} && "
                        f"rm -f {SERVICE_STAGING} && sudo systemctl daemon-reload",
                        timeout=30.0,
                    )
                    shell_ok(
                        port,
                        f"python3 -m compileall -q {INSTALL_ROOT}",
                        timeout=30.0,
                    )
                except Exception:
                    for destination in destinations.values():
                        try:
                            shell_ok(port, f"cp -f {destination}.waverider-prev {destination}")
                        except Exception:
                            pass
                    try:
                        shell_ok(
                            port,
                            f"sudo cp -a {SERVICE_DESTINATION}.waverider-prev "
                            f"{SERVICE_DESTINATION} && sudo systemctl daemon-reload",
                            timeout=30.0,
                        )
                    except Exception:
                        pass
                    try:
                        shell_ok(
                            port,
                            "sudo systemctl start freewili-foxhunt.service",
                            timeout=30.0,
                        )
                    except Exception:
                        pass
                    raise

                if args.stage_only:
                    print(
                        "Corrected runtime modules installed and compiled; "
                        "WaveRider remains stopped for hardware benchmarking."
                    )
                    return 0
                shell_ok(port, "sudo systemctl start freewili-foxhunt.service", timeout=30.0)
                time.sleep(12.0)
            active = shell_readonly(port, "systemctl is-active freewili-foxhunt.service")
            status = read_status(port)
            journal = shell_readonly(
                port,
                "journalctl -u freewili-foxhunt.service -n 100 --no-pager | "
                "grep -Ei 'unexpected response path|timeout waiting for batched responses|"
                "push waterfall:' | tail -n 10 || true",
                timeout=30.0,
            )
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)

    require_live_runtime(status, args.min_row_rate)
    failure_markers = (
        "unexpected response path",
        "timeout waiting for batched responses",
        "push waterfall:",
    )
    if any(marker in journal.casefold() for marker in failure_markers):
        raise RuntimeError(f"WaveRider journal contains a live-path failure:\n{journal}")
    print(active.strip())
    print(json.dumps(status, indent=2, sort_keys=True))
    print("No matching live-path failures in the last 100 service log lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
