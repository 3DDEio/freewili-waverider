from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from freewili_foxhunt.lists_cli import _frequency_hz, _resolve
from freewili_foxhunt.models import FrequencyEntry, FrequencyList
from freewili_foxhunt.store import ListStore


class ListCliTests(unittest.TestCase):
    def test_frequency_is_stored_as_integer_hz(self) -> None:
        self.assertEqual(_frequency_hz("145.265"), 145_265_000)

    def test_resolve_accepts_saved_list_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ListStore(Path(directory) / "lists")
            expected = store.save(
                FrequencyList("ARES Field Day", [FrequencyEntry(145_265_000, "Fox")])
            )
            self.assertEqual(_resolve(store, "ARES Field Day"), expected)


if __name__ == "__main__":
    unittest.main()
