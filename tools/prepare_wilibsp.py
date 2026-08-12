#!/usr/bin/env python3
"""Verify pinned native dependencies and apply WaveRider's reviewed deltas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WILIBSP = ROOT / "wilibsp"
ONEWILI = WILIBSP / "libs" / "onewili"
WILIBSP_COMMIT = "5fa1e56cea29254badb9c8f71acd027cda0ea45a"
ONEWILI_COMMIT = "e9ff9d946ce009f7515e8506cc91df44a299cb34"
SOURCE_MARKER = ROOT / ".waverider-native-source.json"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        capture_output=True,
    )


def require_commit(repo: Path, expected: str, label: str) -> None:
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        raise SystemExit(
            f"{label} is not initialized. Run: git submodule update --init --recursive"
        )
    actual = git(repo, "rev-parse", "HEAD").stdout.strip()
    if actual != expected:
        raise SystemExit(f"{label} drift: expected {expected}, found {actual}")


def tree_digest(
    repo: Path,
    *,
    exclude_onewili: bool = False,
    normalize_metadata: bool = False,
) -> str:
    """Hash paths, modes, symlink targets, and bytes in an archived vendor tree."""

    digest = hashlib.sha256()
    for path in sorted(repo.rglob("*")):
        relative = path.relative_to(repo)
        if ".git" in relative.parts:
            continue
        if exclude_onewili and relative.parts[:2] == ("libs", "onewili"):
            continue
        if path.is_dir():
            continue
        digest.update(relative.as_posix().encode("utf-8") + b"\0")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if normalize_metadata:
            mode = 0o777 if path.is_symlink() else (0o755 if mode & 0o111 else 0o644)
        digest.update(f"{mode:04o}".encode("ascii") + b"\0")
        if path.is_symlink():
            digest.update(b"link\0" + os.readlink(path).encode("utf-8"))
        else:
            digest.update(b"file\0" + path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_identity(*, normalize_metadata: bool = False) -> dict[str, str]:
    return {
        "format": "waverider-native-source-v1",
        "wilibsp_commit": WILIBSP_COMMIT,
        "wilibsp_sha256": tree_digest(
            WILIBSP,
            exclude_onewili=True,
            normalize_metadata=normalize_metadata,
        ),
        "onewili_commit": ONEWILI_COMMIT,
        "onewili_sha256": tree_digest(
            ONEWILI,
            normalize_metadata=normalize_metadata,
        ),
    }


def verify_source_marker() -> None:
    try:
        recorded = json.loads(SOURCE_MARKER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid archived source identity: {error}") from error
    actual = source_identity(normalize_metadata=True)
    if recorded != actual:
        raise SystemExit(
            "archived WiliBSP/OneWili source content does not match its release identity"
        )


def require_source_identity() -> None:
    if (WILIBSP / ".git").exists() and (ONEWILI / ".git").exists():
        require_commit(WILIBSP, WILIBSP_COMMIT, "WiliBSP")
        require_commit(ONEWILI, ONEWILI_COMMIT, "OneWili")
        return
    if SOURCE_MARKER.is_file():
        verify_source_marker()
        return
    raise SystemExit(
        "vendor source has neither Git commit metadata nor a verified release identity"
    )


def apply_reviewed_patch(repo: Path, patch: Path) -> str:
    forward = git(repo, "apply", "--check", str(patch), check=False)
    if forward.returncode == 0:
        git(repo, "apply", "--whitespace=nowarn", str(patch))
        return "applied"
    reverse = git(repo, "apply", "--reverse", "--check", str(patch), check=False)
    if reverse.returncode == 0:
        return "already applied"
    detail = (forward.stderr or reverse.stderr).strip()
    raise SystemExit(f"cannot apply {patch.name}; dependency drifted\n{detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-source-marker",
        type=Path,
        help="write a content identity for an archive that omits Git metadata",
    )
    args = parser.parse_args(argv)
    if args.write_source_marker is not None:
        args.write_source_marker.write_text(
            json.dumps(
                source_identity(normalize_metadata=True),
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"native source identity: {args.write_source_marker}")
        return 0
    require_source_identity()
    patches = [
        (WILIBSP, ROOT / "native/patches/wilibsp-waverider.patch"),
        (ONEWILI, ROOT / "native/patches/onewili-waverider.patch"),
    ]
    for repo, patch in patches:
        print(f"{patch.name}: {apply_reviewed_patch(repo, patch)}")
    print(f"WiliBSP {WILIBSP_COMMIT}")
    print(f"OneWili {ONEWILI_COMMIT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
