"""Host-side FreeWili 2 installation primitives for WaveRider.

The removable-volume and Main command framing in this module is adapted from
FreeWili WiliBSP's MIT-licensed ``tools/fw.py``.  WaveRider keeps the copied
surface deliberately small so release bundles do not need to include the BSP
or OneWili source trees.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import serial

from deploy.serial_install import install_cm0
from tools.fw2_install_native_app import (
    inspect_display_uf2,
    inspect_volatile_elf,
    openocd_command,
    resolve_openocd,
)
from tools.fw2_migrate_apps_menu import migrate_volume


ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]
SD_HOST_COMMAND = r"h\x\k"
SD_HANDOFF_SETTLE_SECONDS = 1.5
SHELL_READY_MARKER = "__WAVERIDER_INSTALLER_READY__"


class DirectSdInstallError(RuntimeError):
    """The direct Apps-SD path failed after safely returning ownership."""


class SdOwnershipError(RuntimeError):
    """Main SD ownership could not be returned; no fallback may proceed."""


def _progress(callback: ProgressCallback | None, percent: int, message: str) -> None:
    if callback is not None:
        callback(percent, message)


def _log(callback: LogCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def verify_release_checksums(root: Path) -> None:
    """Verify every file named by the native release checksum manifest."""

    manifest = root / "native/dist/SHA256SUMS"
    if not manifest.is_file():
        raise FileNotFoundError(f"native checksum manifest not found: {manifest}")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        relative = relative.lstrip("*")
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"release artifact not found: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError(f"checksum mismatch for {relative}")


def find_main_ports() -> list[tuple[str, str]]:
    """Return fwFinder-identified FreeWili Main serial interfaces."""

    try:
        import pyfwfinder
    except ImportError as error:
        raise RuntimeError(
            "pyfwfinder is required. Run the included installer launcher, "
            "or install the project's installer dependencies."
        ) from error

    choices: list[tuple[str, str]] = []
    for device in pyfwfinder.find_all():
        if getattr(device, "device_type", None) != pyfwfinder.FreeWili2:
            continue
        serial_number = str(getattr(device, "serial", "") or "unknown")
        try:
            main = device.get_main_usb_device()
        except (AttributeError, RuntimeError):
            main = next(
                (
                    candidate
                    for candidate in getattr(device, "usb_devices", ())
                    if getattr(candidate, "kind", None) == pyfwfinder.SerialMain
                ),
                None,
            )
        if main is None:
            continue
        for attribute in ("port", "path", "port_name", "location"):
            value = getattr(main, attribute, None)
            if value:
                path = str(value)
                choices.append((f"FreeWili {serial_number} — {path}", path))
                break
    return choices


def _set_sd_host(port_name: str, to_pc: bool, timeout: float = 8.0) -> None:
    """Select Main (false) or the PC USB reader (true), with reply checking."""

    command = f"{SD_HOST_COMMAND} {1 if to_pc else 0}"
    deadline = time.monotonic() + timeout
    with serial.Serial(port_name, 1_000_000, timeout=0.2) as wire:
        wire.reset_input_buffer()
        wire.write(b"\x02" + command.encode("ascii") + b"\n")
        pending = ""
        while time.monotonic() < deadline:
            pending += wire.readline().decode("utf-8", "replace")
            if "]" not in pending:
                continue
            line, pending = pending.split("]", 1)
            line = line.strip() + "]"
            if "[" in line:
                line = line[line.rfind("[") :]
            if not line.startswith("[" + SD_HOST_COMMAND + " "):
                continue
            if line.endswith(" 1]"):
                wire.write(b"\x02")
                return
            raise RuntimeError(f"device rejected {command!r}: {line}")
    raise TimeoutError(f"timeout waiting for Main to acknowledge {command!r}")


def _mounted_volumes() -> set[Path]:
    if sys.platform == "win32":
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        mounted: set[Path] = set()
        for index in range(26):
            letter = chr(65 + index)
            root = Path(f"{letter}:/")
            if not (mask & (1 << index)):
                continue
            if ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") != 2:
                continue
            try:
                next(root.iterdir(), None)
                mounted.add(root)
            except OSError:
                pass
        return mounted
    if sys.platform == "darwin":
        root = Path("/Volumes")
        return set(root.iterdir()) if root.is_dir() else set()
    mounted = set()
    try:
        for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
            _device, mount, *_rest = line.split()
            if mount.startswith(("/media/", "/run/media/")):
                mounted.add(Path(mount.replace("\\040", " ")))
    except OSError:
        pass
    return mounted


def _wait_for_sd(baseline: set[Path], timeout: float = 25.0) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        added = _mounted_volumes() - baseline
        if len(added) == 1:
            return added.pop()
        if len(added) > 1:
            raise RuntimeError(
                "more than one removable volume appeared; refusing to guess"
            )
        time.sleep(0.25)
    raise TimeoutError("timed out waiting for the FreeWili Main SD card")


def install_native_via_sd(
    port_name: str,
    source: Path,
    *,
    timeout: float = 25.0,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    """Install the SRAM-only app directly through Main's supported SD mux."""

    if source.name != "WaveRider.uf2":
        raise ValueError("the Apps-menu payload must be named WaveRider.uf2")
    inspect_display_uf2(source)
    baseline = _mounted_volumes()
    pc_selected = False
    result: dict[str, object] | None = None
    operation_error: Exception | None = None
    try:
        _progress(progress, 10, "Requesting the FreeWili Apps SD card")
        _set_sd_host(port_name, True)
        pc_selected = True
        time.sleep(SD_HANDOFF_SETTLE_SECONDS)
        volume = _wait_for_sd(baseline, timeout)
        _progress(progress, 45, "Installing Apps → Radio → WaveRider")
        result = migrate_volume(volume, source)
        time.sleep(SD_HANDOFF_SETTLE_SECONDS)
        _progress(progress, 90, "Returning the Apps SD card to Main")
    except (OSError, RuntimeError, TimeoutError) as error:
        operation_error = error
    finally:
        if pc_selected:
            try:
                _set_sd_host(port_name, False)
            except Exception as error:
                raise SdOwnershipError(
                    "could not return the Apps SD card to Main; stop and restart "
                    "the FreeWili before retrying"
                ) from error
    if operation_error is not None:
        raise DirectSdInstallError(str(operation_error)) from operation_error
    if result is None:
        raise DirectSdInstallError("the Apps SD operation completed without a result")
    return result


