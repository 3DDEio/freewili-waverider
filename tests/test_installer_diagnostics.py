from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import installer.device_install as device_install
import installer.diagnostics as diagnostics


def test_redaction_hides_home_path_and_decoded_cw_text():
    source = (
        f"file={Path.home()}/private.txt\n"
        "decoded Morse candidate confidence=0.90 text='KO6FQY SECRET MESSAGE'\n"
    )

    redacted = diagnostics.redact_text(source)

    assert str(Path.home()) not in redacted
    assert "KO6FQY SECRET MESSAGE" not in redacted
    assert "text=<redacted>" in redacted


def test_redaction_removes_the_remainder_of_a_cw_log_line():
    redacted = diagnostics.redact_text(
        "decoded Morse candidate text=\"CALL'S PRIVATE TEXT\" trailing=secret\n"
        "startup stage=receiver state=started\n"
    )

    assert "CALL'S PRIVATE TEXT" not in redacted
    assert "trailing=secret" not in redacted
    assert "startup stage=receiver state=started" in redacted


def test_sanitized_status_omits_messages_and_frequency_lists():
    status = diagnostics.sanitize_status(
        {
            "state": "starting",
            "startup_stage": "display",
            "frequency_hz": 147_500_000,
            "morse_message": "DO NOT EXPORT",
            "morse_candidate": "DO NOT EXPORT EITHER",
            "list_name": "Private hunt",
            "selected": 4,
        }
    )

    assert status == {
        "state": "starting",
        "startup_stage": "display",
        "frequency_hz": 147_500_000,
    }


def test_session_log_is_written_and_rotated(tmp_path):
    for index in range(12):
        (tmp_path / f"installer-20260101T0000{index:02d}Z-1.log").write_text("old\n")

    session = diagnostics.SessionLog(tmp_path, keep=3)
    session.write("TEST", "hello")

    logs = list(tmp_path.glob("installer-*.log"))
    assert len(logs) == 3
    assert "WaveRider installer session started" in session.path.read_text()
    assert "TEST" in session.path.read_text()
    assert "hello" in session.path.read_text()


def test_host_inventory_identifies_selected_freewili_main_port(monkeypatch):
    monkeypatch.setattr(
        diagnostics.list_ports,
        "comports",
        lambda: [
            SimpleNamespace(
                device="COM11",
                description="FreeWili Main",
                manufacturer="FreeWili",
                product="Main",
                interface="CDC",
                vid=0x1209,
                pid=0x0001,
            ),
            SimpleNamespace(
                device="COM12",
                description="Other serial",
                manufacturer="Other",
                product="Other",
                interface="CDC",
                vid=0x1234,
                pid=0x5678,
            ),
        ],
    )
    monkeypatch.setattr(
        device_install,
        "find_main_ports",
        lambda: [("FreeWili FX0000 — COM11", "COM11")],
    )

    inventory = diagnostics.host_serial_inventory("COM11")

    assert inventory["selected_is_freewili_main"] is True
    assert inventory["freewili_main_candidates"] == ["COM11"]
    assert inventory["serial_ports"][0]["selected"] is True
    assert inventory["serial_ports"][1]["selected"] is False


def test_main_route_probe_distinguishes_read_only_main_ack():
    class FakePort:
        def __init__(self):
            self.writes = []
            self.responses = [b"[h\\t 2026 8 18 1]"]

        def reset_input_buffer(self):
            return None

        def write(self, value):
            self.writes.append(value)

        def flush(self):
            return None

        def read(self, _size):
            return self.responses.pop(0) if self.responses else b""

    port = FakePort()
    report = diagnostics.probe_main_route(
        port, prompt_timeout=0.0, command_timeout=0.1
    )

    assert "ROUTE_STATE=main-parser-responsive" in report
    assert "MAIN_RTC_ACK=yes" in report
    assert port.writes == [b"\r", b"\x02h\\t\n"]


