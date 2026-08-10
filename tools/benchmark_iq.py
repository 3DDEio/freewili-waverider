#!/usr/bin/env python3
"""Measure steady-state native RTL-SDR FFT row cadence."""

from __future__ import annotations

import argparse
import time

from freewili_foxhunt.models import FrequencyEntry
from freewili_foxhunt.rtl_iq import RtlIqStream


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=20)
    parser.add_argument("--frequency", type=float, default=147.495)
    parser.add_argument("--span", type=int, default=200_000)
    args = parser.parse_args()
    stream = RtlIqStream()
    entry = FrequencyEntry(round(args.frequency * 1_000_000), "benchmark", args.span)
    started = time.monotonic()
    stream.start(entry)
    try:
        for _ in range(args.rows):
            item = stream.rows.get(timeout=5.0)
            if isinstance(item, Exception):
                raise item
    finally:
        stream.close()
    elapsed = time.monotonic() - started
    print(f"rows={args.rows} elapsed={elapsed:.3f}s rows_per_second={args.rows/elapsed:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
