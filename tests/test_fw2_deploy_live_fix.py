import pytest

from tools.fw2_deploy_live_fix import (
    MODULES,
    has_shell_prompt,
    open_shell,
    parse_compact_status,
    parse_scalar_output,
    parse_status_chunk,
    parse_status,
    require_live_runtime,
)


def test_live_deploy_includes_runtime_status_permissions_fix():
    assert "status.py" in MODULES
    assert "spectrum.py" in MODULES


def live_status(**overrides):
    status = {
        "state": "live",
        "sdr_connected": True,
        "display_connected": True,
        "waterfall_row_rate_hz": 6.4,
    }
    status.update(overrides)
    return status


def test_parse_status_extracts_json_from_marker_wrapped_shell_output():
    output = (
        "cat /run/freewili-foxhunt/status.json\r\n"
        '{"display_connected": true, "state": "live"}\r\n'
        "__WAVERIDER_123__:0\r\n"
    )

    assert parse_status(output) == {"display_connected": True, "state": "live"}


def test_parse_compact_status_extracts_bounded_runtime_evidence():
    output = (
        "WRSTATUS|live|1|1|147495000|0|6.4|81.2|3\r\n"
        "__WAVERIDER_123__:0\r\n"
    )

    assert parse_compact_status(output) == {
        "state": "live",
        "sdr_connected": True,
        "display_connected": True,
        "frequency_hz": 147495000,
        "selected": 0,
        "waterfall_row_rate_hz": 6.4,
        "display_push_ms": 81.2,
        "sdr_queue_depth": 3,
    }


def test_parse_scalar_output_ignores_marker_and_colored_prompt():
    output = (
        "\r\n6.4\r\n__WAVERIDER_123__:0\r\n"
        "\x1b[01;32mpi@raspberrypi\x1b[00m:~ $\x1b[00m "
    )

    assert parse_scalar_output(output) == "6.4"


def test_parse_status_chunk_preserves_json_spaces():
    output = (
        "\r\nWRCHUNK|{\"display_message\": \"SDR LIVE\", \"state\": \"live\"}\r\n"
        "__WAVERIDER_123__:0\r\n"
    )

    assert parse_status_chunk(output) == (
        '{"display_message": "SDR LIVE", "state": "live"}'
    )


def test_live_runtime_requires_measured_field_cadence():
    require_live_runtime(live_status(), 3.0)

    with pytest.raises(RuntimeError, match="below the field cadence gate"):
        require_live_runtime(live_status(waterfall_row_rate_hz=1.2), 3.0)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"state": "error"}, "live SDR state"),
        ({"sdr_connected": False}, "live SDR state"),
        ({"display_connected": False}, "live display state"),
    ],
)
def test_live_runtime_requires_sdr_and_display(overrides, message):
    with pytest.raises(RuntimeError, match=message):
        require_live_runtime(live_status(**overrides), 3.0)


def test_open_shell_reuses_existing_routed_prompt_without_ctrl_c():
    class FakeSerial:
        def __init__(self):
            self.writes = []
            self.reads = iter([b"pi@freewili:~$ "])

        def reset_input_buffer(self):
            pass

        def write(self, value):
            self.writes.append(value)

        def flush(self):
            pass

        def read(self, _size):
            return next(self.reads, b"")

    port = FakeSerial()

    open_shell(port)

    assert port.writes == [b"\r"]


def test_open_shell_reuses_ansi_colored_prompt_without_ctrl_c():
    class FakeSerial:
        def __init__(self):
            self.writes = []
            self.reads = iter(
                [
                    b"\r\n\x1b[?2004h\x1b]0;pi@raspberrypi: ~\x07",
                    b"\x1b[01;32mpi@raspberrypi\x1b[00m:~ $\x1b[00m ",
                ]
            )

        def reset_input_buffer(self):
            pass

        def write(self, value):
            self.writes.append(value)

        def flush(self):
            pass

        def read(self, _size):
            return next(self.reads, b"")

    port = FakeSerial()

    open_shell(port)

    assert port.writes == [b"\r"]


def test_has_shell_prompt_rejects_regular_output():
    assert has_shell_prompt(b"active\r\n") is False
