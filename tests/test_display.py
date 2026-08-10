import queue
from types import SimpleNamespace
from unittest.mock import patch

from freewili_foxhunt.display import NativeSignalDisplay, OneWiliDisplay
from freewili_foxhunt.models import FrequencyEntry


class FakeProperties:
    def __init__(self) -> None:
        self.bins = []
        self.commits = []
        self.text = []

    def set_plot_data(self, plot_index, settings, value):
        self.bins.append((plot_index, settings, value))

    def set_control_value_int(self, control_index, value):
        self.commits.append((control_index, value))

    def set_control_value_text(self, control_index, value):
        self.text.append((control_index, value))


def test_center_marker_is_a_two_pixel_overlay_at_tuned_center():
    calls = []
    display = OneWiliDisplay()
    gui = SimpleNamespace(
        controls=SimpleNamespace(
            add_button=lambda *args: calls.append(args) or SimpleNamespace(is_err=lambda: False)
        )
    )

    display._add_center_marker(gui)

    assert calls == [
        (
            display.CONTROL_CENTER_MARKER,
            display.WATERFALL_X + display.WATERFALL_WIDTH // 2 - 1,
            display.WATERFALL_Y,
            2,
            display.WATERFALL_HEIGHT,
            "#DDF7FF",
            "#DDF7FF",
            "",
        )
    ]


def test_connect_enables_only_display_button_stream():
    calls = []

    class FakeTransport:
        pass

    transport = FakeTransport()

    class FakeGui:
        def _call(self, path, arguments, returns):
            calls.append(("gui", path, arguments, returns))
            return SimpleNamespace(is_err=lambda: False)

    class FakeOneWili:
        def __init__(self, transport):
            assert transport is globals_transport

        def open(self):
            return SimpleNamespace(gui=FakeGui())

    globals_transport = transport
    fake_encoding = SimpleNamespace(enc_int=lambda value: f"int:{value}")
    fake_onewili = SimpleNamespace(OneWili=FakeOneWili, encoding=fake_encoding)

    with (
        patch.dict(
            "sys.modules",
            {"onewili": fake_onewili, "onewili.encoding": fake_encoding},
        ),
        patch(
            "freewili_foxhunt.cm0_transport.SocketCm0Transport",
            return_value=transport,
        ),
    ):
        display = OneWiliDisplay()
        display.connect()

    assert calls == [
        (
            "gui",
            "o",
            [f"int:{OneWiliDisplay.BUTTON_STREAM_INTERVAL_MS}"],
            [],
        )
    ]


def test_waterfall_rows_are_committed_after_bins_are_staged():
    properties = FakeProperties()
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(control_properties=properties),
    )

    display.push_waterfall([3, 7, 11])
    display.push_waterfall([13])

    assert properties.bins == [
        (display.PLOT_INDEX, 0, 3),
        (display.PLOT_INDEX, 0, 7),
        (display.PLOT_INDEX, 0, 11),
        (display.PLOT_INDEX, 0, 13),
    ]
    assert properties.commits == [
        (display.CONTROL_WATERFALL, 1),
        (display.CONTROL_WATERFALL, 2),
    ]


def test_waterfall_uses_batched_cm0_transport_when_available():
    properties = FakeProperties()
    calls = []
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(control_properties=properties),
        _transport=SimpleNamespace(
            call_batch=lambda commands: calls.append(commands),
            events=queue.Queue(),
        ),
    )

    display.push_waterfall([3, 7, 11])

    assert calls == [[
        "g\\e\\f 0 0 3",
        "g\\e\\f 0 0 7",
        "g\\e\\f 0 0 11",
        "g\\e\\b 7 1",
    ]]
    assert properties.bins == []
    assert properties.commits == []


def test_live_text_pointer_and_waterfall_share_one_transport_batch():
    properties = FakeProperties()
    calls = []
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(control_properties=properties),
        _transport=SimpleNamespace(
            call_batch=lambda commands: calls.append(commands),
            events=queue.Queue(),
        ),
    )
    entry = SimpleNamespace(frequency_hz=147_495_000, span_hz=200_000)

    display.update_receiver(entry, -50.0, 1_000.0)
    display.push_waterfall([3, 7])

    assert len(calls) == 1
    assert "g\\e\\a 4 RSSI -50.0 dBFS" in calls[0]
    assert "g\\e\\a 9 -50.0" in calls[0]
    assert calls[0][-3:] == ["g\\e\\f 0 0 3", "g\\e\\f 0 0 7", "g\\e\\b 7 1"]


def test_button_event_accepts_generated_path_without_wire_prefix():
    events = queue.Queue()
    events.put(SimpleNamespace(path="button", response="0 0 1 0 0"))
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(read_all=lambda: None),
        _transport=SimpleNamespace(events=events),
    )

    assert display.poll_action() == "green"


