#!/usr/bin/env python3
"""Create a version-locked FW2 v07 Display UF2 with quiet/dark defaults.

This tool never connects to hardware.  It accepts only the exact stock Display
UF2 recovered from the validated FX0177 v07 unit, checks the original Thumb
instructions at both patch sites, changes only the final effect points, and
writes a new UF2 plus a JSON audit manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


UF2_BLOCK_SIZE = 512
UF2_HEADER_SIZE = 32
UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
VERIFIED_STOCK_SHA256 = (
    "0d49cdd3ebf4e0068c283da2bd6d141a2cd76f4f1c78ddc3ac6422cfb6a0bdc9"
)
FLASH_BASE = 0x10000000


@dataclass(frozen=True)
class FirmwarePatch:
    address: int
    before: bytes
    after: bytes
    purpose: str


PATCHES = (
    FirmwarePatch(
        address=0x10000694,
        before=bytes.fromhex("d4f84c14"),
        after=bytes.fromhex("002100bf"),
        purpose="pass light-show selector 0 immediately before activation",
    ),
    FirmwarePatch(
        address=0x100028CC,
        before=bytes.fromhex("0a23"),
        after=bytes.fromhex("0023"),
        purpose="initialize the live light-show object selector to 0 instead of 10",
    ),
    FirmwarePatch(
        address=0x100075B2,
        before=bytes.fromhex("d0d0"),
        after=bytes.fromhex("d0e7"),
        purpose="always branch over the stock startup voice call",
    ),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_uf2(data: bytes) -> None:
    if not data or len(data) % UF2_BLOCK_SIZE:
        raise RuntimeError("input is not a whole-block UF2 file")
    for offset in range(0, len(data), UF2_BLOCK_SIZE):
        start0, start1 = struct.unpack_from("<II", data, offset)
        end = struct.unpack_from("<I", data, offset + UF2_BLOCK_SIZE - 4)[0]
        if (start0, start1, end) != (
            UF2_MAGIC_START0,
            UF2_MAGIC_START1,
            UF2_MAGIC_END,
        ):
            raise RuntimeError(f"invalid UF2 magic in block {offset // UF2_BLOCK_SIZE}")
        payload_size = struct.unpack_from("<I", data, offset + 16)[0]
        if payload_size > 476:
            raise RuntimeError(
                f"invalid UF2 payload size {payload_size} in block "
                f"{offset // UF2_BLOCK_SIZE}"
            )


def _patch_locations(data: bytes, patch: FirmwarePatch) -> list[int]:
    locations: list[int] = []
    for offset in range(0, len(data), UF2_BLOCK_SIZE):
        target, payload_size = struct.unpack_from("<II", data, offset + 12)
        relative = patch.address - target
        if 0 <= relative and relative + len(patch.before) <= payload_size:
            locations.append(offset + UF2_HEADER_SIZE + relative)
    return locations


def patch_verified_stock(data: bytes) -> tuple[bytes, list[dict[str, object]]]:
    validate_uf2(data)
    digest = sha256(data)
    if digest != VERIFIED_STOCK_SHA256:
        raise RuntimeError(
            "refusing unverified Display firmware: SHA256 "
            f"{digest} does not match the validated FX0177 v07 stock image"
        )

    result = bytearray(data)
    audit: list[dict[str, object]] = []
    for patch in PATCHES:
        locations = _patch_locations(data, patch)
        if len(locations) != 1:
            raise RuntimeError(
                f"expected one UF2 payload for {patch.address:#010x}; "
                f"found {len(locations)}"
            )
        location = locations[0]
        actual = bytes(result[location : location + len(patch.before)])
        if actual != patch.before:
            raise RuntimeError(
                f"instruction mismatch at {patch.address:#010x}: "
                f"expected {patch.before.hex()}, found {actual.hex()}"
            )
        result[location : location + len(patch.after)] = patch.after
        audit.append(
            {
                "address": f"{patch.address:#010x}",
                "before": patch.before.hex(),
                "after": patch.after.hex(),
                "purpose": patch.purpose,
                "uf2_block": location // UF2_BLOCK_SIZE,
            }
        )

    patched = bytes(result)
    validate_uf2(patched)
    return patched, audit


def extract_flash_range(data: bytes, address: int, size: int) -> bytes:
    """Return a completely populated raw flash range from a validated UF2."""
    validate_uf2(data)
    if size <= 0:
        raise RuntimeError("flash range size must be positive")
    result = bytearray(b"\xff" * size)
    covered = bytearray(size)
    end = address + size
    for offset in range(0, len(data), UF2_BLOCK_SIZE):
        target, payload_size = struct.unpack_from("<II", data, offset + 12)
        payload_end = target + payload_size
        copy_start = max(address, target)
        copy_end = min(end, payload_end)
        if copy_start >= copy_end:
            continue
        source_start = offset + UF2_HEADER_SIZE + copy_start - target
        destination = copy_start - address
        length = copy_end - copy_start
        result[destination : destination + length] = data[source_start : source_start + length]
        covered[destination : destination + length] = b"\x01" * length
    if not all(covered):
        first_gap = covered.index(0)
        raise RuntimeError(
            f"UF2 does not completely cover flash range at {address + first_gap:#010x}"
        )
    return bytes(result)


def write_patched_firmware(source: Path, output: Path, *, force: bool = False) -> Path:
    if output.exists() and not force:
        raise RuntimeError(f"output already exists (use --force to replace it): {output}")
    original = source.read_bytes()
    patched, audit = patch_verified_stock(original)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    manifest = output.with_suffix(output.suffix + ".json")
    manifest.write_text(
        json.dumps(
            {
                "source": str(source),
                "source_sha256": sha256(original),
                "output": str(output),
                "output_sha256": sha256(patched),
                "patches": audit,
                "recovery": "Reinstall the verified stock FW2Display.uf2.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def write_raw_patch_sectors(
    data: bytes, directory: Path, *, force: bool = False
) -> list[Path]:
    """Write only the 4 KiB sectors containing verified patch sites."""
    sector_offsets = sorted(
        {(patch.address - FLASH_BASE) & ~0xFFF for patch in PATCHES}
    )
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sector_offset in sector_offsets:
        path = directory / f"FW2Display-sector-0x{sector_offset:06x}.bin"
        if path.exists() and not force:
            raise RuntimeError(
                f"raw sector already exists (use --force to replace it): {path}"
            )
        path.write_bytes(
            extract_flash_range(data, FLASH_BASE + sector_offset, 0x1000)
        )
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch the exact verified FX0177 FW2 v07 Display UF2"
    )
    parser.add_argument("source", type=Path, help="verified stock FW2Display.uf2")
    parser.add_argument("output", type=Path, help="new quiet/dark Display UF2")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        help="also write only the patched 4 KiB sectors for verified SWD deployment",
    )
    args = parser.parse_args()

    manifest = write_patched_firmware(args.source, args.output, force=args.force)
    if args.raw_dir:
        for path in write_raw_patch_sectors(
            args.output.read_bytes(), args.raw_dir, force=args.force
        ):
            print(f"Raw patch sector: {path}")
            print(f"Raw sector SHA256: {sha256(path.read_bytes())}")
    print(f"Patched firmware: {args.output}")
    print(f"SHA256: {sha256(args.output.read_bytes())}")
    print(f"Audit manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