def test_remote_collection_detaches_after_query_failure(monkeypatch):
    calls: list[str] = []

    class FakeSerial:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append("serial-close")

    monkeypatch.setattr(diagnostics.serial, "Serial", lambda *_args, **_kwargs: FakeSerial())
    monkeypatch.setattr(diagnostics, "open_shell", lambda _port: calls.append("open"))
    monkeypatch.setattr(
        diagnostics, "probe_main_route", lambda _port: "ROUTE_STATE=test\n"
    )
    monkeypatch.setattr(diagnostics, "shell_ok", lambda _port, command, **_kwargs: calls.append(command))
    monkeypatch.setattr(
        diagnostics,
        "_remote_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("query failed")),
    )
    monkeypatch.setattr(
        diagnostics,
        "read_remote_line_file",
        lambda *_args, **_kwargs: json.dumps({"state": "starting"}),
    )
    monkeypatch.setattr(diagnostics, "detach_shell", lambda _port: calls.append("detach"))

    reports, warnings, opened = diagnostics.collect_remote_diagnostics("/dev/fake")

    assert reports["runtime-status.json"].strip().startswith("{")
    assert len(warnings) == len(diagnostics.REMOTE_QUERIES)
    assert opened is True
    assert calls[-2:] == ["detach", "serial-close"]


def test_remote_collection_reports_unconfirmed_detach(monkeypatch):
    class FakeSerial:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(diagnostics.serial, "Serial", lambda *_args, **_kwargs: FakeSerial())
    monkeypatch.setattr(diagnostics, "open_shell", lambda _port: None)
    monkeypatch.setattr(
        diagnostics, "probe_main_route", lambda _port: "ROUTE_STATE=test\n"
    )
    monkeypatch.setattr(diagnostics, "shell_ok", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(diagnostics, "_remote_report", lambda *_args, **_kwargs: "ok\n")
    monkeypatch.setattr(diagnostics, "read_remote_line_file", lambda *_args, **_kwargs: "{}")
    monkeypatch.setattr(
        diagnostics,
        "detach_shell",
        lambda _port: (_ for _ in ()).throw(TimeoutError("no quiet prompt")),
    )

    _reports, warnings, opened = diagnostics.collect_remote_diagnostics("/dev/fake")

    assert opened is True
    assert any("detach could not be confirmed" in warning for warning in warnings)


def test_shell_open_failure_preserves_main_preflight(monkeypatch):
    class FakeSerial:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(diagnostics.serial, "Serial", lambda *_args, **_kwargs: FakeSerial())
    monkeypatch.setattr(
        diagnostics,
        "probe_main_route",
        lambda _port: "ROUTE_STATE=main-parser-responsive\nMAIN_RTC_ACK=yes\n",
    )
    monkeypatch.setattr(
        diagnostics,
        "open_shell",
        lambda _port: (_ for _ in ()).throw(
            RuntimeError("Main did not open a correlated CM0 shell")
        ),
    )

    reports, warnings, opened = diagnostics.collect_remote_diagnostics("COM11")

    assert opened is False
    assert "MAIN_RTC_ACK=yes" in reports["main-route-probe.txt"]
    assert "Main did not open" in reports["cm0-shell-error.txt"]
    assert warnings == (
        "CM0 shell: Main did not open a correlated CM0 shell",
    )


def test_bundle_survives_remote_failure_and_omits_private_text(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
    session = diagnostics.SessionLog(tmp_path / "logs")
    session.write(
        "DETAIL", "decoded Morse candidate confidence=1.00 text='PRIVATE CW TEXT'"
    )
    monkeypatch.setattr(device_install, "verify_release_checksums", lambda _root: None)
    monkeypatch.setattr(
        diagnostics,
        "collect_remote_diagnostics",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bridge timeout")),
    )
    monkeypatch.setattr(
        diagnostics,
        "host_serial_inventory",
        lambda port: {
            "selected_port": port,
            "selected_is_freewili_main": True,
            "freewili_main_candidates": [port],
            "serial_ports": [],
        },
    )

    def progress(value, message):
        session.write("PROGRESS", f"{value}% {message}")

    result = diagnostics.collect_support_bundle(
        root,
        tmp_path / "support.zip",
        port_name="/dev/cu.FreeWili",
        session_log=session.path,
        progress=progress,
    )

    assert result.path.is_file()
    assert not result.remote_collected
    with zipfile.ZipFile(result.path) as archive:
        names = set(archive.namelist())
        assert "cm0-collection-error.txt" in names
        assert "installer-session.log" in names
        assert "host-serial-ports.json" in names
        combined = "\n".join(
            archive.read(name).decode("utf-8", errors="replace") for name in names
        )
    assert "PRIVATE CW TEXT" not in combined
    assert "text=<redacted>" in combined
    assert "bridge timeout" in combined
    assert "82% CM0 evidence unavailable: bridge timeout" in combined
    assert "90% Writing the support ZIP" in combined
