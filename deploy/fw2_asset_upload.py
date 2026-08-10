#!/usr/bin/env python3
"""Upload the WaveRider splash to the FreeWili 2 Main SD image directory."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Callable

from freewili.fw_serial import FreeWiliSerial


DEFAULT_ASSETS = (
    ("assets/splash/WAVERIDR.FWI", "1:/images/WAVERIDR.FWI"),
    ("assets/ui/RSSISCL.FWI", "1:/images/RSSISCL.FWI"),
)


def patch_fw2_file_menu(device: FreeWiliSerial) -> None:
    """Route legacy ``x`` file commands through FW2 v07 Hardware/Files."""

    original: Callable[..., Any] = device.serial_port.send

    def send(value: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(value, str) and value.startswith("x\n"):
            value = "h\n" + value
        return original(value, *args, **kwargs)

    device.serial_port.send = send


def wait_for_commit(device: FreeWiliSerial, target: str, size: int, initial: str) -> str:
    """Require the firmware's delayed final size confirmation.

    FW2 v07 can leave a second response frame behind after ``send_file`` has
    returned. Starting another transfer at that point lets the stale frame
    satisfy the next request and produces a directory entry that the Display
    processor cannot yet open.
    """

    expected = f"success {size} bytes"
    messages = [initial]
    deadline = time.monotonic() + 12.0
    while expected not in " ".join(messages) and time.monotonic() < deadline:
        response = device._wait_for_response_frame(  # noqa: SLF001 - upstream lacks commit wait
            min(2.0, max(0.1, deadline - time.monotonic())),
            what_msg=f"committing {target}",
        )
        if response.is_ok():
            messages.append(response.ok_value.response)
    combined = " | ".join(message for message in messages if message)
    if expected not in combined:
        raise RuntimeError(f"firmware did not confirm {target}: {combined}")
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the WaveRider FWI splash on FreeWili 2")
    parser.add_argument("--port", required=True, help="Main serial port, such as /dev/cu.usbmodemFX01771")
    parser.add_argument("--asset", type=Path, help="upload one custom FWI asset")
    parser.add_argument("--target", help="custom Main-SD target for --asset")
    parser.add_argument("--show", action="store_true", help="show the image after upload")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    if args.asset is not None:
        assets = ((args.asset, args.target or f"1:/images/{args.asset.name}"),)
    else:
        assets = tuple((root / source, target) for source, target in DEFAULT_ASSETS)
    for asset, _target in assets:
        if not asset.is_file():
            raise SystemExit(f"UI asset not found: {asset}")

    device = FreeWiliSerial(args.port, stay_open=True)
    patch_fw2_file_menu(device)
    try:
        for asset, target in assets:
            result = device.send_file(asset, target, print)
            if result.is_err():
                raise SystemExit(result.err_value)
            committed = wait_for_commit(device, target, asset.stat().st_size, result.ok_value)
            print(committed)
        # Give the Display-side filesystem bridge one scheduling slice after
        # Main's final checksum/size confirmation before requesting a preview.
        time.sleep(0.5)
        if args.show:
            shown = device.show_gui_image(assets[0][1])
            if shown.is_err():
                raise SystemExit(shown.err_value)
            print(shown.ok_value)
    finally:
        device.close(restore_menu=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
