import hashlib
import struct

import pytest

from tools import fw2_patch_display_startup


def _block(target, payload, *, block_no=0, block_count=1, family=0x46574432):
    block = bytearray(fw2_patch_display_startup.UF2_BLOCK_SIZE)
    struct.pack_into(
        "<IIIIIIII",
        block,
        0,
        fw2_patch_display_startup.UF2_MAGIC_START0,
        fw2_patch_display_startup.UF2_MAGIC_START1,
        0x2000,
        target,
        len(payload),
        block_no,
        block_count,
        family,
    )
    block[32 : 32 + len(payload)] = payload
    struct.pack_into(
        "<I",
        block,
        fw2_patch_display_startup.UF2_BLOCK_SIZE - 4,
        fw2_patch_display_startup.UF2_MAGIC_END,
    )
    return bytes(block)


def _verified_fixture(monkeypatch):
    blocks = []
    for block_no, patch in enumerate(fw2_patch_display_startup.PATCHES):
        payload = bytearray(256)
        base = patch.address & ~0xFF
        offset = patch.address - base
        payload[offset : offset + len(patch.before)] = patch.before
        blocks.append(
            _block(
                base,
                payload,
                block_no=block_no,
                block_count=len(fw2_patch_display_startup.PATCHES),
            )
        )
    data = b"".join(blocks)
    monkeypatch.setattr(
        fw2_patch_display_startup,
        "VERIFIED_STOCK_SHA256",
        hashlib.sha256(data).hexdigest(),
    )
    return data


def test_patches_only_the_verified_instructions(monkeypatch):
    original = _verified_fixture(monkeypatch)

    patched, audit = fw2_patch_display_startup.patch_verified_stock(original)

    differences = [index for index, pair in enumerate(zip(original, patched)) if pair[0] != pair[1]]
    expected = []
    for block_no, patch in enumerate(fw2_patch_display_startup.PATCHES):
        payload_offset = block_no * 512 + 32 + (patch.address & 0xFF)
        expected.extend(
            payload_offset + index
            for index, pair in enumerate(zip(patch.before, patch.after))
            if pair[0] != pair[1]
        )
    assert differences == expected
    assert len(audit) == len(fw2_patch_display_startup.PATCHES)
    fw2_patch_display_startup.validate_uf2(patched)


def test_rejects_unknown_firmware_hash(monkeypatch):
    original = _verified_fixture(monkeypatch)
    monkeypatch.setattr(fw2_patch_display_startup, "VERIFIED_STOCK_SHA256", "0" * 64)

    with pytest.raises(RuntimeError, match="refusing unverified"):
        fw2_patch_display_startup.patch_verified_stock(original)


def test_rejects_instruction_mismatch_even_with_matching_hash(monkeypatch):
    original = _verified_fixture(monkeypatch)
    damaged = bytearray(original)
    damaged[32 + (fw2_patch_display_startup.PATCHES[0].address & 0xFF)] ^= 1
    damaged = bytes(damaged)
    monkeypatch.setattr(
        fw2_patch_display_startup,
        "VERIFIED_STOCK_SHA256",
        hashlib.sha256(damaged).hexdigest(),
    )

    with pytest.raises(RuntimeError, match="instruction mismatch"):
        fw2_patch_display_startup.patch_verified_stock(damaged)


def test_writes_manifest_and_refuses_accidental_overwrite(monkeypatch, tmp_path):
    original = _verified_fixture(monkeypatch)
    source = tmp_path / "stock.uf2"
    output = tmp_path / "patched.uf2"
    source.write_bytes(original)

    manifest = fw2_patch_display_startup.write_patched_firmware(source, output)

    assert output.is_file()
    assert manifest.is_file()
    with pytest.raises(RuntimeError, match="already exists"):
        fw2_patch_display_startup.write_patched_firmware(source, output)


def test_extracts_a_fully_covered_raw_flash_range():
    first = bytes(range(256))
    second = bytes(reversed(range(256)))
    image = _block(0x10005000, first, block_no=0, block_count=2) + _block(
        0x10005100, second, block_no=1, block_count=2
    )

    raw = fw2_patch_display_startup.extract_flash_range(image, 0x10005080, 256)

    assert raw == first[128:] + second[:128]


def test_rejects_an_incompletely_covered_raw_flash_range():
    image = _block(0x10005000, bytes(256))

    with pytest.raises(RuntimeError, match="does not completely cover"):
        fw2_patch_display_startup.extract_flash_range(image, 0x10005000, 512)


def test_writes_only_sectors_that_contain_patch_sites(monkeypatch, tmp_path):
    original = _verified_fixture(monkeypatch)
    patched, _audit = fw2_patch_display_startup.patch_verified_stock(original)

    with pytest.raises(RuntimeError, match="does not completely cover"):
        fw2_patch_display_startup.write_raw_patch_sectors(patched, tmp_path)
