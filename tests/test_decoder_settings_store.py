import pytest

from freewili_foxhunt.store import DecoderSettings, DecoderSettingsStore


def test_decoder_settings_default_enabled_and_round_trips_atomically(tmp_path):
    store = DecoderSettingsStore(tmp_path / "decoder-settings.json")

    assert store.load_or_default() == DecoderSettings(cw_enabled=True)
    store.save(DecoderSettings(cw_enabled=False))
    assert store.load() == DecoderSettings(cw_enabled=False)


def test_decoder_settings_rejects_unknown_schema(tmp_path):
    path = tmp_path / "decoder-settings.json"
    path.write_text('{"schema_version": 2, "cw_enabled": true}\n')

    with pytest.raises(ValueError, match="unsupported decoder-settings schema"):
        DecoderSettingsStore(path).load()
