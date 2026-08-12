#!/usr/bin/env python3
"""Best-effort detach of an already-routed CM0 login shell."""

from __future__ import annotations

import argparse

import serial

try:
    from .serial_put import read_until_quiet
except ImportError:  # direct script execution
    from serial_put import read_until_quiet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        port.reset_input_buffer()
        # On FW2 v07, Ctrl-C leaves the tunnel before Linux receives the next
        # bytes. Sending it before `exit` therefore strands the login shell and
        # gives the word `exit` to Main's parser. A plain carriage-return shell
        # command lets the bridge's PTY reader observe login termination and
        # report SHELL_EXIT to Main.
        port.write(b"exit\r")
        port.flush()
        read_until_quiet(port, quiet=0.3, timeout=3.0)
    print("Routed CM0 shell detach sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
