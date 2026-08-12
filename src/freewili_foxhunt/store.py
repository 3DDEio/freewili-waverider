"""Atomic JSON persistence for named frequency lists."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
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


@dataclass(slots=True)
class DecoderSettings:
    """Persistent opt-in controls for decoded-data processing."""

    cw_enabled: bool = True

    def to_dict(self) -> dict[str, bool | int]:
        return {
            "schema_version": 1,
            "cw_enabled": self.cw_enabled,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "DecoderSettings":
        if int(payload.get("schema_version", 1)) != 1:
            raise ValueError("unsupported decoder-settings schema")
        return cls(cw_enabled=bool(payload.get("cw_enabled", True)))


class DecoderSettingsStore:
    """Atomic persistence for the CW decoder toggle."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, settings: DecoderSettings) -> Path:
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

    def load(self) -> DecoderSettings:
        with self.path.open("r", encoding="utf-8") as handle:
            return DecoderSettings.from_dict(json.load(handle))

    def load_or_default(self) -> DecoderSettings:
        if self.path.exists():
            return self.load()
        settings = DecoderSettings()
        self.save(settings)
        return settings


@dataclass(slots=True)
class MessageRecord:
    """One durable CW message observation, coalesced across beacon repeats."""

    text: str
    frequency_hz: int
    first_seen_unix: float
    last_seen_unix: float
    repeat_count: int = 1
    confidence: float = 0.0
    variants: list[str] | None = None
    variant_counts: dict[str, int] | None = None
    evidence_count: int = 0
    agreement: float = 0.0
    verified: bool = False

    def validate(self) -> None:
        text = " ".join(self.text.upper().split())
        if not text or len(text) > 90:
            raise ValueError("message text must contain 1 to 90 characters")
        if not 24_000_000 <= self.frequency_hz <= 1_766_000_000:
            raise ValueError("message frequency is outside the RTL-SDR range")
        if self.first_seen_unix < 0 or self.last_seen_unix < self.first_seen_unix:
            raise ValueError("message timestamps are invalid")
        if self.repeat_count < 1:
            raise ValueError("message repeat count must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("message confidence must be between zero and one")
        if self.evidence_count < 0:
            raise ValueError("message evidence count cannot be negative")
        if not 0.0 <= self.agreement <= 1.0:
            raise ValueError("message agreement must be between zero and one")
        self.text = text
        variants = self.variants if self.variants is not None else [text]
        self.variants = list(
            dict.fromkeys(" ".join(value.upper().split())[:90] for value in variants)
        )[-8:]
        if text not in self.variants:
            self.variants.append(text)
            self.variants = self.variants[-8:]
        counts: dict[str, int] = {}
        for value, count in (self.variant_counts or {}).items():
            normalized = " ".join(value.upper().split())[:90]
            if normalized and int(count) > 0:
                counts[normalized] = counts.get(normalized, 0) + int(count)
        self.variant_counts = counts

    @property
    def display_confidence(self) -> float:
        """Quality shown to users combines decode quality and repeat agreement."""

        if not self.verified:
            return 0.0
        return min(self.confidence, self.agreement)

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "text": self.text,
            "frequency_hz": self.frequency_hz,
            "first_seen_unix": self.first_seen_unix,
            "last_seen_unix": self.last_seen_unix,
            "repeat_count": self.repeat_count,
            "confidence": self.confidence,
            "variants": self.variants,
            "variant_counts": self.variant_counts,
            "evidence_count": self.evidence_count,
            "agreement": self.agreement,
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "MessageRecord":
        record = cls(
            text=str(payload["text"]),
            frequency_hz=int(payload["frequency_hz"]),
            first_seen_unix=float(payload["first_seen_unix"]),
            last_seen_unix=float(payload["last_seen_unix"]),
            repeat_count=int(payload.get("repeat_count", 1)),
            confidence=float(payload.get("confidence", 0.0)),
            variants=[str(value) for value in payload.get("variants", [])],
            variant_counts={
                str(key): int(value)
                for key, value in dict(payload.get("variant_counts", {})).items()
            },
            evidence_count=int(payload.get("evidence_count", 0)),
            agreement=float(payload.get("agreement", 0.0)),
            verified=bool(payload.get("verified", False)),
        )
        record.validate()
        return record


class MessageStore:
    """Atomic, bounded CW history with conservative repeat coalescing."""

    MAX_RECORDS = 100
    SIMILARITY_THRESHOLD = 0.65
    CLUSTER_WINDOW_SECONDS = 600.0

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join(text.upper().split())

    @classmethod
    def _similar(cls, first: str, second: str) -> bool:
        first = cls._normalized(first)
        second = cls._normalized(second)
        if first == second:
            return True
        # Unknown symbols are decoder erasures, not meaningful content.  Drop
        # them only for clustering so independent receptions of one repeating
        # beacon can improve a stored record without merging unrelated text.
        first_known = first.replace("?", "")
        second_known = second.replace("?", "")
        if min(len(first_known), len(second_known)) < 4:
            return False
        length_ratio = min(len(first_known), len(second_known)) / max(
            len(first_known), len(second_known)
        )
        return (
            length_ratio >= 0.65
            and SequenceMatcher(None, first_known, second_known).ratio()
            >= cls.SIMILARITY_THRESHOLD
        )

    @staticmethod
    def _quality(text: str, confidence: float) -> tuple[float, int, int]:
        return (
            confidence,
            -text.count("?"),
            sum(character.isalnum() for character in text),
        )

    @staticmethod
    def _fill_erasures(first: str, second: str) -> str | None:
        """Combine aligned receptions only when every conflict is an erasure."""

        if len(first) != len(second):
            return None
        merged: list[str] = []
        for left, right in zip(first, second):
            if left == right:
                merged.append(left)
            elif left == "?":
                merged.append(right)
            elif right == "?":
                merged.append(left)
            else:
                return None
        return "".join(merged)

    @staticmethod
    def _consensus(variant_counts: dict[str, int], fallback: str) -> tuple[str, float]:
        """Return a weighted, aligned consensus and its reception agreement.

        Earlier builds deduplicated variants, so six matching receptions had
        the same vote as one noisy outlier.  Counts now preserve real evidence;
        the medoid reception supplies alignment and repeated positions vote in
        proportion to how often they were actually heard.
        """

        if not variant_counts:
            return fallback, 0.0
        references = list(variant_counts)
        reference = max(
            references,
            key=lambda candidate: sum(
                SequenceMatcher(None, candidate, other).ratio() * count
                for other, count in variant_counts.items()
            ),
        )
        votes: list[Counter[str]] = [
            Counter({character: variant_counts[reference]})
            if character != "?"
            else Counter()
            for character in reference
        ]
        for variant, weight in variant_counts.items():
            if variant == reference:
                continue
            matcher = SequenceMatcher(None, reference, variant)
            for tag, first_start, first_stop, second_start, second_stop in matcher.get_opcodes():
                if tag == "equal":
                    for offset in range(first_stop - first_start):
                        character = variant[second_start + offset]
                        if character != "?":
                            votes[first_start + offset][character] += weight
                elif tag == "replace" and first_stop - first_start == second_stop - second_start:
                    for offset in range(first_stop - first_start):
                        character = variant[second_start + offset]
                        if character != "?":
                            votes[first_start + offset][character] += weight
        result = list(reference)
        for index, counts in enumerate(votes):
            if not counts:
                continue
            replacement, support = counts.most_common(1)[0]
            reference_support = counts[result[index]]
            if support >= 2 and support > reference_support:
                result[index] = replacement
            elif result[index] == "?" and support >= 1:
                result[index] = replacement
        consensus = "".join(result)
        total = sum(variant_counts.values())
        agreement = sum(
            SequenceMatcher(None, consensus, variant).ratio() * count
            for variant, count in variant_counts.items()
        ) / max(1, total)
        return consensus, agreement

    def save(self, records: list[MessageRecord]) -> Path:
        records = sorted(records, key=lambda item: item.last_seen_unix)[
            -self.MAX_RECORDS :
        ]
        payload = json.dumps(
            {
                "schema_version": 2,
                "messages": [record.to_dict() for record in records],
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
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

    def load(self) -> list[MessageRecord]:
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if int(payload.get("schema_version", 1)) not in (1, 2):
            raise ValueError("unsupported message-history schema")
        records = [MessageRecord.from_dict(item) for item in payload["messages"]]
        return sorted(records, key=lambda item: item.last_seen_unix)[
            -self.MAX_RECORDS :
        ]

    def load_or_empty(self) -> list[MessageRecord]:
        if not self.path.exists():
            self.save([])
            return []
        return self.load()

    def clear(self, records: list[MessageRecord]) -> Path:
        """Clear in-memory and persisted message history atomically."""

        records.clear()
        return self.save(records)

    def observe(
        self,
        records: list[MessageRecord],
        *,
        text: str,
        frequency_hz: int,
        confidence: float,
        observed_unix: float,
    ) -> MessageRecord:
        normalized = self._normalized(text)[:90]
        matches = [
            record
            for record in records
            if record.frequency_hz == frequency_hz
            and observed_unix - record.last_seen_unix <= self.CLUSTER_WINDOW_SECONDS
            and self._similar(record.text, normalized)
        ]
        match = max(matches, key=lambda item: item.last_seen_unix, default=None)
        if match is None:
            match = MessageRecord(
                text=normalized,
                frequency_hz=frequency_hz,
                first_seen_unix=observed_unix,
                last_seen_unix=observed_unix,
                confidence=confidence,
                variants=[normalized],
                variant_counts={normalized: 1},
                evidence_count=1,
            )
            match.validate()
            records.append(match)
        else:
            assert match.variants is not None
            assert match.variant_counts is not None
            for other in matches:
                if other is match:
                    continue
                assert other.variants is not None
                match.variants.extend(other.variants)
                for variant, count in (other.variant_counts or {}).items():
                    match.variant_counts[variant] = (
                        match.variant_counts.get(variant, 0) + count
                    )
                match.repeat_count += other.repeat_count
                match.evidence_count += other.evidence_count
                match.first_seen_unix = min(
                    match.first_seen_unix, other.first_seen_unix
                )
                match.confidence = max(match.confidence, other.confidence)
                records.remove(other)
            if normalized not in match.variants:
                match.variants.append(normalized)
            match.variants = list(dict.fromkeys(match.variants))[-8:]
            match.variant_counts[normalized] = match.variant_counts.get(normalized, 0) + 1
            combined = self._fill_erasures(match.text, normalized)
            if combined is not None:
                match.text = combined
            elif self._quality(normalized, confidence) > self._quality(
                match.text, match.confidence
            ):
                match.text = normalized
            match.last_seen_unix = observed_unix
            match.repeat_count += 1
            match.evidence_count += 1
            match.confidence = max(match.confidence, confidence)
            match.text, match.agreement = self._consensus(
                match.variant_counts, match.text
            )
            match.verified = (
                match.evidence_count >= 3
                and match.confidence >= 0.82
                and match.agreement >= 0.72
            )
            match.validate()
        records.sort(key=lambda item: item.last_seen_unix)
        if len(records) > self.MAX_RECORDS:
            del records[: len(records) - self.MAX_RECORDS]
        self.save(records)
        return match


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
