from deploy import serial_install
from deploy.serial_install import upload_archive, write_paced


class FakePort:
    def __init__(self) -> None:
        self.writes = []
        self.flushes = 0

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        self.flushes += 1


def test_serial_payload_is_split_into_mailbox_safe_chunks():
    port = FakePort()

    write_paced(port, b"abcdefghij", chunk_size=4, pause_seconds=0)

    assert port.writes == [b"abcd", b"efgh", b"ij"]
    assert port.flushes == 3


def test_shell_commands_use_carriage_return(monkeypatch):
    port = FakePort()
    monkeypatch.setattr(serial_install, "read_until_quiet", lambda *_args, **_kwargs: "ready")

    result = serial_install.command(port, "printf READY")

    assert result == "ready"
    assert port.writes == [b"printf READY\r"]


def test_archive_upload_uses_complete_restartable_shell_commands(monkeypatch):
    port = FakePort()
    commands = []
    monkeypatch.setattr(serial_install, "command", lambda _port, value: commands.append(value))

    upload_archive(port, b"abcdef", "/tmp/release.tar.gz", chunk_size=4)

    assert commands == [
        "rm -f /tmp/release.tar.gz.b64 /tmp/release.tar.gz",
        "printf %s 'YWJj' >> /tmp/release.tar.gz.b64",
        "printf %s 'ZGVm' >> /tmp/release.tar.gz.b64",
        "base64 -d /tmp/release.tar.gz.b64 > /tmp/release.tar.gz && rm -f /tmp/release.tar.gz.b64",
    ]
