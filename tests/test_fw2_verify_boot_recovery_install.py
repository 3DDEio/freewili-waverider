from __future__ import annotations

import hashlib

import pytest

from tools import fw2_verify_boot_recovery_install


class FakePort:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def configure_port(monkeypatch, calls):
    port = FakePort()
    monkeypatch.setattr(
        fw2_verify_boot_recovery_install.serial,
        "Serial",
        lambda *_args, **_kwargs: port,
    )
    monkeypatch.setattr(
        fw2_verify_boot_recovery_install,
        "open_shell",
        lambda _port: calls.append("open"),
    )
    monkeypatch.setattr(
        fw2_verify_boot_recovery_install,
        "detach_shell",
        lambda _port: calls.append("detach"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["fw2_verify_boot_recovery_install.py", "--port", "/dev/test"],
    )
    return port


def test_verifier_detaches_when_initial_stty_fails(monkeypatch):
    calls = []
    configure_port(monkeypatch, calls)

    def shell_ok(_port, command, **_kwargs):
        calls.append(command)
        if command == "stty -echo":
            raise TimeoutError("stty failed")

    monkeypatch.setattr(fw2_verify_boot_recovery_install, "shell_ok", shell_ok)

    with pytest.raises(TimeoutError, match="stty failed"):
        fw2_verify_boot_recovery_install.main()

    assert calls == ["open", "stty -echo", "stty echo", "detach"]


def test_verifier_requires_exact_trimmed_hash(monkeypatch):
    calls = []
    configure_port(monkeypatch, calls)
    monkeypatch.setattr(
        fw2_verify_boot_recovery_install,
        "shell_ok",
        lambda _port, command, **_kwargs: calls.append(command),
    )
    expected = hashlib.sha256(
        (
            fw2_verify_boot_recovery_install.ROOT
            / "src/freewili_foxhunt/app.py"
        ).read_bytes()
    ).hexdigest()
    monkeypatch.setattr(
        fw2_verify_boot_recovery_install,
        "shell_readonly",
        lambda *_args, **_kwargs: f"unexpected-prefix-{expected}\n",
    )

    with pytest.raises(RuntimeError, match="does not match working tree"):
        fw2_verify_boot_recovery_install.main()

    assert calls == ["open", "stty -echo", "stty echo", "detach"]