def test_button_press_is_not_lost_when_release_is_already_queued():
    events = queue.Queue()
    events.put(SimpleNamespace(path="*button", response="0 0 1 0 0"))
    events.put(SimpleNamespace(path="*button", response="0 0 0 0 0"))
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(read_all=lambda: None),
        _transport=SimpleNamespace(events=events),
    )

    assert display.poll_action() == "green"
    assert display.poll_action() is None


def test_multiple_button_edges_are_preserved_in_wire_order():
    events = queue.Queue()
    events.put(SimpleNamespace(path="button", response="0 1 0 0 0"))
    events.put(SimpleNamespace(path="button", response="0 0 0 0 0"))
    events.put(SimpleNamespace(path="button", response="0 0 0 1 0"))
    events.put(SimpleNamespace(path="button", response="0 0 0 0 0"))
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(read_all=lambda: None),
        _transport=SimpleNamespace(events=events),
    )

    assert display.poll_action() == "yellow"
    assert display.poll_action() == "blue"
    assert display.poll_action() is None


def test_waterfall_commit_drains_press_and_release_without_losing_action():
    properties = FakeProperties()
    events = queue.Queue()
    events.put(SimpleNamespace(path="button", response="0 0 1 0 0"))
    events.put(SimpleNamespace(path="button", response="0 0 0 0 0"))
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(control_properties=properties),
        _transport=SimpleNamespace(
            call_batch=lambda commands: None,
            events=events,
        ),
    )

    display.push_waterfall([3, 7])

    assert display.poll_action() == "green"


def test_rssi_uses_moving_range_pointer_instead_of_progress_fill():
    properties = FakeProperties()
    display = OneWiliDisplay()
    display.device = SimpleNamespace(
        gui=SimpleNamespace(control_properties=properties),
    )
    entry = SimpleNamespace(frequency_hz=147_495_000, span_hz=200_000)

    display.update_receiver(entry, -90.0, 0.0)
    display.update_receiver(entry, -10.0, 1_000.0)

    assert (display.CONTROL_RSSI_VALUE, "-90.0") in properties.text
    assert (display.CONTROL_RSSI_VALUE, "-10.0") in properties.text
    marker_values = [
        value for control, value in properties.text if control == display.CONTROL_RSSI_MARKER
    ]
    assert marker_values[0].startswith("V")
    assert marker_values[-1].endswith("V")
    assert all(len(value) == display.RSSI_MARKER_STEPS for value in marker_values)
    assert all(set(value) <= {"-", "V"} for value in marker_values)
    assert all(control != display.CONTROL_RSSI_RANGE for control, _value in properties.commits)


class FakeSignalTransport:
    def __init__(self) -> None:
        self.commands = []
        self.batches = []
        self.last_command = ""
        self.command_value = 0.0
        self.new_frequency_khz = 0.0
        self.closed = False

    def open(self):
        pass

    def close(self):
        self.closed = True

    def send(self, command):
        self.last_command = command
        self.commands.append(command)

    def wait_frame(self, timeout=2.0):
        del timeout
        if self.last_command == "s\\i\\g wr_cmd":
            response = f"wr_cmd {self.command_value:.3f}"
        elif self.last_command == "s\\i\\g wr_state":
            response = f"wr_state {self.new_frequency_khz:.3f}"
        else:
            response = "Ok"
        return SimpleNamespace(success=True, response=response)

    def call_batch(self, commands, timeout=3.0):
        del timeout
        self.batches.append(list(commands))
        return [SimpleNamespace(success=True, response="Ok") for _ in commands]


def test_native_display_packs_twelve_bins_into_three_exact_signal_words():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()
    display.update_receiver(
        SimpleNamespace(frequency_hz=147_495_000, span_hz=100_000),
        -42.5,
        12_500.0,
    )

    display.push_waterfall([0, 7, 13, 20, 27, 33, 40, 47, 53, 67, 80, 100])

    frame = transport.batches[-1]
    assert len(frame) == 6
    assert frame[-1] == "s\\i\\s wr_seq 1.000"
    assert not any(" wr_freq " in command for command in frame)
    assert not any(" wr_span " in command for command in frame)
    assert not any(" wr_sel " in command for command in frame)
    assert any(command.startswith("s\\i\\s wr_row0 ") for command in frame)
    assert any(command.startswith("s\\i\\s wr_row1 ") for command in frame)
    assert any(command.startswith("s\\i\\s wr_row2 ") for command in frame)
    packed = [
        int(float(command.rsplit(" ", 1)[1]))
        for command in frame
        if " wr_row" in command
    ]
    assert len(packed) == 3
    assert all(0 <= value <= 0xFFFF for value in packed)


