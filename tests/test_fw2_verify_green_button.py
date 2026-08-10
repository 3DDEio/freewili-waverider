from tools.fw2_verify_green_button import selection_changed


def test_selection_changed_requires_both_row_and_frequency():
    before = {
        "state": "live",
        "display_connected": True,
        "selected": 0,
        "frequency_hz": 145_265_000,
    }

    assert selection_changed(
        before,
        {
            "state": "live",
            "display_connected": True,
            "selected": 1,
            "frequency_hz": 146_520_000,
        },
    )
    assert not selection_changed(before, {**before, "selected": 1})
    assert not selection_changed(before, {**before, "frequency_hz": 146_520_000})
    assert not selection_changed(
        before,
        {
            "state": "error",
            "display_connected": True,
            "selected": 1,
            "frequency_hz": 146_520_000,
        },
    )
