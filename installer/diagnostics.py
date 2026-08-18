"""Privacy-safe WaveRider installer and CM0 support bundles."""

from __future__ import annotations

import base64
import json
import os
import platform
import re
import sys
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import serial

from tools.fw2_deploy_live_fix import (
    detach_shell,
    open_shell,
    read_remote_line_file,
    shell_ok,
)


ProgressCallback = Callable[[int, str], None]
SUPPORT_SCHEMA = 1
REMOTE_REPORT_LIMIT = 12_000
STATUS_LIMIT = 12_000
STATUS_FIELDS = (
    "state",
    "startup_stage",
    "frequency_hz",
    "span_hz",
    "rssi_dbfs",
    "peak_offset_hz",
    "sdr_connected",
    "display_connected",
    "display_message",
    "waterfall_row_rate_hz",
    "display_push_ms",
    "sdr_queue_depth",
    "sdr_realtime_ratio",
    "waterfall_raw_min_dbfs",
    "waterfall_raw_max_dbfs",
    "waterfall_floor_dbfs",
    "waterfall_ceiling_dbfs",
    "waterfall_encoded_min",
    "waterfall_encoded_max",
    "waterfall_encoded_unique",
    "cw_decoder_enabled",
    "audio_monitor_available",
    "updated_unix",
    "updated_monotonic",
    "error",
)
REMOTE_QUERIES = (
    (
        "system.txt",
        "printf 'UTC: '; date -u '+%Y-%m-%dT%H:%M:%SZ'; "
        "printf 'KERNEL: '; uname -a; printf 'UPTIME: '; uptime; "
        "printf 'MODEL: '; tr -d '\\000' </proc/device-tree/model; echo; "
        "printf 'ROOTFS: '; df -h / | tail -n 1",
    ),
    (
        "services.txt",
        "for unit in fwcm0-bridge.service freewili-foxhunt.service "
        "freewili-foxhunt-guard.service; do echo \"=== $unit\"; "
        "systemctl show \"$unit\" -p LoadState -p ActiveState -p SubState "
        "-p UnitFileState -p Result -p MainPID -p ExecMainStatus -p NRestarts "
        "-p ActiveEnterTimestampMonotonic -p InactiveEnterTimestampMonotonic; done",
    ),
    (
        "usb-and-boot.txt",
        "echo '=== USB'; (lsusb 2>&1 || true); echo '=== BOOT ROLE'; "
        "grep -E '^(dtoverlay=dwc2,dr_mode=|gpio=[23]=op,)' "
        "/boot/firmware/config.txt 2>/dev/null || true; "
        "echo '=== TOOLS'; command -v rtl_power || true; command -v fwcm0 || true; "
        "test -f /opt/onewili/cm0/python/onewili_cm0.py && echo ONEWILI_CM0=present "
        "|| echo ONEWILI_CM0=missing",
    ),
    (
        "startup-journal.txt",
        "journalctl -b -u fwcm0-bridge.service -u freewili-foxhunt.service "
        "-u freewili-foxhunt-guard.service -n 100 --no-pager "
        "-o short-monotonic 2>&1",
    ),
)
CW_TEXT_RE = re.compile(
    r"(decoded Morse candidate[^\n]*?\btext=)[^\n]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SupportBundleResult:
    path: Path
    remote_collected: bool
    warnings: tuple[str, ...]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_log_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "WaveRider"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "WaveRider" / "Logs"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "waverider"


def redact_text(value: str) -> str:
    """Remove local home paths and decoded CW text from exported support data."""

    home = str(Path.home())
    if home and home != os.path.sep:
        value = value.replace(home, "~")
    value = CW_TEXT_RE.sub(r"\1<redacted>", value)
    return value


def sanitize_status(status: object) -> dict[str, object]:
    if not isinstance(status, dict):
        raise ValueError("WaveRider runtime status is not a JSON object")
    sanitized = {field: status.get(field) for field in STATUS_FIELDS if field in status}
    if isinstance(sanitized.get("error"), str):
        sanitized["error"] = redact_text(str(sanitized["error"]))
    return sanitized


class SessionLog:
    """Small rotating installer timeline that survives GUI failures."""

    def __init__(self, directory: Path | None = None, *, keep: int = 10) -> None:
        self.directory = directory or default_log_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        self.path = self.directory / f"installer-{stamp}-{os.getpid()}.log"
        self._lock = threading.Lock()
        self._rotate(keep)
        self.write("SESSION", "WaveRider installer session started")

    def _rotate(self, keep: int) -> None:
        logs = sorted(self.directory.glob("installer-*.log"), reverse=True)
        for old in logs[max(keep - 1, 0) :]:
            try:
                old.unlink()
            except OSError:
                pass

    def write(self, event: str, message: str) -> None:
        timestamp = utc_now().isoformat(timespec="milliseconds").replace("+00:00", "Z")
        message = redact_text(message.rstrip()).replace("\r", "")
        continuation = f"\n{timestamp} {event:<10} | "
        line = f"{timestamp} {event:<10} | {message.replace(chr(10), continuation)}\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()


def _progress(callback: ProgressCallback | None, percent: int, message: str) -> None:
    if callback is not None:
        callback(percent, message)


def _project_version(root: Path) -> str:
    try:
        match = re.search(
            r'^version\s*=\s*"([^"]+)"',
            (root / "pyproject.toml").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    except OSError:
        return "unknown"
    return match.group(1) if match else "unknown"


def _remote_report(port: serial.Serial, name: str, command: str) -> str:
    """Capture bounded multiline output through the small FW2 routed mailbox."""

    safe_name = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    remote = f"/tmp/waverider-support-{safe_name}-{os.getpid()}"
    encoded = remote + ".b64"
    encoded_limit = 4 * ((REMOTE_REPORT_LIMIT + 2) // 3) + 81
    try:
        shell_ok(
            port,
            f"({command}) 2>&1 | tail -c {REMOTE_REPORT_LIMIT} > {remote} && "
            f"base64 -w0 {remote} > {encoded}",
            timeout=30.0,
        )
        wire_text = read_remote_line_file(port, encoded, max_bytes=encoded_limit)
        return base64.b64decode(wire_text, validate=True).decode(
            "utf-8", errors="replace"
        )
    finally:
        try:
            shell_ok(port, f"rm -f {remote} {encoded}")
        except Exception:
            pass


def collect_remote_diagnostics(
    port_name: str,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Collect bounded CM0 evidence and always attempt to release an opened route."""

    reports: dict[str, str] = {}
    warnings: list[str] = []
    detach_confirmed = True
    _progress(progress, 5, "Opening a temporary CM0 support route")
    with serial.Serial(port_name, 1_000_000, timeout=0.05) as port:
        opened = False
        try:
            open_shell(port)
            opened = True
            shell_ok(port, "stty -echo")
            for index, (name, command) in enumerate(REMOTE_QUERIES):
                _progress(
                    progress,
                    15 + int(55 * index / max(len(REMOTE_QUERIES), 1)),
                    f"Collecting {name.replace('-', ' ').removesuffix('.txt')}",
                )
                try:
                    reports[name] = redact_text(_remote_report(port, name, command))
                except Exception as error:
                    warning = f"{name}: {redact_text(str(error))}"
                    warnings.append(warning)
                    reports[name] = "COLLECTION ERROR\n" + warning + "\n"
            _progress(progress, 72, "Reading sanitized WaveRider runtime status")
            try:
                raw_status = read_remote_line_file(
                    port,
                    "/run/freewili-foxhunt/status.json",
                    max_bytes=STATUS_LIMIT,
                )
                reports["runtime-status.json"] = json.dumps(
                    sanitize_status(json.loads(raw_status)), indent=2, sort_keys=True
                ) + "\n"
            except Exception as error:
                warning = f"runtime-status.json: {redact_text(str(error))}"
                warnings.append(warning)
                reports["runtime-status.json"] = json.dumps(
                    {"collection_error": warning}, indent=2, sort_keys=True
                ) + "\n"
        finally:
            if opened:
                try:
                    shell_ok(port, "stty echo")
                except Exception:
                    pass
                try:
                    detach_shell(port)
                except Exception as error:
                    detach_confirmed = False
                    warnings.append(
                        "CM0 support route detach could not be confirmed: "
                        + redact_text(str(error))
                    )
    _progress(
        progress,
        80,
        (
            "CM0 support route released"
            if detach_confirmed
            else "CM0 support route release could not be confirmed"
        ),
    )
    return reports, tuple(warnings)


def collect_support_bundle(
    root: Path,
    destination: Path,
    *,
    port_name: str | None = None,
    session_log: Path | None = None,
    progress: ProgressCallback | None = None,
) -> SupportBundleResult:
    """Create an atomic ZIP suitable for a public support attachment."""

    destination = destination.expanduser().resolve()
    if destination.suffix.lower() != ".zip":
        destination = destination.with_suffix(".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    remote_collected = False
    _progress(progress, 1, "Preparing the support bundle")

    with tempfile.TemporaryDirectory(prefix="waverider-support-") as temporary:
        stage = Path(temporary)
        summary = {
            "schema": SUPPORT_SCHEMA,
            "created_utc": utc_now().isoformat().replace("+00:00", "Z"),
            "waverider_version": _project_version(root),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "selected_port": Path(port_name).name if port_name else None,
            "privacy": "CW text, message history, home paths, and saved frequency lists omitted",
        }
        (stage / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / "README.txt").write_text(
            "WaveRider support bundle\n\n"
            "This archive contains installer timing, bounded service state, startup "
            "journal excerpts, USB/boot-role facts, and sanitized runtime status.\n"
            "It does not include CW text, message history, saved frequency lists, "
            "or unrelated files from the user's home directory. Collection never restarts, "
            "reboots, installs, or changes a service. A temporary CM0 shell route is "
            "released before collection ends when possible, and any detach failure is "
            "recorded in warnings.txt.\n",
            encoding="utf-8",
        )
        if session_log is not None and session_log.is_file():
            try:
                content = redact_text(session_log.read_text(encoding="utf-8"))
                (stage / "installer-session.log").write_text(content, encoding="utf-8")
            except OSError as error:
                warnings.append(f"installer log: {redact_text(str(error))}")

        try:
            from installer.device_install import verify_release_checksums

            verify_release_checksums(root)
            integrity = "PASS: native release checksum manifest verified\n"
        except Exception as error:
            integrity = "NOT VERIFIED: " + redact_text(str(error)) + "\n"
            warnings.append(integrity.strip())
        (stage / "release-integrity.txt").write_text(integrity, encoding="utf-8")

        if port_name:
            try:
                reports, remote_warnings = collect_remote_diagnostics(
                    port_name,
                    progress=lambda value, message: _progress(
                        progress, 10 + int(value * 0.75), message
                    ),
                )
                remote_collected = True
                warnings.extend(remote_warnings)
                for name, content in reports.items():
                    (stage / name).write_text(content, encoding="utf-8")
            except Exception as error:
                warning = "CM0 collection: " + redact_text(str(error))
                warnings.append(warning)
                (stage / "cm0-collection-error.txt").write_text(
                    warning + "\n", encoding="utf-8"
                )
        else:
            warning = "CM0 collection skipped: no FreeWili 2 Main port was selected"
            warnings.append(warning)
            (stage / "cm0-collection-error.txt").write_text(
                warning + "\n", encoding="utf-8"
            )

        (stage / "warnings.txt").write_text(
            ("\n".join(warnings) + "\n") if warnings else "None\n",
            encoding="utf-8",
        )
        _progress(progress, 90, "Writing the support ZIP")
        candidate = destination.with_name(destination.name + ".tmp")
        try:
            with zipfile.ZipFile(
                candidate, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for path in sorted(stage.iterdir()):
                    archive.write(path, arcname=path.name)
            os.replace(candidate, destination)
        finally:
            candidate.unlink(missing_ok=True)
    _progress(progress, 100, "Support bundle saved")
    return SupportBundleResult(destination, remote_collected, tuple(warnings))