def install_native_via_debug_probe(
    root: Path,
    *,
    progress: ProgressCallback | None = None,
) -> None:
    """Run the physically proven volatile installer when SD mounting fails."""

    openocd, scripts = resolve_openocd(None)
    config = root / "native/freewili2-openocd.cfg"
    installer = root / "native/dist/waverider_installer.elf"
    display_uf2 = root / "native/dist/WaveRider.uf2"
    inspect_display_uf2(display_uf2)
    entry, _segments = inspect_volatile_elf(installer)
    _progress(progress, 20, "Loading the safe installer through the debug probe")
    command = openocd_command(openocd, scripts, config, installer, entry)
    subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
    _progress(progress, 65, "WaveRider is being copied into the Apps menu")
    # The Display-side installer performs a write, full readback, and atomic
    # promotion. Keep host traffic off Main while that bounded transaction runs.
    time.sleep(20.0)
    _progress(progress, 100, "Apps-menu installation launched successfully")


def _main_call(
    wire: serial.Serial,
    inputs: tuple[bytes, ...],
    expected: bytes,
    description: str,
) -> bytes:
    wire.reset_input_buffer()
    payload = bytearray(b"\x02")
    for value in inputs:
        payload.extend(value + b"\n")
    wire.write(payload)
    wire.flush()
    deadline = time.monotonic() + 12.0
    pending = bytearray()
    while time.monotonic() < deadline:
        data = wire.read(4096)
        if not data:
            continue
        pending.extend(data)
        start = pending.find(expected)
        if start < 0:
            continue
        end = pending.find(b"]", start)
        if end < 0:
            continue
        frame = bytes(pending[start : end + 1]).strip()
        if not frame.endswith(b" 1]"):
            raise RuntimeError(f"{description}: {frame.decode(errors='replace')}")
        return frame
    raise TimeoutError(f"no matching Main response while {description}")


