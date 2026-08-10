#!/usr/bin/env python3
"""Measure repeated 12-bin Display rows through the installed CM0 bridge."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


for candidate in (
    Path("/opt/freewili-foxhunt/src"),
    Path("/opt/onewili/python"),
    Path("/opt/onewili/cm0/python"),
):
    if candidate.exists():
        sys.path.insert(0, str(candidate))

from freewili_foxhunt.cm0_transport import SocketCm0Transport  # noqa: E402
from freewili_foxhunt.display import OneWiliDisplay  # noqa: E402
from freewili_foxhunt.models import FrequencyEntry  # noqa: E402
from onewili import OneWili  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bins", type=int, default=12)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument(
        "--reuse-panel",
        action="store_true",
        help="stream into the persistent WaveRider panel instead of adding panel 0",
    )
    args = parser.parse_args()
    if min(args.bins, args.batch, args.rows) <= 0:
        parser.error("bins, batch, and rows must be positive")

    entry = FrequencyEntry(147_495_000, "Benchmark")
    display = OneWiliDisplay()
    bridge = SocketCm0Transport()
    display.device = OneWili(transport=bridge).open()
    print("STAGE connected", flush=True)
    if args.reuse_panel:
        print("STAGE persistent-panel", flush=True)
    else:
        gui = display.device.gui
        display._require(  # noqa: SLF001 - hardware benchmark fixture
            gui.panels.add_panel(False, 0, "#071014", False),
            "create benchmark panel",
        )
        display._require(display._add_waterfall(), "add benchmark waterfall")  # noqa: SLF001
        display._require(gui.panels.show_panel(0), "show benchmark panel")  # noqa: SLF001
        print("STAGE panel", flush=True)
    transport = display.device._transport
    original_batch = transport.call_batch
    transport.call_batch = lambda commands: original_batch(  # type: ignore[method-assign]
        commands,
        timeout=10.0,
        window=args.batch,
    )
    started = time.monotonic()
    try:
        for row in range(args.rows):
            display.update_receiver(entry, -55.0 + row, row * 100.0)
            display.push_waterfall(
                [(row * 17 + index * 7) % 101 for index in range(args.bins)]
            )
            print(f"STAGE row={row + 1}", flush=True)
    finally:
        display.close()
    elapsed = time.monotonic() - started
    print(
        f"PASS rows={args.rows} bins={args.bins} batch={args.batch} "
        f"elapsed={elapsed:.3f}s rows_per_second={args.rows / elapsed:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
