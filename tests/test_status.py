import stat

from freewili_foxhunt.status import StatusWriter


def test_status_writer_publishes_world_readable_runtime_evidence(tmp_path):
    path = tmp_path / "status.json"

    StatusWriter(path).write(state="live")

    assert stat.S_IMODE(path.stat().st_mode) == 0o644
