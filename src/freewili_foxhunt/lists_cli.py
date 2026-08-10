"""Maintenance-console commands for creating and editing saved frequency lists."""

from __future__ import annotations

import argparse
from pathlib import Path

from .models import ALLOWED_SPANS_HZ, GAIN_PROFILES, FrequencyEntry, FrequencyList
from .store import ListStore, slugify


def _resolve(store: ListStore, value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate
    path = store.directory / f"{slugify(value)}.json"
    if not path.exists():
        raise SystemExit(f"frequency list not found: {value}")
    return path


def _frequency_hz(value: str) -> int:
    mhz = float(value)
    return int(round(mhz * 1_000_000))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage FreeWili Foxhunt frequency lists")
    parser.add_argument("--state-dir", default="/var/lib/freewili-foxhunt")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("show")

    create = commands.add_parser("create")
    create.add_argument("name")
    create.add_argument("frequency_mhz")
    create.add_argument("label")
    create.add_argument("--span", type=int, default=200_000, choices=ALLOWED_SPANS_HZ)
    create.add_argument("--gain", default="foxhunt", choices=GAIN_PROFILES)

    add = commands.add_parser("add")
    add.add_argument("list")
    add.add_argument("frequency_mhz")
    add.add_argument("label")
    add.add_argument("--span", type=int, default=200_000, choices=ALLOWED_SPANS_HZ)
    add.add_argument("--gain", default="foxhunt", choices=GAIN_PROFILES)

    delete = commands.add_parser("delete")
    delete.add_argument("list")
    delete.add_argument("index", type=int, help="1-based entry number")

    move = commands.add_parser("move")
    move.add_argument("list")
    move.add_argument("index", type=int, help="1-based entry number")
    move.add_argument("direction", choices=("up", "down"))

    rename = commands.add_parser("rename")
    rename.add_argument("list")
    rename.add_argument("name")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = ListStore(Path(args.state_dir) / "lists")
    if args.command == "show":
        for item in store.load_all():
            print(f"{item.name} ({len(item.frequencies)} frequencies)")
            for index, entry in enumerate(item.frequencies, 1):
                print(
                    f"  {index:>2}. {entry.frequency_hz / 1_000_000:.6f} MHz  "
                    f"{entry.label}  span={entry.span_hz} gain={entry.gain_profile}"
                )
        return 0

    if args.command == "create":
        entry = FrequencyEntry(
            _frequency_hz(args.frequency_mhz), args.label, args.span, args.gain
        )
        saved = store.save(FrequencyList(name=args.name, frequencies=[entry]))
        print(saved)
        return 0

    path = _resolve(store, args.list)
    value = store.load(path)
    if args.command == "add":
        value.frequencies.append(
            FrequencyEntry(_frequency_hz(args.frequency_mhz), args.label, args.span, args.gain)
        )
    elif args.command == "delete":
        if len(value.frequencies) == 1:
            raise SystemExit("cannot delete the only entry in a frequency list")
        if args.index not in range(1, len(value.frequencies) + 1):
            raise SystemExit(f"entry index out of range: {args.index}")
        try:
            del value.frequencies[args.index - 1]
        except IndexError as error:
            raise SystemExit(f"entry index out of range: {args.index}") from error
    elif args.command == "move":
        source = args.index - 1
        target = source + (-1 if args.direction == "up" else 1)
        if source not in range(len(value.frequencies)) or target not in range(len(value.frequencies)):
            raise SystemExit("entry cannot move farther in that direction")
        value.frequencies[source], value.frequencies[target] = (
            value.frequencies[target],
            value.frequencies[source],
        )
    elif args.command == "rename":
        value.name = args.name

    saved = store.save(value)
    if args.command == "rename" and saved != path and path.parent == store.directory:
        path.unlink()
    print(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
