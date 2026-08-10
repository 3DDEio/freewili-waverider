from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from freewili_foxhunt.models import FrequencyEntry, FrequencyList
from freewili_foxhunt.store import ListStore, slugify


class ModelTests(unittest.TestCase):
    def sample(self) -> FrequencyList:
        return FrequencyList(
            name="ARES Field Day",
            frequencies=[FrequencyEntry(145_265_000, "Primary fox")],
        )

    def test_round_trip(self) -> None:
        original = self.sample()
        restored = FrequencyList.from_dict(original.to_dict())
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.frequencies[0].frequency_hz, 145_265_000)

    def test_rejects_frequency_outside_receiver_range(self) -> None:
        with self.assertRaises(ValueError):
            FrequencyEntry(1_000_000, "Too low").validate()

    def test_atomic_store_keeps_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ListStore(directory)
            value = self.sample()
            destination = store.save(value)
            value.frequencies[0].label = "Updated"
            store.save(value)
            backup = destination.with_suffix(".json.bak")
            self.assertTrue(backup.exists())
            self.assertEqual(json.loads(backup.read_text())["frequencies"][0]["label"], "Primary fox")

    def test_save_preserves_ordered_source_path_and_archives_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ListStore(directory)
            value = self.sample()
            ordered = Path(directory) / "00-ares-field-day.json"
            ordered.write_text(json.dumps(value.to_dict()), encoding="utf-8")
            duplicate = Path(directory) / "ares-field-day.json"
            duplicate.write_text(json.dumps(value.to_dict()), encoding="utf-8")

            value.frequencies.append(FrequencyEntry(433_200_000, "Saved fox"))
            destination = store.save(value)

            self.assertEqual(destination, ordered)
            self.assertEqual(
                len(json.loads(ordered.read_text())["frequencies"]),
                2,
            )
            self.assertFalse(duplicate.exists())
            self.assertTrue(Path(f"{duplicate}.duplicate").exists())

    def test_slugify(self) -> None:
        self.assertEqual(slugify("  70cm / Foxes  "), "70cm-foxes")


if __name__ == "__main__":
    unittest.main()
