from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from freewili_foxhunt.app import FoxhuntApp
from freewili_foxhunt.models import FrequencyEntry, FrequencyList
from freewili_foxhunt.store import (
    FrequencyLibraryStore,
    ListStore,
    PocketAlertSettings,
    PocketAlertStore,
)


class FakeDisplay:
    def __init__(self) -> None:
        self.built = 0
        self.footer = ""
        self.button_labels = None
        self.status = ""
        self.lists_built = 0
        self.list_selection = None
        self.library = None
        self.alert = None

    def build(self, *_args) -> None:
        self.built += 1

    def set_footer(self, value: str, *_args) -> None:
        self.footer = value

    def set_button_labels(self, value) -> None:
        self.button_labels = value

    def set_status(self, value: str) -> None:
        self.status = value

    def build_lists(self, *_args) -> None:
        self.lists_built += 1

    def update_list_selection(self, value: int) -> None:
        self.list_selection = value

    def build_library(self, *args) -> None:
        self.library = args

    def set_pocket_alert(self, enabled, threshold_dbfs) -> None:
        self.alert = (enabled, threshold_dbfs)


class FakeSdr:
    def __init__(self) -> None:
        self.started = []
        self.stopped = 0

    def start(self, entry) -> None:
        self.started.append(entry.frequency_hz)

    def stop(self) -> None:
        self.stopped += 1


class AppEditorTests(unittest.TestCase):
    def make_app(self, directory: str) -> FoxhuntApp:
        value = FrequencyList(
            "ARES",
            [
                FrequencyEntry(145_265_000, "Primary"),
                FrequencyEntry(146_565_000, "Secondary"),
            ],
        )
        return FoxhuntApp(
            value,
            Path(directory) / "status.json",
            ListStore(Path(directory) / "lists"),
            display=FakeDisplay(),
            sdr=FakeSdr(),
            library_store=FrequencyLibraryStore(
                Path(directory) / "frequency-library.json"
            ),
            alert_store=PocketAlertStore(Path(directory) / "pocket-alert.json"),
            alert_settings=PocketAlertSettings(),
        )

    def test_add_move_delete_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(directory)
            app._execute_editor_action("ADD +25K")
            self.assertEqual(len(app.frequency_list.frequencies), 3)
            self.assertEqual(app.entry.frequency_hz, 145_290_000)
            app._execute_editor_action("MOVE DOWN")
            self.assertEqual(app.selected, 2)
            app._execute_editor_action("DELETE")
            self.assertEqual(len(app.frequency_list.frequencies), 2)
            app._execute_editor_action("SAVE")
            self.assertFalse(app.dirty)
            self.assertTrue((Path(directory) / "lists" / "ares.json").exists())

    def test_span_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(directory)
            app._execute_editor_action("SPAN")
            self.assertEqual(app.entry.span_hz, 500_000)

    def test_live_button_actions_match_screen_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(directory)
            app._show_live()
            self.assertEqual(
                app.display.button_labels,
                ("LISTS", "MSGS", "NEXT", "PREV", "REFRESH"),
            )
            app._handle_action("gray")
            self.assertTrue(app.lists_mode)
            self.assertIsNotNone(app.display.library)
            self.assertEqual(len(app.frequency_list.frequencies), 2)
            app._handle_action("add:147495000")
            self.assertEqual(len(app.saved_frequencies), 3)
            self.assertEqual(len(app.frequency_list.frequencies), 2)
            self.assertTrue(
                (Path(directory) / "frequency-library.json").exists()
            )
            app._handle_action("library_toggle:2")
            self.assertEqual(len(app.frequency_list.frequencies), 3)
            self.assertEqual(app.frequency_list.frequencies[-1].frequency_hz, 147_495_000)
            app._handle_action("library_toggle:2")
            self.assertEqual(len(app.frequency_list.frequencies), 2)
            app._handle_action("library_back")
            self.assertFalse(app.lists_mode)
            app._handle_action("yellow")
            self.assertIn("MESSAGE HISTORY", app.display.footer)
            app._handle_action("green")
            self.assertEqual(app.pending_delta, 1)
            app._handle_action("blue")
            self.assertEqual(app.pending_delta, 0)
            starts = len(app.sdr.started)
            app._handle_action("red")
            self.assertEqual(len(app.sdr.started), starts + 1)
            self.assertEqual(app.display.status, "REFRESH")

    def test_pocket_alert_actions_persist_without_retuning_sdr(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(directory)
            starts = len(app.sdr.started)

            app._handle_action("alert_enabled:1")
            app._handle_action("alert_threshold:-47")

            settings = PocketAlertStore(
                Path(directory) / "pocket-alert.json"
            ).load()
            self.assertTrue(settings.enabled)
            self.assertEqual(settings.threshold_dbfs, -47)
            self.assertEqual(app.display.alert, (True, -47))
            self.assertEqual(len(app.sdr.started), starts)
            self.assertEqual(app.display.built, 0)

    def test_stop_and_start_buttons_control_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(directory)
            app._toggle_capture()
            self.assertTrue(app.capture_paused)
            self.assertEqual(app.sdr.stopped, 1)
            self.assertEqual(app.display.status, "PAUSED")
            app._toggle_capture()
            self.assertFalse(app.capture_paused)
            self.assertEqual(app.sdr.started[-1], app.entry.frequency_hz)

    def test_mark_button_persists_current_reading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(directory)
            app.last_rssi_dbfs = -42.5
            app.last_peak_offset_hz = 1_250.0
            app._mark_current_signal()
            mark_path = Path(directory) / "marks.jsonl"
            self.assertTrue(mark_path.exists())
            self.assertIn('"rssi_dbfs": -42.5', mark_path.read_text())


if __name__ == "__main__":
    unittest.main()
