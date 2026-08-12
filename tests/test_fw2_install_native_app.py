import struct
from pathlib import Path

import pytest

from tools.fw2_install_native_app import (
    ROOT,
    SRAM_START,
    SRAM_STOP,
    PSRAM_START,
    inspect_volatile_elf,
    inspect_display_uf2,
    openocd_command,
)


def elf32(entry=SRAM_START + 0x178, vaddr=SRAM_START, memsz=0x2000):
    data = bytearray(52 + 32)
    data[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<II", data, 24, entry, 52)
    struct.pack_into("<HH", data, 42, 32, 1)
    struct.pack_into("<IIIIII", data, 52, 1, 0, vaddr, vaddr, 0x100, memsz)
    return bytes(data)


def test_inspect_volatile_elf_accepts_sram_app_and_clears_thumb_bit(tmp_path):
    image = tmp_path / "installer.elf"
    image.write_bytes(elf32(entry=SRAM_START + 0x179))

    entry, segments = inspect_volatile_elf(image)

    assert entry == SRAM_START + 0x178
    assert segments == [(SRAM_START, 0x2000)]


def test_inspect_volatile_elf_accepts_psram_workspace(tmp_path):
    image = tmp_path / "installer.elf"
    image.write_bytes(elf32(vaddr=PSRAM_START, memsz=0x4B000))

    entry, segments = inspect_volatile_elf(image)

    assert entry == SRAM_START + 0x178
    assert segments == [(PSRAM_START, 0x4B000)]


@pytest.mark.parametrize(
    ("entry", "vaddr", "memsz"),
    [
        (0x10000178, SRAM_START, 0x2000),
        (SRAM_START + 0x178, 0x10000000, 0x2000),
        (SRAM_START + 0x178, SRAM_STOP - 0x100, 0x200),
    ],
)
def test_inspect_volatile_elf_rejects_flash_or_out_of_range_segments(
    tmp_path, entry, vaddr, memsz
):
    image = tmp_path / "unsafe.elf"
    image.write_bytes(elf32(entry=entry, vaddr=vaddr, memsz=memsz))

    with pytest.raises(ValueError):
        inspect_volatile_elf(image)


def test_openocd_transaction_loads_and_verifies_without_programming(tmp_path):
    command = openocd_command(
        tmp_path / "openocd",
        None,
        tmp_path / "freewili2.cfg",
        tmp_path / "installer.elf",
        SRAM_START + 0x178,
    )
    joined = " ".join(command)

    assert "load_image" in joined
    assert "verify_image" in joined
    assert "targets rp2350.cm1" in joined
    assert "mww 0x50000464 0x0000ffff" in joined
    assert command.index("mww 0x50000464 0x0000ffff") < command.index(
        next(part for part in command if part.startswith("load_image "))
    )
    assert "reg pc 0x20000178" in joined
    assert "reg msp 0x20082000" in joined
    assert " -s " not in f" {joined} "
    assert "program" not in joined
    assert "flash write" not in joined


def test_committed_native_release_artifacts_pass_fail_closed_gates():
    assert inspect_display_uf2(ROOT / "native/dist/WaveRider.uf2") == "SRAM"
    entry, segments = inspect_volatile_elf(
        ROOT / "native/dist/waverider_installer.elf"
    )
    # Linker layout can legitimately move as the installer changes. The public
    # safety contract is that execution begins at an aligned address in
    # volatile SRAM, not at one historical byte offset.
    assert SRAM_START <= entry < SRAM_STOP
    assert entry % 2 == 0
    assert segments
