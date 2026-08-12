import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "test-beacon" / "code.py"
DEPLOY = ROOT / "test-beacon" / "deploy.py"
RELEASE = ROOT / "deploy" / "build-release.sh"


def assigned_literals(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text())
    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            try:
                values[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return values


def test_optional_beacon_matches_two_frequency_field_fixture():
    values = assigned_literals(SOURCE)

    assert values["FREQUENCY_MHZ"] == 144.3000
    assert values["CALL_MESSAGE"] == "KO6FQY -- decoy decoy -- KO6FQY"
    assert values["MORSE_WPM"] == 13
    assert values["MORSE_TONE_HZ"] == 800
    assert values["MESSAGE_DELAY_SECONDS"] == 30.0


def test_optional_beacon_is_low_power_and_preserves_pwm_timing():
    source = SOURCE.read_text()

    assert "POWER_LEVEL_PIN = board.D5" in source
    assert "power_level = output_pin(POWER_LEVEL_PIN, False)" in source
    assert source.count("pwmio.PWMOut(") == 1
    assert "tone_pwm.duty_cycle = 32768" in source
    assert "tone_pwm.duty_cycle = 0" in source
    assert "ptt.value = True" in source


def test_optional_beacon_deployment_verifies_before_activation():
    source = DEPLOY.read_text()
    readback = source.index("readback = ast.literal_eval")
    verification = source.index("if readback != content")
    activation = source.index("os.rename('/code.py.new','/code.py')")

    assert readback < verification < activation
    assert "active code.py was preserved" in source
    assert "os.rename('/code.py','/code.py.last')" in source


def test_optional_beacon_is_not_in_end_user_release_bundle():
    assert '"$ROOT/test-beacon"' not in RELEASE.read_text()
