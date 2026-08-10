from types import SimpleNamespace

import pytest

from freewili_foxhunt.cm0_transport import (
    RESET_QUIET,
    SocketCm0Transport,
    configured_batch_window,
)


def test_batch_window_defaults_to_safe_single_command(monkeypatch):
    monkeypatch.delenv("WAVERIDER_CM0_BATCH_WINDOW", raising=False)
    assert configured_batch_window() == 1


@pytest.mark.parametrize("value", ["0", "9", "not-a-number"])
def test_batch_window_rejects_unproven_or_invalid_values(monkeypatch, value):
    monkeypatch.setenv("WAVERIDER_CM0_BATCH_WINDOW", value)
    assert configured_batch_window() == 1


def test_batch_window_accepts_benchmarked_range(monkeypatch):
    monkeypatch.setenv("WAVERIDER_CM0_BATCH_WINDOW", "4")
    assert configured_batch_window() == 4


def test_call_batch_uses_bounded_windows_and_preserves_response_order():
    transport = SocketCm0Transport()
    transport._socket = object()
    writes = []
    transport._write = writes.append
    responses = iter(
        [
            SimpleNamespace(path="g\\e\\f", response="Ok", success=True),
            SimpleNamespace(path="g\\e\\f", response="Ok", success=True),
            SimpleNamespace(path="g\\e\\b", response="Ok", success=True),
        ]
    )
    transport._wait_frame_any = lambda _timeout: next(responses)

    result = transport.call_batch(
        ["g\\e\\f 0 0 3", "g\\e\\f 0 0 7", "g\\e\\b 7 1"],
        window=2,
    )

    assert [frame.path for frame in result] == ["g\\e\\f", "g\\e\\f", "g\\e\\b"]
    assert writes == [
        RESET_QUIET + b"g\\e\\f 0 0 3\n",
        RESET_QUIET + b"g\\e\\f 0 0 7\n",
        RESET_QUIET + b"g\\e\\b 7 1\n",
    ]


def test_call_batch_correlates_out_of_order_and_ignores_unrelated_frames():
    transport = SocketCm0Transport()
    transport._socket = object()
    transport._write = lambda _data: None
    responses = iter(
        [
            SimpleNamespace(path="h\\p", response="host traffic", success=True),
            SimpleNamespace(path="g\\e\\b", response="Ok", success=True),
            SimpleNamespace(path="g\\e\\f", response="Ok", success=True),
            SimpleNamespace(path="g\\e\\f", response="Ok", success=True),
        ]
    )
    transport._wait_frame_any = lambda _timeout: next(responses)

    result = transport.call_batch(
        ["g\\e\\f 0 0 3", "g\\e\\f 0 0 7", "g\\e\\b 7 1"],
        window=3,
    )

    assert [frame.path for frame in result] == ["g\\e\\f", "g\\e\\f", "g\\e\\b"]


def test_call_batch_raises_for_failed_matching_response():
    transport = SocketCm0Transport()
    transport._socket = object()
    transport._write = lambda _data: None
    transport._wait_frame_any = lambda _timeout: SimpleNamespace(
        path="g\\e\\b", response="Invalid", success=False
    )

    with pytest.raises(RuntimeError, match="Invalid"):
        transport.call_batch(["g\\e\\b 7 1"])


def test_call_batch_discards_stale_same_path_frame_before_write():
    transport = SocketCm0Transport()
    transport._socket = object()
    stale = SimpleNamespace(path="g\\e\\b", response="stale", success=True)
    fresh = SimpleNamespace(path="g\\e\\b", response="fresh", success=True)
    transport.frames.put(stale)

    def write(_data):
        transport.frames.put(fresh)

    transport._write = write

    assert transport.call_batch(["g\\e\\b 7 1"]) == [fresh]


def test_wait_frame_ignores_unrelated_path_after_send():
    transport = SocketCm0Transport()
    transport._socket = object()
    transport._write = lambda _data: None
    transport.send("g\\o 100")
    transport.frames.put(SimpleNamespace(path="h\\p", response="host", success=True))
    expected = SimpleNamespace(path="g\\o", response="Ok", success=True)
    transport.frames.put(expected)

    assert transport.wait_frame(0.1) is expected
    assert transport._expected_path is None


def test_wait_frame_timeout_clears_expected_path():
    transport = SocketCm0Transport()
    transport._socket = object()
    transport._write = lambda _data: None
    transport.send("g\\o 100")

    assert transport.wait_frame(0.0) is None
    assert transport._expected_path is None


def test_flush_queues_preserves_events_by_default():
    transport = SocketCm0Transport()
    transport.frames.put(object())
    transport.lines.put("stale")
    event = object()
    transport.events.put(event)

    transport.flush_queues()

    assert transport.frames.empty()
    assert transport.lines.empty()
    assert transport.events.get_nowait() is event


def test_flush_queues_clears_stale_expected_path():
    transport = SocketCm0Transport()
    transport._expected_path = "g\\o"

    transport.flush_queues()

    assert transport._expected_path is None
