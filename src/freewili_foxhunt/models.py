"""Versioned, validated frequency-list model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


MIN_FREQUENCY_HZ = 24_000_000
MAX_FREQUENCY_HZ = 1_766_000_000
ALLOWED_SPANS_HZ = (25_000, 100_000, 200_000, 500_000, 1_000_000, 2_000_000)
GAIN_PROFILES = ("auto", "foxhunt", "close-in", "manual")


def _identifier() -> str:
    return str(uuid4())


def _clean_name(value: Any, field_name: str, maximum: int) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    if len(text) > maximum:
        raise ValueError(f"{field_name} cannot exceed {maximum} characters")
    return text


@dataclass(slots=True)
class FrequencyEntry:
    frequency_hz: int
    label: str
    span_hz: int = 200_000
    gain_profile: str = "foxhunt"
    id: str = field(default_factory=_identifier)

    def validate(self) -> None:
        if not MIN_FREQUENCY_HZ <= self.frequency_hz <= MAX_FREQUENCY_HZ:
            raise ValueError(
                f"frequency_hz must be between {MIN_FREQUENCY_HZ} and {MAX_FREQUENCY_HZ}"
            )
        self.label = _clean_name(self.label, "label", 40)
        if self.span_hz not in ALLOWED_SPANS_HZ:
            raise ValueError(f"span_hz must be one of {ALLOWED_SPANS_HZ}")
        if self.gain_profile not in GAIN_PROFILES:
            raise ValueError(f"gain_profile must be one of {GAIN_PROFILES}")
        self.id = _clean_name(self.id, "id", 64)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FrequencyEntry":
        entry = cls(
            id=str(value.get("id") or _identifier()),
            frequency_hz=int(value["frequency_hz"]),
            label=str(value["label"]),
            span_hz=int(value.get("span_hz", 200_000)),
            gain_profile=str(value.get("gain_profile", "foxhunt")),
        )
        entry.validate()
        return entry

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "frequency_hz": self.frequency_hz,
            "label": self.label,
            "span_hz": self.span_hz,
            "gain_profile": self.gain_profile,
        }


@dataclass(slots=True)
class FrequencyList:
    name: str
    frequencies: list[FrequencyEntry]
    id: str = field(default_factory=_identifier)
    schema_version: int = 1
    palette: str = "deep-blue-orange"
    floor_dbfs: float = -90.0
    ceiling_dbfs: float = -30.0

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        self.name = _clean_name(self.name, "name", 40)
        self.id = _clean_name(self.id, "id", 64)
        if not self.frequencies:
            raise ValueError("a frequency list must contain at least one entry")
        if len(self.frequencies) > 100:
            raise ValueError("a frequency list cannot contain more than 100 entries")
        for entry in self.frequencies:
            entry.validate()
        if self.floor_dbfs >= self.ceiling_dbfs:
            raise ValueError("floor_dbfs must be below ceiling_dbfs")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FrequencyList":
        defaults = value.get("defaults") or {}
        result = cls(
            schema_version=int(value.get("schema_version", 1)),
            id=str(value.get("id") or _identifier()),
            name=str(value["name"]),
            frequencies=[FrequencyEntry.from_dict(item) for item in value["frequencies"]],
            palette=str(defaults.get("palette", "deep-blue-orange")),
            floor_dbfs=float(defaults.get("floor_dbfs", -90.0)),
            ceiling_dbfs=float(defaults.get("ceiling_dbfs", -30.0)),
        )
        result.validate()
        return result

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "defaults": {
                "palette": self.palette,
                "floor_dbfs": self.floor_dbfs,
                "ceiling_dbfs": self.ceiling_dbfs,
            },
            "frequencies": [entry.to_dict() for entry in self.frequencies],
        }
