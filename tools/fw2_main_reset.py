#!/usr/bin/env python3
"""Request a non-destructive FreeWili Main CPU software reset over USB."""

from __future__ import annotations

import argparse
import time

from freewili.fw_serial import FreeWiliSerial


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset the FreeWili Main CPU without changing settings or SD cards"
    )
    parser.add_argument("--port", required=True, help="Main USB serial port")
    parser.add_argument(
        "--allow-physical-recovery",
        action="store_true",
        help=(
            "acknowledge that FW2 v07 may re-enumerate with a silent command "
            "parser and then require an on-device physical Main reset"
        ),
    )
    args = parser.parse_args()

    if not args.allow_physical_recovery:
        raise SystemExit(
            "Refusing unattended Main software reset: FX0177 v07 has twice "
            "re-enumerated with a silent parser. Re-run only with "
            "--allow-physical-recovery while someone can physically reset Main."
        )

    device = FreeWiliSerial(args.port, stay_open=True)
    opened = device.open()
    if opened.is_err():
        raise SystemExit(opened.err_value)

    try:
        # The firmware command is Hardware -> Settings -> Software Reset.
        # It intentionally disconnects USB before a response can be guaranteed.
        device._empty_all()  # noqa: SLF001 - no public raw-command API exists
        device.serial_port.send(b"\x02h\\s\\1\n", append_newline=False)
        time.sleep(0.5)
        print("Main CPU software reset requested; a brief USB disconnect is expected.")
    finally:
        device.close(restore_menu=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
