#!/usr/bin/env python3
"""Create a portable, deterministic tar.gz archive from one directory tree."""

from __future__ import annotations

import argparse
import gzip
import os
import stat
import tarfile
from pathlib import Path


def archive_paths(source: Path) -> list[Path]:
    return [source, *sorted(source.rglob("*"), key=lambda path: path.as_posix())]


def normalized_mode(path: Path) -> int:
    if path.is_symlink():
        return 0o777
    if path.is_dir():
        return 0o755
    return 0o755 if stat.S_IMODE(path.stat().st_mode) & 0o111 else 0o644


def add_path(bundle: tarfile.TarFile, source: Path, root: Path, epoch: int) -> None:
    relative = source.relative_to(root.parent).as_posix()
    info = tarfile.TarInfo(relative)
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = epoch
    info.mode = normalized_mode(source)

    if source.is_symlink():
        info.type = tarfile.SYMTYPE
        info.linkname = os.readlink(source)
        bundle.addfile(info)
    elif source.is_dir():
        info.type = tarfile.DIRTYPE
        bundle.addfile(info)
    elif source.is_file():
        info.type = tarfile.REGTYPE
        info.size = source.stat().st_size
        with source.open("rb") as handle:
            bundle.addfile(info, handle)
    else:
        raise SystemExit(f"unsupported release path type: {source}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "0")),
    )
    args = parser.parse_args()
    source = args.source.resolve()
    archive = args.archive.resolve()
    if not source.is_dir():
        raise SystemExit(f"source directory not found: {source}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=args.epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as bundle:
                for path in archive_paths(source):
                    add_path(bundle, path, source, args.epoch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
