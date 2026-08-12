#!/usr/bin/env python3
"""Run the WaveRider self-installer from volatile DISPLAY SRAM.

The command deliberately uses OpenOCD ``load_image`` rather than ``program``:
the installer itself never touches the stock DISPLAY QSPI firmware.  The
installer then writes the already safety-checked WaveRider UF2 into Main's
supported ``/apps/Radio`` SD directory. Its embedded metadata labels the menu
entry ``WaveRider``.
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OPENOCD = ROOT / "research/openocd-mac/openocd"
DEFAULT_SCRIPTS = ROOT / "research/openocd-mac/scripts"
DEFAULT_CONFIG = ROOT / "native/freewili2-openocd.cfg"
DEFAULT_INSTALLER = (
    ROOT / "native/dist/waverider_installer.elf"
)
DEFAULT_DISPLAY_UF2 = (
    ROOT / "native/dist/WaveRider.uf2"
)
SRAM_START = 0x20000000
SRAM_STOP = 0x20082000
PSRAM_START = 0x11000000
PSRAM_STOP = 0x11800000
VOLATILE_WINDOWS = (
    ("SRAM", SRAM_START, SRAM_STOP),
    ("PSRAM", PSRAM_START, PSRAM_STOP),
)
ELF32_HEADER_SIZE = 52
ELF32_PROGRAM_HEADER_SIZE = 32
PT_LOAD = 1
UF2_MAGIC = (0x0A324655, 0x9E5D5157, 0x0AB16F30)
QSPI_FLASH = (0x10000000, 0x11000000)
APP_WINDOWS = (
    ("SRAM", 0x20000000, 0x20070000),
    ("PSRAM", 0x11000000, 0x11800000),
)


def inspect_volatile_elf(path: Path) -> tuple[int, list[tuple[int, int]]]:
    """Return the entry point and prove every loadable byte is volatile."""

    data = path.read_bytes()
    if len(data) < ELF32_HEADER_SIZE or data[:4] != b"\x7fELF":
        raise ValueError(f"{path} is not an ELF image")
    if data[4] != 1 or data[5] != 1:
        raise ValueError("installer must be a little-endian ELF32 image")
    entry, phoff = struct.unpack_from("<II", data, 24)
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    if phentsize < ELF32_PROGRAM_HEADER_SIZE or phnum == 0:
        raise ValueError("installer ELF has no usable program headers")
    # ARM ELF entry points carry the Thumb-state bit in bit zero. OpenOCD's
    # PC register receives the aligned address while xPSR below supplies T=1.
    entry &= ~1
    if not SRAM_START <= entry < SRAM_STOP:
        raise ValueError(f"installer entry point 0x{entry:08x} is outside SRAM")

    segments: list[tuple[int, int]] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        if offset + ELF32_PROGRAM_HEADER_SIZE > len(data):
            raise ValueError("installer ELF has a truncated program-header table")
        p_type, _file_offset, vaddr, _paddr, _filesz, memsz = struct.unpack_from(
            "<IIIIII", data, offset
        )
        if p_type != PT_LOAD or memsz == 0:
            continue
        window = next(
            (
                name
                for name, start, stop in VOLATILE_WINDOWS
                if start <= vaddr and memsz <= stop - vaddr
            ),
            None,
        )
        if window is None:
            raise ValueError(
                f"installer segment {index} targets non-volatile memory "
                f"0x{vaddr:08x}+0x{memsz:x}"
            )
        segments.append((vaddr, memsz))
    if not segments:
        raise ValueError("installer ELF has no loadable volatile segments")
    return entry, segments


def inspect_display_uf2(path: Path) -> str:
    """Fail closed unless every UF2 payload targets one app-memory window."""

    data = path.read_bytes()
    if not data or len(data) % 512:
        raise ValueError("app UF2 must contain complete 512-byte blocks")
    target: str | None = None
    declared_blocks: int | None = None
    seen_blocks: set[int] = set()
    payload_blocks = 0
    for index in range(len(data) // 512):
        block = data[index * 512 : (index + 1) * 512]
        m0, m1, flags, address, size, block_no, num_blocks, _family = struct.unpack_from(
            "<8I", block
        )
        end, = struct.unpack_from("<I", block, 508)
        if (m0, m1, end) != UF2_MAGIC:
            raise ValueError(f"UF2 block {index} has invalid magic")
        if num_blocks == 0 or block_no >= num_blocks:
            raise ValueError(f"UF2 block {index} has invalid block numbering")
        if declared_blocks is None:
            declared_blocks = num_blocks
        elif num_blocks != declared_blocks:
            raise ValueError(f"UF2 block {index} has inconsistent total block count")
        if block_no in seen_blocks:
            raise ValueError(f"UF2 block {index} duplicates block number {block_no}")
        seen_blocks.add(block_no)
        if flags & 1 or size == 0:
            continue
        if QSPI_FLASH[0] <= address < QSPI_FLASH[1]:
            raise ValueError(f"UF2 block {index} targets QSPI flash at 0x{address:08x}")
        here = next(
            (
                name
                for name, start, stop in APP_WINDOWS
                if size <= 476 and start <= address and address + size <= stop
            ),
            None,
        )
        if here is None or (target is not None and here != target):
            raise ValueError(f"UF2 block {index} is outside or mixes app-memory windows")
        target = here
        payload_blocks += 1
    if payload_blocks == 0 or target is None:
        raise ValueError("UF2 has no loadable app payload")
    if declared_blocks is None or seen_blocks != set(range(declared_blocks)):
        raise ValueError("UF2 is incomplete: declared block set is not present")
    if target != "SRAM":
        raise ValueError(f"expected an SRAM WaveRider app, got {target}")
    return target


def openocd_command(
    openocd: Path,
    scripts: Path | None,
    config: Path,
    installer: Path,
    entry: int,
) -> list[str]:
    """Build the non-persistent OpenOCD launch transaction."""

    image = str(installer.resolve())
    command = [
        str(openocd.resolve()),
    ]
    if scripts is not None:
        command.extend(("-s", str(scripts.resolve())))
    command.extend([
        "-f", str(config.resolve()), "-c", "init",
        "-c",
        "targets rp2350.cm0",
        "-c",
        "reset halt",
        # The previous display app can leave core 1 and peripheral DMA alive
        # after core 0 halts. Quiesce both cores and the peripheral clock gate
        # before load+verify so a keyboard DMA ring cannot rewrite the freshly
        # loaded installer image during the fail-closed comparison.
        "-c",
        "targets rp2350.cm1",
        "-c",
        "halt",
        "-c",
        "targets rp2350.cm0",
        "-c",
        "halt",
        "-c",
        "mww 0x50000464 0x0000ffff",
        "-c",
        "sleep 50",
        "-c",
        f"load_image {image}",
        "-c",
        f"verify_image {image}",
        "-c",
        f"reg msp 0x{SRAM_STOP:08x}",
        "-c",
        "reg xpsr 0x01000000",
        "-c",
        f"reg pc 0x{entry:08x}",
        "-c",
        "resume",
        "-c",
        "shutdown",
    ])
    return command


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def resolve_openocd(requested: Path | None) -> tuple[Path, Path | None]:
    """Find OpenOCD and an explicit script tree when its bundle needs one."""

    if requested is not None:
        executable = require_file(requested, "OpenOCD executable")
        scripts = DEFAULT_SCRIPTS if executable.resolve() == DEFAULT_OPENOCD.resolve() else None
        return executable, scripts
    if DEFAULT_OPENOCD.is_file() and DEFAULT_SCRIPTS.is_dir():
        return DEFAULT_OPENOCD, DEFAULT_SCRIPTS
    found = shutil.which("openocd")
    if found:
        return Path(found), None
    pico_root = Path.home() / ".pico-sdk/openocd"
    executable_name = "openocd.exe" if sys.platform == "win32" else "openocd"
    candidates = sorted(pico_root.glob(f"*/{executable_name}"), reverse=True)
    if candidates:
        return candidates[0], None
    raise FileNotFoundError(
        "OpenOCD was not found. Install Raspberry Pi's RP2350-capable OpenOCD "
        "or pass --openocd PATH and, when needed, --scripts PATH."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install WaveRider into the FreeWili Apps menu without replacing firmware"
    )
    parser.add_argument("--openocd", type=Path)
    parser.add_argument("--scripts", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--installer", type=Path, default=DEFAULT_INSTALLER)
    parser.add_argument("--display-uf2", type=Path, default=DEFAULT_DISPLAY_UF2)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate artifacts and print the volatile loader command only",
    )
    args = parser.parse_args()

    openocd, detected_scripts = resolve_openocd(args.openocd)
    scripts = args.scripts or detected_scripts
    if scripts is not None:
        scripts = scripts.resolve()
        if not scripts.is_dir():
            raise FileNotFoundError(f"OpenOCD scripts directory not found: {scripts}")
    config = require_file(args.config, "FreeWili OpenOCD configuration")
    installer = require_file(args.installer, "WaveRider installer ELF")
    display_uf2 = require_file(args.display_uf2, "WaveRider display UF2")

    target = inspect_display_uf2(display_uf2)
    entry, segments = inspect_volatile_elf(installer)
    command = openocd_command(openocd, scripts, config, installer, entry)
    print(
        f"verified {display_uf2.name}: {target}; "
        f"installer entry=0x{entry:08x}, {len(segments)} volatile segment(s)"
    )
    if args.dry_run:
        print(" ".join(command))
        return 0

    subprocess.run(command, cwd=ROOT, check=True)
    print(
        "WaveRider installer is running from volatile SRAM. "
        "Wait for INSTALL COMPLETE on the device, then hold Home to return. "
        "Launch it from Apps > Radio > WaveRider."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
