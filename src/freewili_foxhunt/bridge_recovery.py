"""Narrow recovery for a boot-time Main ``TYPE_SHELL`` attachment.

FreeWili v07 stops servicing CM0 app-signal commands while its routed Linux
shell is attached.  The CM0 bridge already treats a self-exiting login session
as authoritative: its PTY reader sends ``SHELL_EXIT`` to Main, which releases
the route.  WaveRider can therefore recover a startup race without restarting
the bridge by hanging up only the bridge-owned ``login -f pi`` child.

This module deliberately does not use broad process-name signals.  Both the
bridge process and its direct login child must match the installed command
lines before a signal is sent.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
from typing import Callable


@dataclass(frozen=True, slots=True)
class ShellRecoveryResult:
    released: bool
    message: str


def _cmdline(process_dir: Path) -> tuple[str, ...]:
    try:
        raw = (process_dir / "cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return ()
    return tuple(part.decode(errors="replace") for part in raw.split(b"\0") if part)


def _parent_pid(process_dir: Path) -> int | None:
    try:
        lines = (process_dir / "status").read_text(errors="replace").splitlines()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return None
    for line in lines:
        if line.startswith("PPid:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _process_dirs(proc_root: Path) -> list[Path]:
    try:
        return [item for item in proc_root.iterdir() if item.name.isdigit()]
    except (FileNotFoundError, PermissionError, OSError):
        return []


def release_initial_shell_route(
    proc_root: Path = Path("/proc"),
    killer: Callable[[int, int], None] = os.kill,
    inhibit_path: Path = Path("/run/freewili-foxhunt/maintenance-shell"),
) -> ShellRecoveryResult:
    """Hang up one exact bridge-owned login session, if present.

    Returning ``released=False`` is normal when the bridge is still booting or
    no shell is attached.  Callers may retry for a short startup-only window.
    """

    if inhibit_path.exists():
        return ShellRecoveryResult(False, "maintenance shell recovery is inhibited")

    process_dirs = _process_dirs(proc_root)
    bridge_pids: set[int] = set()
    for process_dir in process_dirs:
        args = _cmdline(process_dir)
        if len(args) < 2:
            continue
        if Path(args[0]).name == "fwcm0" and args[1] == "bridge":
            bridge_pids.add(int(process_dir.name))

    if not bridge_pids:
        return ShellRecoveryResult(False, "fwcm0 bridge process not ready")

    for process_dir in process_dirs:
        if _parent_pid(process_dir) not in bridge_pids:
            continue
        args = _cmdline(process_dir)
        if not args or Path(args[0]).name != "login":
            continue
        # The shipped bridge creates exactly `login -f pi`. Requiring both
        # arguments prevents an unrelated login process from being touched if
        # the process tree changes in a future CM0 image.
        if len(args) < 3 or args[1:3] != ("-f", "pi"):
            continue
        pid = int(process_dir.name)
        try:
            killer(pid, signal.SIGHUP)
        except (PermissionError, ProcessLookupError, OSError) as error:
            return ShellRecoveryResult(False, f"could not release routed shell: {error}")
        return ShellRecoveryResult(True, f"released bridge login pid {pid}")

    return ShellRecoveryResult(False, "no bridge-owned routed shell found")
