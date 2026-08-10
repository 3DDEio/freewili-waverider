"""Atomic JSON persistence for named frequency lists."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .models import FrequencyEntry, FrequencyList


SAFE_NAME = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class PocketAlertSettings:
    """Persistent, battery-conscious haptic alert preferences."""

    enabled: bool = False
    threshold_dbfs: int = -50
    cooldown_seconds: int = 30

    def validate(self) -> None:
        if not -70 <= self.threshold_dbfs <= -10:
            raise ValueError("pocket-alert threshold must be between -70 and -10 dBFS")
        if self.cooldown_seconds != 30:
            raise ValueError("pocket-alert cooldown must be 30 seconds")

    def to_dict(self) -> dict[str, bool | int]:
        self.validate()
        return {
            "schema_version": 1,
            "enabled": self.enabled,
            "threshold_dbfs": self.threshold_dbfs,
            "cooldown_seconds": self.cooldown_seconds,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "PocketAlertSettings":
        if int(payload.get("schema_version", 1)) != 1:
            raise ValueError("unsupported pocket-alert schema")
        settings = cls(
            enabled=bool(payload.get("enabled", False)),
            threshold_dbfs=int(payload.get("threshold_dbfs", -50)),
            cooldown_seconds=int(payload.get("cooldown_seconds", 30)),
        )
        settings.validate()
        return settings


class PocketAlertStore:
    """Atomic persistence for the opt-in Pocket Alert feature."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, settings: PocketAlertSettings) -> Path:
        payload = json.dumps(settings.to_dict(), indent=2, sort_keys=True) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return self.path

    def load(self) -> PocketAlertSettings:
        with self.path.open("r", encoding="utf-8") as handle:
            return PocketAlertSettings.from_dict(json.load(handle))

    def load_or_default(self) -> PocketAlertSettings:
        if self.path.exists():
            return self.load()
        settings = PocketAlertSettings()
        self.save(settings)
        return settings


def slugify(name: str) -> str:
    slug = SAFE_NAME.sub("-", name.casefold()).strip("-")
    return slug or "untitled"


class ListStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def path_for(self, frequency_list: FrequencyList) -> Path:
        return self.directory / f"{slugify(frequency_list.name)}.json"

    def _paths_for_id(self, list_id: str) -> list[Path]:
        if not self.directory.exists():
            return []
        matches: list[Path] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            if str(payload.get("id", "")) == list_id:
                matches.append(path)
        return matches

    def save(self, frequency_list: FrequencyList) -> Path:
        frequency_list.validate()
        self.directory.mkdir(parents=True, exist_ok=True)
        matching_paths = self._paths_for_id(frequency_list.id)
        # Lists installed with an ordering prefix (for example `00-`) must be
        # updated in place. Saving only to the name-derived slug creates a
        # second list, and the older prefixed file wins again after reboot.
        destination = matching_paths[0] if matching_paths else self.path_for(frequency_list)
        backup = destination.with_suffix(".json.bak")
        if destination.exists():
            shutil.copy2(destination, backup)

        payload = json.dumps(frequency_list.to_dict(), indent=2, sort_keys=True) + "\n"
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=self.directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
            # Older WaveRider builds could already have created an unprefixed
            # duplicate with the same stable list ID. Remove it from the load
            # set without destroying it so the ordered original remains the
            # single source of truth on the next boot.
            for duplicate in matching_paths[1:]:
                archive = duplicate.with_suffix(duplicate.suffix + ".duplicate")
                os.replace(duplicate, archive)
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return destination

    def load(self, path: str | Path) -> FrequencyList:
        with Path(path).open("r", encoding="utf-8") as handle:
            return FrequencyList.from_dict(json.load(handle))

    def load_all(self) -> list[FrequencyList]:
        if not self.directory.exists():
            return []
        return [self.load(path) for path in sorted(self.directory.glob("*.json"))]


class FrequencyLibraryStore:
    """Atomic persistence for the device-wide saved-frequency library."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, entries: list[FrequencyEntry]) -> Path:
        if len(entries) > 100:
            raise ValueError("the saved-frequency library cannot exceed 100 entries")
        seen: set[int] = set()
        for entry in entries:
            entry.validate()
            if entry.frequency_hz in seen:
                raise ValueError("the saved-frequency library cannot contain duplicates")
            seen.add(entry.frequency_hz)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "schema_version": 1,
                "frequencies": [entry.to_dict() for entry in entries],
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return self.path

    def load(self) -> list[FrequencyEntry]:
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if int(payload.get("schema_version", 1)) != 1:
            raise ValueError("unsupported frequency-library schema")
        entries = [FrequencyEntry.from_dict(item) for item in payload["frequencies"]]
        if len(entries) > 100:
            raise ValueError("the saved-frequency library cannot exceed 100 entries")
        if len({entry.frequency_hz for entry in entries}) != len(entries):
            raise ValueError("the saved-frequency library cannot contain duplicates")
        return entries

    def load_or_seed(self, frequency_lists: list[FrequencyList]) -> list[FrequencyEntry]:
        if self.path.exists():
            entries = self.load()
        else:
            entries = []
        seen = {entry.frequency_hz for entry in entries}
        changed = not self.path.exists()
        for frequency_list in frequency_lists:
            for entry in frequency_list.frequencies:
                if entry.frequency_hz in seen:
                    continue
                if len(entries) >= 100:
                    break
                entries.append(FrequencyEntry.from_dict(entry.to_dict()))
                seen.add(entry.frequency_hz)
                changed = True
        if changed:
            self.save(entries)
        return entries
