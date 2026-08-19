from __future__ import annotations

from collections import deque
import json
import queue
from types import SimpleNamespace

from freewili_foxhunt.app import FoxhuntApp
from freewili_foxhunt.models import FrequencyEntry, FrequencyList
from freewili_foxhunt.morse import DecodedMessage
from freewili_foxhunt.spectrum import SpectrumRow
from freewili_foxhunt.store import ListStore, MessageStore


class RuntimeDisplay:
    def __init__(self) -> None:
        self.actions = deque(["green"])
        self.selected = None
        self.rows = []
        self.receiver_frequency = None
        self.closed = False
        self.messages = []

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

    def show_message(self, text, confidence, **metadata):
        self.messages.append((text, confidence, metadata))

    def close(self):
        self.closed = True

    @property
    def snapshot(self):
        return SimpleNamespace(connected=True, message="panel active")


class RuntimeSdr:
    def __init__(self, row) -> None:
        self.rows = queue.Queue()
        self.rows.put(row)
        self.messages = queue.Queue()
        self.started = []
        self.closed = False

    def start(self, entry):
        self.started.append(entry.frequency_hz)

    def close(self):
        self.closed = True


def test_sdr_capture_starts_before_display_handshake(tmp_path):
    events = []

    class OrderedDisplay(RuntimeDisplay):
        def connect(self):
            events.append("display")

    class OrderedSdr(RuntimeSdr):
        def start(self, entry):
            events.append("sdr")
            super().start(entry)

    frequencies = FrequencyList(
        "Field", [FrequencyEntry(147_495_000, "Primary")]
    )
    row = SpectrumRow(
        low_hz=147_494_000,
        high_hz=147_496_000,
        bin_hz=1_000,
        samples=2_048,
        powers_dbfs=[-60.0, -30.0, -45.0],
    )
    app = FoxhuntApp(
        frequencies,
        tmp_path / "status.json",
        ListStore(tmp_path / "lists"),
        once=True,
        display=OrderedDisplay(),
        sdr=OrderedSdr(row),
    )

    assert app.run() == 0
    assert events[:2] == ["sdr", "display"]


def test_runtime_publishes_distinct_startup_milestones(tmp_path):
    class RecordingStatus:
        def __init__(self):
            self.items = []

        def write(self, **values):
            self.items.append(values)

    frequencies = FrequencyList(
        "Field", [FrequencyEntry(147_495_000, "Primary")]
    )
    row = SpectrumRow(
        low_hz=147_494_000,
        high_hz=147_496_000,
        bin_hz=1_000,
        samples=2_048,
        powers_dbfs=[-60.0, -30.0, -45.0],
    )
    app = FoxhuntApp(
        frequencies,
        tmp_path / "status.json",
        ListStore(tmp_path / "lists"),
        once=True,
        display=RuntimeDisplay(),
        sdr=RuntimeSdr(row),
    )
    status = RecordingStatus()
    app.status = status

    assert app.run() == 0
    assert [item["startup_stage"] for item in status.items] == [
        "receiver",
        "display",
        "first_row",
        "live",
    ]


def test_confirmed_message_clear_removes_candidates_and_runtime_summary(tmp_path):
    frequencies = FrequencyList(
        "Field", [FrequencyEntry(147_500_000, "Primary")]
    )
    store = MessageStore(tmp_path / "messages.json")
    records = []
    store.observe(
        records,
        text="UNVERIFIED CANDIDATE",
        frequency_hz=147_500_000,
        confidence=0.75,
        observed_unix=100.0,
    )
    app = FoxhuntApp(
        frequencies,
        tmp_path / "status.json",
        ListStore(tmp_path / "lists"),
        display=RuntimeDisplay(),
        sdr=SimpleNamespace(),
        message_store=store,
        message_records=records,
    )
    app.last_morse_message = "OLD VERIFIED MESSAGE"
    app.last_morse_confidence = 0.99
    app.last_morse_candidate = "UNVERIFIED CANDIDATE"
    app.last_morse_candidate_confidence = 0.75

    app._handle_action("messages_clear")

    assert records == []
    assert store.load() == []
    assert app.last_morse_message is None
    assert app.last_morse_confidence is None
    assert app.last_morse_candidate is None
    assert app.last_morse_candidate_confidence is None


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
    assert status["startup_stage"] == "live"
    assert status["selected"] == 1
    assert status["frequency_hz"] == 146_520_000
    assert status["waterfall_bins"] == 12
    assert status["waterfall_raw_min_dbfs"] == -49.3
    assert status["waterfall_raw_max_dbfs"] == -20.43
    assert status["waterfall_floor_dbfs"] < status["waterfall_ceiling_dbfs"]
    assert 0 <= status["waterfall_encoded_min"] <= status["waterfall_encoded_max"] <= 100
    assert status["waterfall_encoded_unique"] >= 2
    assert display.closed and sdr.closed


def test_decoded_morse_message_reaches_display_and_runtime_status(tmp_path):
    frequencies = FrequencyList(
        "Field", [FrequencyEntry(147_500_000, "Beacon")]
    )
    row = SpectrumRow(
        low_hz=147_499_000,
        high_hz=147_501_000,
        bin_hz=1_000,
        samples=2_048,
        powers_dbfs=[-60.0, -30.0, -45.0],
    )
    display = RuntimeDisplay()
    sdr = RuntimeSdr(row)
    sdr.messages.put(DecodedMessage("KO6FQY JOIN NORCALCYBER.IO! KO6FQY", 1.0))
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
    assert display.messages == [
        (
            "KO6FQY JOIN NORCALCYBER.IO! KO6FQY",
            1.0,
            {
                "frequency_hz": 147_500_000,
                "repeat_count": 1,
                "observed_unix": display.messages[0][2]["observed_unix"],
                "replay": False,
            },
        )
    ]
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["morse_message"] == "KO6FQY JOIN NORCALCYBER.IO! KO6FQY"
    assert status["morse_confidence"] == 1.0


def test_morse_history_persists_and_replays_after_display_reconnect(tmp_path):
    frequencies = FrequencyList(
        "Field", [FrequencyEntry(147_500_000, "Beacon")]
    )
    row = SpectrumRow(
        low_hz=147_499_000,
        high_hz=147_501_000,
        bin_hz=1_000,
        samples=2_048,
        powers_dbfs=[-60.0, -30.0, -45.0],
    )
    store = MessageStore(tmp_path / "messages.json")
    first_display = RuntimeDisplay()
    first_sdr = RuntimeSdr(row)
    for _ in range(3):
        first_sdr.messages.put(DecodedMessage("KO6FQY TEST", 0.9))
    first = FoxhuntApp(
        frequencies,
        tmp_path / "first-status.json",
        ListStore(tmp_path / "lists"),
        once=True,
        display=first_display,
        sdr=first_sdr,
        message_store=store,
        message_records=store.load_or_empty(),
    )

    assert first.run() == 0
    records = store.load()
    assert len(records) == 1
    assert records[0].frequency_hz == 147_500_000
    assert records[0].verified

    replay_display = RuntimeDisplay()
    replay_sdr = RuntimeSdr(row)
    replay = FoxhuntApp(
        frequencies,
        tmp_path / "replay-status.json",
        ListStore(tmp_path / "lists"),
        once=True,
        display=replay_display,
        sdr=replay_sdr,
        message_store=store,
        message_records=records,
    )

    assert replay.run() == 0
    assert replay_display.messages[0][0] == "KO6FQY TEST"
    assert replay_display.messages[0][2]["replay"] is True
    assert replay_display.messages[0][2]["frequency_hz"] == 147_500_000


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
