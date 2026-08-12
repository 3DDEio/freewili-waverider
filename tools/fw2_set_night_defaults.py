#!/usr/bin/env python3
"""Persist quiet, dark stock-Display startup defaults on a FreeWili.

The first-generation serial-console path is verified.  The former FW2 v07
debug-probe path is deliberately disabled: connected cold-boot acceptance
proved that the presumed LittleFS volume is not consumed by the installed v07
startup code.  The low-level image helpers remain for forensic comparison only
and must not be presented as a working v07 configuration mechanism.

The legacy serial-console path is retained for first-generation hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path

import serial


DEFAULT_BAUDS = (115_200, 1_000_000)
FLASH_BASE = 0x10000000
FIRMWARE_PROBE_SIZE = 0x90000
LITTLEFS_BASE = 0x1037F000
LITTLEFS_SIZE = 0x80000
BLOCK_SIZE = 4096
BLOCK_COUNT = LITTLEFS_SIZE // BLOCK_SIZE
NIGHT_SETTINGS = {
    "sndvol": "0",
    "sndsys": "0",
    "lshowdef": "0",
}
FIRMWARE_TOKENS = (
    b"flsh:settings.txt\x00",
    b"sndvol\x00",
    b"sndsys\x00",
    b"lshowdef\x00",
)
LFS_KWARGS = {
    "block_size": BLOCK_SIZE,
    "block_count": BLOCK_COUNT,
    "read_size": 1,
    "prog_size": 256,
    "cache_size": 256,
    "lookahead_size": 16,
    "name_max": 255,
    "file_max": 0x7FFFFFFF,
    "attr_max": 1022,
}


def read_until_quiet(
    port: serial.Serial,
    *,
    quiet: float = 0.25,
    timeout: float = 3.0,
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


def send_line(port: serial.Serial, value: str, *, delay: float = 0.05) -> str:
    port.write(value.encode("ascii") + b"\n")
    port.flush()
    if delay:
        time.sleep(delay)
    return read_until_quiet(port)


def require_text(value: str, *needles: str) -> None:
    folded = value.casefold()
    if not all(needle.casefold() in folded for needle in needles):
        expected = ", ".join(repr(needle) for needle in needles)
        raise RuntimeError(f"Display console did not show {expected}; response was {value!r}")


def open_settings_console(port_name: str, bauds: Iterable[int]) -> tuple[serial.Serial, int, str]:
    failures: list[str] = []
    for baud in bauds:
        port = serial.Serial(
            port_name,
            baud,
            timeout=0.05,
            rtscts=False,
            xonxoff=False,
            dsrdtr=False,
        )
        try:
            # The vendor library requires a short settle after opening an FTDI
            # endpoint. q/q safely unwinds unknown submenus before z opens
            # Display Settings; no preference is changed during this probe.
            time.sleep(0.6)
            port.reset_input_buffer()
            port.write(b"q\nq\nz\n")
            port.flush()
            response = read_until_quiet(port, timeout=4.0)
            require_text(response, "Settings", "Configure Sound", "Configure Light Show")
            return port, baud, response
        except Exception as error:
            failures.append(f"{baud}: {error}")
            port.close()
    raise RuntimeError(
        "No verified stock Display Settings console was found. "
        + " | ".join(failures)
    )


def apply_night_defaults(port: serial.Serial, *, delay: float = 0.05) -> None:
    response = send_line(port, "g", delay=delay)
    require_text(response, "Configure Sound")

    response = send_line(port, "v", delay=delay)
    require_text(response, "Speaker Volume", "Enter Number")
    response = send_line(port, "0", delay=delay)
    require_text(response, "Configure Sound", "Speaker Volume")

    response = send_line(port, "p", delay=delay)
    if not re.search(r"(?:Sys|System) Sounds.*Enter Number", response, re.IGNORECASE | re.DOTALL):
        raise RuntimeError(f"Display console did not request the System Sounds value: {response!r}")
    response = send_line(port, "0", delay=delay)
    require_text(response, "Configure Sound", "Sounds")

    response = send_line(port, "q", delay=delay)
    require_text(response, "Settings", "Configure Light Show")
    response = send_line(port, "f", delay=delay)
    require_text(response, "Configure Light Show", "Default Light Show")
    response = send_line(port, "c", delay=delay)
    require_text(response, "Default Light Show", "Enter Number")
    response = send_line(port, "0", delay=delay)
    require_text(response, "Configure Light Show", "Default Light Show", "manual")

    response = send_line(port, "q", delay=delay)
    require_text(response, "Settings", "Save Settings as Startup")
    response = send_line(port, "s", delay=delay)
    require_text(response, "Saving", "Done!")


def merge_settings(text: str) -> str:
    """Set the three night defaults while preserving every unrelated line."""

    result: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        key, separator, _value = line.partition("=")
        normalized = key.strip().casefold()
        if separator and normalized in NIGHT_SETTINGS:
            if normalized not in seen:
                result.append(f"{normalized}={NIGHT_SETTINGS[normalized]}")
                seen.add(normalized)
            continue
        result.append(line)
    for key, value in NIGHT_SETTINGS.items():
        if key not in seen:
            result.append(f"{key}={value}")
    return "\n".join(result) + "\n"


def _littlefs_types():
    try:
        from littlefs import LittleFS, UserContext
    except ImportError as error:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "FW2 v07 maintenance requires littlefs-python. Install the "
            "project's maintenance extra: pip install -e '.[maintenance]'"
        ) from error
    return LittleFS, UserContext


def read_settings_image(image: bytes) -> tuple[list[str], str]:
    LittleFS, UserContext = _littlefs_types()
    context = UserContext(buffer=bytearray(image))
    filesystem = LittleFS(context=context, **LFS_KWARGS)
    try:
        files = filesystem.listdir("/")
        if "settings.txt" not in files:
            return files, ""
        with filesystem.open("/settings.txt", "r") as settings_file:
            return files, settings_file.read()
    finally:
        filesystem.unmount()


def update_settings_image(image: bytes) -> bytes:
    if len(image) != LITTLEFS_SIZE:
        raise RuntimeError(
            f"unexpected Display settings volume size: {len(image)} "
            f"(expected {LITTLEFS_SIZE})"
        )
    LittleFS, UserContext = _littlefs_types()
    context = UserContext(buffer=bytearray(image))
    filesystem = LittleFS(context=context, **LFS_KWARGS)
    try:
        files = filesystem.listdir("/")
        previous = ""
        if "settings.txt" in files:
            with filesystem.open("/settings.txt", "r") as settings_file:
                previous = settings_file.read()
        merged = merge_settings(previous)
        if merged == previous:
            return image
        with filesystem.open("/settings.txt", "w") as settings_file:
            settings_file.write(merged)
    finally:
        filesystem.unmount()
    updated = bytes(context.buffer)
    _files, content = read_settings_image(updated)
    require_night_settings(content)
    return updated


def require_night_settings(content: str) -> None:
    parsed: dict[str, str] = {}
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            parsed[key.strip().casefold()] = value.strip()
    missing = {
        key: value for key, value in NIGHT_SETTINGS.items() if parsed.get(key) != value
    }
    if missing:
        raise RuntimeError(f"night defaults did not validate in settings.txt: {missing}")


def changed_blocks(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after) or len(before) % BLOCK_SIZE:
        raise RuntimeError("settings images are not equally sized whole-block images")
    return [
        offset // BLOCK_SIZE
        for offset in range(0, len(before), BLOCK_SIZE)
        if before[offset : offset + BLOCK_SIZE] != after[offset : offset + BLOCK_SIZE]
    ]


def _tcl_path(path: Path) -> str:
    value = str(path.resolve())
    if "}" in value:
        raise RuntimeError(f"OpenOCD path cannot contain a closing brace: {value}")
    return "{" + value + "}"


def run_openocd(
    executable: str,
    config: Path,
    commands: str,
    *,
    scripts: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [executable]
    if scripts is not None:
        command.extend(("-s", str(scripts)))
    command.extend(("-f", str(config), "-c", commands))
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_v07_debug_defaults(
    *,
    openocd: str,
    config: Path,
    scripts: Path | None,
    backup_dir: Path,
) -> tuple[Path, list[int], str]:
    executable = shutil.which(openocd) if "/" not in openocd else openocd
    if not executable or not Path(executable).exists():
        raise RuntimeError(f"OpenOCD executable not found: {openocd}")
    if not config.is_file():
        raise RuntimeError(f"OpenOCD FreeWili 2 config not found: {config}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"FW2Display-littlefs-before-{stamp}.bin"
    metadata_path = backup_path.with_suffix(".json")

    with tempfile.TemporaryDirectory(prefix="fw2-night-defaults-") as temporary:
        temp = Path(temporary)
        firmware_probe = temp / "firmware-probe.bin"
        before_path = temp / "littlefs-before.bin"
        after_read_path = temp / "littlefs-after.bin"
        initial_commands = (
            "init; reset halt; flash probe 0; "
            f"dump_image {_tcl_path(firmware_probe)} {FLASH_BASE:#x} "
            f"{FIRMWARE_PROBE_SIZE:#x}; "
            f"dump_image {_tcl_path(before_path)} {LITTLEFS_BASE:#x} "
            f"{LITTLEFS_SIZE:#x}; reset run; shutdown"
        )
        try:
            probe = run_openocd(executable, config, initial_commands, scripts=scripts)
        except Exception:
            try:
                run_openocd(executable, config, "init; reset run; shutdown", scripts=scripts)
            except Exception:
                pass
            raise
        geometry_output = probe.stdout + probe.stderr
        if "size = 16384 KiB in 4096 sectors" not in geometry_output:
            raise RuntimeError("debug probe did not report the expected 16 MiB / 4 KiB flash")

        firmware = firmware_probe.read_bytes()
        absent = [token.rstrip(b"\x00").decode() for token in FIRMWARE_TOKENS if token not in firmware]
        if absent:
            raise RuntimeError(f"connected Display firmware lacks v07 settings tokens: {absent}")
        before = before_path.read_bytes()
        read_settings_image(before)  # also validates the LittleFS geometry
        backup_path.write_bytes(before)
        metadata_path.write_text(
            json.dumps(
                {
                    "littlefs_base": f"{LITTLEFS_BASE:#x}",
                    "littlefs_size": LITTLEFS_SIZE,
                    "sha256": _sha256(before),
                    "settings": NIGHT_SETTINGS,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        after = update_settings_image(before)
        blocks = changed_blocks(before, after)
        if not blocks:
            return backup_path, [], _sha256(after)

        before_blocks: dict[int, Path] = {}
        after_blocks: dict[int, Path] = {}
        for block in blocks:
            start = block * BLOCK_SIZE
            before_block = temp / f"before-{block:03d}.bin"
            after_block = temp / f"after-{block:03d}.bin"
            before_block.write_bytes(before[start : start + BLOCK_SIZE])
            after_block.write_bytes(after[start : start + BLOCK_SIZE])
            before_blocks[block] = before_block
            after_blocks[block] = after_block

        def flash_commands(paths: dict[int, Path]) -> str:
            pieces = ["init", "reset halt", "flash probe 0"]
            for block, path in paths.items():
                address = LITTLEFS_BASE + block * BLOCK_SIZE
                pieces.append(
                    f"flash write_image erase {_tcl_path(path)} {address:#x} bin"
                )
                pieces.append(f"verify_image {_tcl_path(path)} {address:#x} bin")
            pieces.extend(("reset run", "shutdown"))
            return "; ".join(pieces)

        try:
            run_openocd(executable, config, flash_commands(after_blocks), scripts=scripts)
            verify_commands = (
                "init; reset halt; "
                f"dump_image {_tcl_path(after_read_path)} {LITTLEFS_BASE:#x} "
                f"{LITTLEFS_SIZE:#x}; reset run; shutdown"
            )
            run_openocd(executable, config, verify_commands, scripts=scripts)
            readback = after_read_path.read_bytes()
            if readback != after:
                raise RuntimeError("post-write Display settings volume differs from staged image")
            _files, content = read_settings_image(readback)
            require_night_settings(content)
        except Exception as write_error:
            try:
                run_openocd(executable, config, flash_commands(before_blocks), scripts=scripts)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"settings write failed ({write_error}); automatic rollback also failed "
                    f"({rollback_error}). Restore {backup_path} before further use."
                ) from rollback_error
            raise RuntimeError(
                f"settings write failed and the changed sectors were rolled back: {write_error}"
            ) from write_error
        return backup_path, blocks, _sha256(after)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Set the stock Display startup to manual/off LEDs, zero speaker "
            "volume, and disabled system sounds"
        )
    )
    parser.add_argument(
        "--method",
        choices=("v07-debug", "legacy-console"),
        default="v07-debug",
        help="FW2 v07 debug-probe maintenance or first-generation serial console",
    )
    parser.add_argument("--port", default="/dev/cu.usbserial-FX0177")
    parser.add_argument(
        "--baud",
        type=int,
        action="append",
        help="baud rate to try; repeat to provide multiple values",
    )
    parser.add_argument("--openocd", default="openocd")
    parser.add_argument(
        "--openocd-scripts",
        type=Path,
        help="OpenOCD scripts directory when rp2350.cfg is not installed system-wide",
    )
    parser.add_argument(
        "--openocd-config",
        type=Path,
        default=Path(__file__).with_name("openocd") / "freewili2.cfg",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("device-backups") / "night-defaults",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        if args.method == "v07-debug":
            print(
                "FW2 v07 debug maintenance is disabled: the staged settings "
                "file survives read-back but v07 ignores it during cold boot. "
                "No device write would be attempted."
            )
            return 2
        print(
            f"Would use {args.method} to set lshowdef=manual(0), sndvol=0, "
            "sndsys=off(0), with a rollback backup and read-back verification."
        )
        return 0

    if args.method == "v07-debug":
        raise RuntimeError(
            "FW2 v07 night-default writes are disabled. Connected cold-boot "
            "testing proved that v07 ignores the presumed settings volume. "
            "Restore or retain the rollback backup and use stock firmware "
            "until a version-locked firmware fix is independently verified."
        )

    port, baud, _response = open_settings_console(args.port, args.baud or DEFAULT_BAUDS)
    try:
        apply_night_defaults(port)
        send_line(port, "q")
    finally:
        port.close()
    print(
        f"Night defaults saved through {args.port} at {baud} baud: "
        "LED show manual/off, speaker volume 0, system sounds off."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
