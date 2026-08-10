import hashlib
import re

import pytest

from tools import serial_put


class MarkerSerial:
    def __init__(self, exit_status):
        self.exit_status = exit_status
        self.marker = b""
        self.returned = False

    def write(self, value):
        match = re.search(rb"(__WAVERIDER_[0-9]+__)", value)
        assert match
        self.marker = match.group(1)

    def flush(self):
        pass

    def read(self, _size):
        if self.returned:
            return b""
        self.returned = True
        return b"diagnostic\r\n" + self.marker + f":{self.exit_status}\r\n".encode()


def test_command_reports_nonzero_marker_immediately():
    with pytest.raises(RuntimeError, match="exit status 1"):
        serial_put.command(MarkerSerial(1), "false", timeout=0.1)


def test_command_accepts_zero_marker():
    assert "diagnostic" in serial_put.command(MarkerSerial(0), "true", timeout=0.1)


def test_put_file_replaces_only_after_candidate_checksum(tmp_path, monkeypatch):
    source = tmp_path / "module.py"
    source.write_text("answer = 42\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    calls = []

    def fake_command(_port, value, **_kwargs):
        calls.append(value)
        if "sha256sum /opt/app/module.py.new" in value:
            return f"{digest}  /opt/app/module.py.new\n"
        return "ok"

    monkeypatch.setattr(serial_put, "command", fake_command)

    serial_put.put_file(object(), source, "/opt/app/module.py", chunk_size=8)

    assert calls[0] == "rm -f /opt/app/module.py.b64 /opt/app/module.py.new"
    assert all(call != "rm -f /opt/app/module.py.b64 /opt/app/module.py" for call in calls)
    assert calls[-1] == "mv -f /opt/app/module.py.new /opt/app/module.py"
