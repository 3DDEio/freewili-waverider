from pathlib import Path


UNIT = Path(__file__).parents[1] / "deploy" / "freewili-foxhunt.service"


def test_waverider_starts_after_bridge_without_waiting_for_full_multi_user_boot():
    text = UNIT.read_text(encoding="utf-8")

    assert "After=fwcm0-bridge.service" in text
    assert "After=multi-user.target" not in text
    assert "WantedBy=multi-user.target" in text
