from __future__ import annotations

import pytest
from pathlib import Path

from tools import fw2_detach_routed_shell, fw2_read_live_status


ROOT = Path(__file__).resolve().parent.parent


class FakePort:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def reset_input_buffer(self) -> None:
        return

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        return


def test_detach_uses_plain_exit_without_ctrl_c(monkeypatch) -> None:
    port = FakePort()
    monkeypatch.setattr(
        fw2_detach_routed_shell.serial,
        "Serial",
        lambda *_args, **_kwargs: port,
    )
    monkeypatch.setattr(
        fw2_detach_routed_shell,
        "read_until_quiet",
        lambda *_args, **_kwargs: b"",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["fw2_detach_routed_shell.py", "--port", "/dev/test"],
    )

    assert fw2_detach_routed_shell.main() == 0
    assert port.writes == [b"exit\r"]


def test_status_reader_detaches_when_initial_stty_fails(monkeypatch) -> None:
    port = FakePort()
    calls: list[str] = []
    monkeypatch.setattr(
        fw2_read_live_status.serial,
        "Serial",
        lambda *_args, **_kwargs: port,
    )
    monkeypatch.setattr(fw2_read_live_status, "open_shell", lambda _port: None)

    def shell_ok(_port, command, **_kwargs):
        calls.append(command)
        if command == "stty -echo":
            raise TimeoutError("stty failed")

    monkeypatch.setattr(fw2_read_live_status, "shell_ok", shell_ok)
    monkeypatch.setattr(
        fw2_read_live_status,
        "detach_shell",
        lambda _port: calls.append("detach"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["fw2_read_live_status.py", "--port", "/dev/test"],
    )

    with pytest.raises(TimeoutError, match="stty failed"):
        fw2_read_live_status.main()

    assert calls == ["stty -echo", "stty echo", "detach"]


def test_bridge_diagnostic_explicitly_detaches_routed_shell() -> None:
    source = (ROOT / "tools" / "fw2_bridge_diagnose.py").read_text()

    assert "detach_shell," in source
    assert "detach_shell(port)" in source
    try_offset = source.index("        try:\n", source.index("open_shell(port)"))
    stty_offset = source.index('shell_ok(port, "stty -echo")')
    assert try_offset < stty_offset
