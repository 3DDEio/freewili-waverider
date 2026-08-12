from __future__ import annotations

from pathlib import Path
import signal

from freewili_foxhunt.bridge_recovery import release_initial_shell_route


def make_process(root: Path, pid: int, ppid: int, args: tuple[str, ...]) -> None:
    process = root / str(pid)
    process.mkdir()
    (process / "status").write_text(f"Name:\ttest\nPPid:\t{ppid}\n")
    (process / "cmdline").write_bytes(b"\0".join(part.encode() for part in args) + b"\0")


def test_releases_only_bridge_owned_login(tmp_path: Path) -> None:
    make_process(tmp_path, 533, 1, ("/usr/local/bin/fwcm0", "bridge"))
    make_process(tmp_path, 1167, 533, ("login", "-f", "pi"))
    make_process(tmp_path, 1201, 1167, ("-bash",))
    calls: list[tuple[int, int]] = []

    result = release_initial_shell_route(
        tmp_path,
        lambda pid, sig: calls.append((pid, sig)),
        tmp_path / "not-inhibited",
    )

    assert result.released is True
    assert calls == [(1167, signal.SIGHUP)]


def test_ignores_unrelated_login_process(tmp_path: Path) -> None:
    make_process(tmp_path, 533, 1, ("/usr/local/bin/fwcm0", "bridge"))
    make_process(tmp_path, 1167, 533, ("login", "-f", "root"))
    make_process(tmp_path, 2000, 1, ("login", "-f", "pi"))
    calls: list[tuple[int, int]] = []

    result = release_initial_shell_route(
        tmp_path,
        lambda pid, sig: calls.append((pid, sig)),
        tmp_path / "not-inhibited",
    )

    assert result.released is False
    assert calls == []


def test_reports_bridge_not_ready(tmp_path: Path) -> None:
    result = release_initial_shell_route(
        tmp_path,
        lambda pid, sig: None,
        tmp_path / "not-inhibited",
    )

    assert result.released is False
    assert "not ready" in result.message


def test_honors_maintenance_inhibit(tmp_path: Path) -> None:
    make_process(tmp_path, 533, 1, ("/usr/local/bin/fwcm0", "bridge"))
    make_process(tmp_path, 1167, 533, ("login", "-f", "pi"))
    inhibit = tmp_path / "maintenance-shell"
    inhibit.write_text("active\n")
    calls: list[tuple[int, int]] = []

    result = release_initial_shell_route(
        tmp_path,
        lambda pid, sig: calls.append((pid, sig)),
        inhibit,
    )

    assert result.released is False
    assert "inhibited" in result.message
    assert calls == []
