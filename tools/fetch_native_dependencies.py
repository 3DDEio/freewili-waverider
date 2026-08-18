#!/usr/bin/env python3
"""Fetch WaveRider's pinned native dependencies from their upstream repos.

Project-source archives intentionally do not redistribute WiliBSP or OneWili.
This helper recreates the exact recursive-clone state by downloading both
projects directly from FreeWili at the commits reviewed by WaveRider.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from prepare_wilibsp import ONEWILI_COMMIT, WILIBSP_COMMIT


ROOT = Path(__file__).resolve().parents[1]
WILIBSP = ROOT / "wilibsp"
ONEWILI = WILIBSP / "libs/onewili"
WILIBSP_URL = "https://github.com/freewili/wilibsp.git"
ONEWILI_URL = "https://github.com/freewili/onewili.git"


def run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def require_git() -> None:
    if shutil.which("git") is None:
        raise SystemExit("Git is required to fetch the pinned native dependencies")


def fetch_repository(destination: Path, url: str, commit: str) -> None:
    if (destination / ".git").exists() or (destination / ".git").is_file():
        actual = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        if actual != commit:
            raise SystemExit(
                f"{destination} is already initialized at {actual}; expected {commit}"
            )
        return
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"refusing to replace non-empty dependency path: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run("git", "clone", "--filter=blob:none", "--no-checkout", url, str(destination))
    run("git", "-C", str(destination), "fetch", "--depth", "1", "origin", commit)
    run("git", "-C", str(destination), "checkout", "--detach", commit)


def main() -> int:
    require_git()
    fetch_repository(WILIBSP, WILIBSP_URL, WILIBSP_COMMIT)
    fetch_repository(ONEWILI, ONEWILI_URL, ONEWILI_COMMIT)
    run(sys.executable, str(ROOT / "tools/prepare_wilibsp.py"), "--verify-only")
    print("Pinned WiliBSP and OneWili dependencies are ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