def test_native_display_publishes_tuning_state_only_when_it_changes():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()
    first = SimpleNamespace(frequency_hz=147_495_000, span_hz=100_000)
    second = SimpleNamespace(frequency_hz=147_545_000, span_hz=200_000)

    display.update_receiver(first, -60.0, 0.0)
    assert transport.batches[-1] == [
        "s\\i\\s wr_freq 147495000.000",
        "s\\i\\s wr_span 100000.000",
    ]
    batch_count = len(transport.batches)
    display.update_receiver(first, -59.0, 1_000.0)
    assert len(transport.batches) == batch_count

    display.update_receiver(second, -58.0, -1_000.0)
    assert transport.batches[-1] == [
        "s\\i\\s wr_freq 147545000.000",
        "s\\i\\s wr_span 200000.000",
    ]


def test_native_display_decodes_direct_button_and_list_selection_commands():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()

    transport.command_value = (1 << 8) | (3 << 4)
    display._next_command_poll = 0
    assert display.poll_action() == "green"
    assert transport.batches[-1] == ["s\\i\\s wr_ack 1.000"]

    transport.command_value = (2 << 8) | (6 << 4) | 7
    display._next_command_poll = 0
    assert display.poll_action() == "select:7"
    assert transport.batches[-1] == ["s\\i\\s wr_ack 2.000"]
    display._next_command_poll = 0
    assert display.poll_action() is None


def test_native_display_decodes_library_management_commands():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()

    expected = {
        7: "lists",
        8: "library_prev_page",
        9: "library_next_page",
        10: "library_toggle:4",
        11: "library_delete:4",
        12: "library_tune:4",
        13: "library_back",
    }
    sequence = 1
    for opcode, action in expected.items():
        transport.command_value = (sequence << 8) | (opcode << 4) | 4
        display._next_command_poll = 0
        assert display.poll_action() == action
        sequence += 1


def test_native_display_decodes_exact_frequency_add_command():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()
    transport.new_frequency_khz = 147_495
    transport.command_value = (1 << 8) | (1 << 4)

    display._next_command_poll = 0
    assert display.poll_action() == "add:147495000"
    assert transport.batches[-1] == ["s\\i\\s wr_ack 1.000"]


def test_native_display_publishes_frequency_list_before_list_commit():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()
    frequency_list = SimpleNamespace(
        frequencies=[
            SimpleNamespace(frequency_hz=147_420_000, span_hz=100_000),
            SimpleNamespace(frequency_hz=147_495_000, span_hz=100_000),
        ]
    )

    display.build(frequency_list, 1)

    commands = transport.batches[-1]
    # Low byte is the live count; high bits carry disabled/-50 dBFS Pocket
    # Alert settings without consuming a 33rd Main mailbox signal.
    assert f"s\\i\\s wr_count {(40 << 9) | 2}.000" in commands
    assert "s\\i\\s wr_sel 1.000" in commands
    assert "s\\i\\s wr_f0 147420000.000" in commands
    assert "s\\i\\s wr_f1 147495000.000" in commands
    assert commands[-1] == "s\\i\\s wr_lseq 1.000"


def test_native_display_packs_and_decodes_pocket_alert_settings():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()
    display.set_pocket_alert(True, -47)
    frequency_list = SimpleNamespace(
        frequencies=[SimpleNamespace(frequency_hz=147_495_000, span_hz=100_000)]
    )

    display.build(frequency_list, 0)

    assert f"s\\i\\s wr_count {(43 << 9) | (1 << 8) | 1}.000" in transport.batches[-1]

    transport.command_value = (1 << 8) | (14 << 4) | 1
    display._next_command_poll = 0
    assert display.poll_action() == "alert_enabled:1"
    transport.new_frequency_khz = 43
    transport.command_value = (2 << 8) | (15 << 4)
    display._next_command_poll = 0
    assert display.poll_action() == "alert_threshold:-47"


def test_native_display_publishes_paged_library_with_live_membership():
    transport = FakeSignalTransport()
    display = NativeSignalDisplay(lambda: transport)
    display.connect()
    entries = [
        FrequencyEntry(147_420_000, "Saved one"),
        FrequencyEntry(433_200_000, "Saved two"),
        FrequencyEntry(446_125_000, "Saved three"),
    ]
    display.set_footer("LIVE LIST UPDATED")

    display.build_library(
        entries,
        {433_200_000},
        live_count=11,
        total=23,
        offset=16,
        selected=1,
    )

    commands = transport.batches[-1]
    assert "s\\i\\s wr_state 2.000" in commands
    assert "s\\i\\s wr_freq 7.000" in commands
    assert "s\\i\\s wr_count 3.000" in commands
    assert "s\\i\\s wr_sel 1.000" in commands
    assert f"s\\i\\s wr_row0 {(11 << 16) | 2}.000" in commands
    assert "s\\i\\s wr_row1 23.000" in commands
    assert "s\\i\\s wr_row2 16.000" in commands
    assert "s\\i\\s wr_f0 147420.000" in commands
    assert "s\\i\\s wr_f1 433200.000" in commands
    assert commands[-1] == "s\\i\\s wr_lseq 1.000"
