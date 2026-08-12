from tools import fw2_stop_waverider


class FakePort:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_stop_waverider_always_detaches_routed_shell(monkeypatch):
    calls = []
    port = FakePort()
    monkeypatch.setattr(fw2_stop_waverider.serial, "Serial", lambda *_args, **_kwargs: port)
    monkeypatch.setattr(fw2_stop_waverider, "open_shell", lambda value: calls.append(("open", value)))
    monkeypatch.setattr(
        fw2_stop_waverider,
        "shell_ok",
        lambda value, command, **_kwargs: calls.append((command, value)),
    )
    monkeypatch.setattr(
        fw2_stop_waverider,
        "detach_shell",
        lambda value: calls.append(("detach", value)),
    )
    monkeypatch.setattr("sys.argv", ["fw2_stop_waverider.py", "--port", "/dev/test"])

    assert fw2_stop_waverider.main() == 0
    assert calls == [
        ("open", port),
        ("stty -echo", port),
        ("sudo systemctl stop freewili-foxhunt.service", port),
        ("stty echo", port),
        ("detach", port),
    ]


def test_stop_waverider_detaches_after_service_failure(monkeypatch):
    calls = []
    port = FakePort()
    monkeypatch.setattr(fw2_stop_waverider.serial, "Serial", lambda *_args, **_kwargs: port)
    monkeypatch.setattr(fw2_stop_waverider, "open_shell", lambda _value: None)

    def shell_ok(_port, command, **_kwargs):
        calls.append(command)
        if command.startswith("sudo systemctl stop"):
            raise RuntimeError("stop failed")

    monkeypatch.setattr(fw2_stop_waverider, "shell_ok", shell_ok)
    monkeypatch.setattr(fw2_stop_waverider, "detach_shell", lambda _value: calls.append("detach"))
    monkeypatch.setattr("sys.argv", ["fw2_stop_waverider.py", "--port", "/dev/test"])

    try:
        fw2_stop_waverider.main()
    except RuntimeError as error:
        assert str(error) == "stop failed"
    else:
        raise AssertionError("expected the service failure to propagate")

    assert calls == [
        "stty -echo",
        "sudo systemctl stop freewili-foxhunt.service",
        "stty echo",
        "detach",
    ]
