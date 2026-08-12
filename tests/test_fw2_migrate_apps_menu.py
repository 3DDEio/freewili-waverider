from pathlib import Path

import pytest

from tools.fw2_migrate_apps_menu import migrate_volume


def make_volume(tmp_path: Path) -> tuple[Path, Path]:
    volume = tmp_path / "MAIN"
    (volume / "apps" / "Radio").mkdir(parents=True)
    source = tmp_path / "WaveRider.uf2"
    source.write_bytes(b"friendly-wave-rider")
    return volume, source


def test_migration_installs_friendly_name_and_removes_empty_legacy_category(tmp_path):
    volume, source = make_volume(tmp_path)
    old = volume / "apps" / "Radio" / "waverider_display.uf2"
    old.write_bytes(b"old")
    legacy = volume / "apps" / "waverider"
    legacy.mkdir()

    result = migrate_volume(volume, source)

    assert (volume / "apps" / "Radio" / "WaveRider.uf2").read_bytes() == source.read_bytes()
    assert not old.exists()
    assert not legacy.exists()
    assert result["removed_old_radio_file"] is True
    assert result["removed_empty_legacy_category"] is True


def test_migration_refuses_to_remove_nonempty_legacy_category(tmp_path):
    volume, source = make_volume(tmp_path)
    legacy = volume / "apps" / "waverider"
    legacy.mkdir()
    (legacy / "keep-me.uf2").write_bytes(b"user data")

    with pytest.raises(RuntimeError, match="not empty"):
        migrate_volume(volume, source)

    assert (legacy / "keep-me.uf2").read_bytes() == b"user data"
    assert (volume / "apps" / "Radio" / "WaveRider.uf2").is_file()


def test_migration_requires_an_apps_volume(tmp_path):
    source = tmp_path / "WaveRider.uf2"
    source.write_bytes(b"app")

    with pytest.raises(RuntimeError, match="no apps directory"):
        migrate_volume(tmp_path / "not-main-sd", source)
