import json

import pytest

from freewili_foxhunt.store import PocketAlertSettings, PocketAlertStore


def test_pocket_alert_defaults_are_opt_in_and_persist_atomically(tmp_path):
    store = PocketAlertStore(tmp_path / "pocket-alert.json")

    settings = store.load_or_default()

    assert settings == PocketAlertSettings(
        enabled=False,
        threshold_dbfs=-50,
        cooldown_seconds=30,
    )
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["enabled"] is False
    assert list(tmp_path.glob("*.tmp")) == []


def test_pocket_alert_round_trips_and_rejects_unsafe_settings(tmp_path):
    store = PocketAlertStore(tmp_path / "pocket-alert.json")
    store.save(PocketAlertSettings(enabled=True, threshold_dbfs=-47))

    assert store.load() == PocketAlertSettings(enabled=True, threshold_dbfs=-47)

    with pytest.raises(ValueError, match="between -70 and -10"):
        store.save(PocketAlertSettings(enabled=True, threshold_dbfs=-71))
    with pytest.raises(ValueError, match="30 seconds"):
        store.save(PocketAlertSettings(cooldown_seconds=10))