def prepare_linux_shell(
    port_name: str,
    *,
    progress: ProgressCallback | None = None,
    timeout: float = 120.0,
) -> None:
    """Power CM0 Linux, request Main's shell route, and prove a prompt responds."""

    commands = (
        ((b"h", b"p", b"s", b"6 1"), b"[h\\p\\s ", "enabling FPGA"),
        ((b"h", b"p", b"s", b"17 1"), b"[h\\p\\s ", "enabling CM0"),
        ((b"h", b"p", b"c", b"1"), b"[h\\p\\c ", "releasing CM0 reset"),
        ((b"l", b"a"), b"[l\\a ", "starting Linux"),
    )
    with serial.Serial(port_name, 1_000_000, timeout=0.1) as wire:
        for index, (inputs, expected, description) in enumerate(commands):
            _progress(progress, index * 8, description.capitalize())
            _main_call(wire, inputs, expected, description)
    _progress(progress, 35, "Waiting for CM0 Linux to boot")
    time.sleep(8.0)
    with serial.Serial(port_name, 1_000_000, timeout=0.1) as wire:
        _main_call(wire, (b"l", b"b"), b"[l\\b ", "opening the Linux shell")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with serial.Serial(port_name, 115200, timeout=0.15) as shell:
                shell.reset_input_buffer()
                shell.write(
                    f"printf '\\n{SHELL_READY_MARKER}\\n'\r".encode("ascii")
                )
                shell.flush()
                response = bytearray()
                probe_deadline = time.monotonic() + 2.0
                while time.monotonic() < probe_deadline:
                    response.extend(shell.read(4096))
                    if SHELL_READY_MARKER.encode("ascii") in response:
                        _progress(progress, 100, "CM0 Linux shell is ready")
                        return
        except (OSError, serial.SerialException):
            pass
        elapsed = timeout - max(0.0, deadline - time.monotonic())
        _progress(
            progress,
            min(95, 35 + int(60 * elapsed / max(timeout, 1.0))),
            "Waiting for the CM0 Linux shell",
        )
        time.sleep(1.0)
    raise TimeoutError("CM0 Linux did not expose a working shell before timeout")


def install_waverider(
    root: Path,
    port_name: str,
    *,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
) -> None:
    """Install both WaveRider halves, with a debug-probe fallback for Main SD."""

    _progress(progress, 1, "Verifying the downloaded release")
    verify_release_checksums(root)
    display_uf2 = root / "native/dist/WaveRider.uf2"
    try:
        _log(log, "Installing the Apps-menu entry through Main's SD interface…")
        install_native_via_sd(
            port_name,
            display_uf2,
            progress=lambda value, message: _progress(
                progress, 3 + int(value * 0.27), message
            ),
        )
        _log(log, "Apps → Radio → WaveRider installed and verified.")
    except DirectSdInstallError as error:
        _log(log, f"Direct SD installation was unavailable: {error}")
        _log(log, "Trying the safe volatile debug-probe installer…")
        install_native_via_debug_probe(
            root,
            progress=lambda value, message: _progress(
                progress, 3 + int(value * 0.27), message
            ),
        )
        _log(log, "The volatile Apps-menu installer completed its host stage.")

    _progress(progress, 32, "Starting CM0 Linux")
    prepare_linux_shell(
        port_name,
        progress=lambda value, message: _progress(
            progress, 32 + int(value * 0.18), message
        ),
    )
    _log(log, "CM0 Linux is ready; installing the receiver runtime…")
    output = install_cm0(
        root,
        port_name,
        activate=True,
        progress=lambda value, message: _progress(
            progress, 50 + int(value * 0.49), message
        ),
    )
    if output.strip():
        _log(log, output.strip())
    _progress(progress, 100, "WaveRider installation complete")
