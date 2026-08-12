#!/usr/bin/env python3
"""Verify installed boot-recovery modules, then detach the routed shell."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly


ROOT = Path(__file__).resolve().parent.parent
MODULES = ("app.py", "bridge_recovery.py")
INSTALL_ROOT = "/opt/freewili-foxhunt/src/freewili_foxhunt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    expected = {
        name: hashlib.sha256((ROOT / "src/freewili_foxhunt" / name).read_bytes()).hexdigest()
        for name in MODULES
    }
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            for name in MODULES:
                output = shell_readonly(
                    port,
                    f"sha256sum {INSTALL_ROOT}/{name} | cut -d' ' -f1",
                )
                if expected[name] not in output:
                    raise RuntimeError(
                        f"installed {name} does not match working tree: {output!r}"
                    )
                print(f"MATCH {name} {expected[name]}")
            print(shell_readonly(port, "systemctl is-active freewili-foxhunt.service").strip())
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
