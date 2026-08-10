from tools.fw2_verify_native_buttons import command_fields, prove_change


def packed(sequence: int, opcode: int, argument: int = 0) -> int:
    return (sequence << 8) | (opcode << 4) | argument


def snapshot(*, selected: int, frequency: int, command: int) -> dict[str, int]:
    return {
        "wr_ready": 1,
        "wr_count": 10,
        "wr_sel": selected,
        "wr_freq": frequency,
        "wr_cmd": command,
    }


def test_command_fields_decodes_exact_native_layout():
    assert command_fields(packed(17, 6, 9)) == (17, 6, 9)


def test_green_requires_new_command_selection_and_frequency():
    before = snapshot(selected=0, frequency=147_495_000, command=packed(4, 0))
    after = snapshot(selected=1, frequency=147_420_000, command=packed(5, 6, 1))
    prove_change(before, after, 6)


def test_check_requires_applied_argument_to_match_selection():
    before = snapshot(selected=1, frequency=147_420_000, command=packed(5, 6, 1))
    after = snapshot(selected=2, frequency=147_445_000, command=packed(6, 6, 2))
    prove_change(before, after, 6)


def test_dpad_immediately_applies_selection_and_retunes():
    before = snapshot(selected=1, frequency=147_420_000, command=packed(5, 3))
    after = snapshot(selected=2, frequency=147_445_000, command=packed(6, 6, 2))
    prove_change(before, after, 6)
