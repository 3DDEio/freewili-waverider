from __future__ import annotations

from collections import deque
import json
import queue
from types import SimpleNamespace

from freewili_foxhunt.app import FoxhuntApp
from freewili_foxhunt.models import FrequencyEntry, FrequencyList
from freewili_foxhunt.spectrum import SpectrumRow
from freewili_foxhunt.store import ListStore


class RuntimeDisplay:
    def __init__(self) -> None:
        self.actions = deque(["green"])
        self.selected = None
        self.rows = []
        self.receiver_frequency = None
        self.closed = False

    def connect(self):
        pass

    def show_splash(self, _duration):
        pass

    def build(self, *_args):
        pass

    def poll_action(self):
        return self.actions.popleft() if self.actions else None

    def update_selection(self, selected):
        self.selected = selected

    def update_receiver(self, entry, _rssi, _offset):
        self.receiver_frequency = entry.frequency_hz

    def push_waterfall(self, bins):
        self.rows.append(bins)

    def close(self):
        self.closed = True

    @property
    def snapshot(self):
        return SimpleNamespace(connected=True, message="panel active")


class RuntimeSdr:
    def __init__(self, row) -> None:
        self.rows = queue.Queue()
        self.rows.put(row)
        self.started = []
        self.closed = False

    def start(self, entry):
        self.started.append(entry.frequency_hz)

    def close(self):
        self.closed = True


def test_green_press_retunes_before_next_waterfall_and_status_snapshot(tmp_path):
    frequencies = FrequencyList(
        "Field",
        [
            FrequencyEntry(145_265_000, "Primary"),
            FrequencyEntry(146_520_000, "Secondary"),
        ],
    )
    row = SpectrumRow(
        low_hz=146_519_000,
        high_hz=146_520_000,
        bin_hz=1_000,
        samples=2_048,
        powers_dbfs=[-50.0, -20.0],
    )
    display = RuntimeDisplay()
    sdr = RuntimeSdr(row)
    status_path = tmp_path / "status.json"
    app = FoxhuntApp(
        frequencies,
        status_path,
        ListStore(tmp_path / "lists"),
        once=True,
        display=display,
        sdr=sdr,
    )

    assert app.run() == 0

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert sdr.started == [145_265_000, 146_520_000]
    assert display.selected == 1
    assert display.receiver_frequency == 146_520_000
    assert len(display.rows) == 1
    assert status["state"] == "live"
    assert status["selected"] == 1
    assert status["frequency_hz"] == 146_520_000
    assert status["waterfall_bins"] == 12
    assert status["waterfall_raw_min_dbfs"] == -49.3
    assert status["waterfall_raw_max_dbfs"] == -20.43
    assert status["waterfall_floor_dbfs"] < status["waterfall_ceiling_dbfs"]
    assert 0 <= status["waterfall_encoded_min"] <= status["waterfall_encoded_max"] <= 100
    assert status["waterfall_encoded_unique"] >= 2
    assert display.closed and sdr.closed


def test_native_select_command_retunes_to_requested_list_index(tmp_path):
    frequencies = FrequencyList(
        "Field",
        [
            FrequencyEntry(145_265_000, "One"),
            FrequencyEntry(146_520_000, "Two"),
            FrequencyEntry(147_495_000, "Three"),
        ],
    )
    row = SpectrumRow(
        low_hz=147_494_000,
        high_hz=147_496_000,
        bin_hz=1_000,
        samples=2_048,
        powers_dbfs=[-60.0, -30.0, -45.0],
    )
    display = RuntimeDisplay()
    display.actions = deque(["select:2"])
    sdr = RuntimeSdr(row)
    app = FoxhuntApp(
        frequencies,
        tmp_path / "status.json",
        ListStore(tmp_path / "lists"),
        once=True,
        display=display,
        sdr=sdr,
    )

    assert app.run() == 0
    assert sdr.started == [145_265_000, 147_495_000]
    assert display.selected == 2
    assert display.receiver_frequency == 147_495_000
