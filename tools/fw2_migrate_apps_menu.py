#!/usr/bin/env python3
"""Install WaveRider under its friendly menu name and clean one empty legacy category."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UF2 = ROOT / "native" / "dist" / "WaveRider.uf2"
LEGACY_CATEGORY = "waverider"
OLD_RADIO_FILE = "waverider_display.uf2"


def migrate_volume(volume: Path, source: Path) -> dict[str, object]:
    """Perform a narrow, locally mounted Main-SD migration."""

    apps = volume / "apps"
    radio = apps / "Radio"
    legacy = apps / LEGACY_CATEGORY
    destination = radio / source.name

    if not apps.is_dir():
        raise RuntimeError(f"selected volume has no apps directory: {apps}")
    radio.mkdir(parents=True, exist_ok=True)

    temporary = radio / (source.name + ".tmp")
    shutil.copyfile(source, temporary)
    with temporary.open("r+b") as copied:
        os.fsync(copied.fileno())
    os.replace(temporary, destination)

    old_radio = radio / OLD_RADIO_FILE
    removed_old = False
    if old_radio.exists():
        if not old_radio.is_file():
            raise RuntimeError(f"refusing to remove non-file legacy path: {old_radio}")
        old_radio.unlink()
        removed_old = True

    removed_category = False
    if legacy.exists():
        if not legacy.is_dir():
            raise RuntimeError(f"refusing to remove non-directory legacy path: {legacy}")
        entries = list(legacy.iterdir())
        if entries:
            names = ", ".join(sorted(entry.name for entry in entries))
            raise RuntimeError(
                f"legacy category is not empty; left untouched ({names})"
            )
        legacy.rmdir()
        removed_category = True

    return {
        "destination": destination,
        "removed_old_radio_file": removed_old,
        "removed_empty_legacy_category": removed_category,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rename the connected FreeWili WaveRider Apps-menu entry safely"
    )
    parser.add_argument("--port", required=True, help="FreeWili Main command port")
    parser.add_argument("--uf2", type=Path, default=DEFAULT_UF2)
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()

    source = args.uf2.resolve()
    if not source.is_file() or source.name != "WaveRider.uf2":
        raise RuntimeError("the migration source must be the WaveRider.uf2 release app")

    sys.path.insert(0, str(ROOT / "wilibsp" / "tools"))
    import fw

    target = fw.check_app_uf2(source)
    baseline = fw._mounted_volumes()
    pc_selected = False
    try:
        fw._set_sd_host(args.port, True)
        pc_selected = True
        time.sleep(fw.SD_HANDOFF_SETTLE_SECONDS)
        volume = fw._wait_for_sd(baseline, args.timeout)
        result = migrate_volume(volume, source)
        time.sleep(fw.SD_HANDOFF_SETTLE_SECONDS)
    finally:
        if pc_selected:
            fw._set_sd_host(args.port, False)

    print(f"verified {source.name}: {target} app, no QSPI-flash payloads")
    print(f"installed {result['destination']}")
    print(f"removed old Radio filename: {result['removed_old_radio_file']}")
    print(f"removed empty /apps/{LEGACY_CATEGORY}: {result['removed_empty_legacy_category']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
