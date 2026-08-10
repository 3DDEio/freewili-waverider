from pathlib import Path


SOURCE = Path(__file__).parents[1] / "native" / "waverider_display" / "main.c"


def test_native_palette_uses_rgb888_to_rgb565_conversion():
    source = SOURCE.read_text()

    assert "#define RGB565_NATIVE(r, g, b)" in source
    assert "#define COL_BG       RGB565_BE(7, 16, 20)" in source
    assert "#define COL_SELECT   RGB565_BE(15, 67, 59)" in source
    assert "BE16(0x0710)" not in source
    assert "COL_WHITE : COL_RED" not in source


def test_native_app_owns_a_three_second_procedural_splash():
    source = SOURCE.read_text()

    assert "#define WAVERIDER_SPLASH_MS 3000u" in source
    assert "static void draw_splash(void)" in source
    assert "Procedural surfing whale" in source
    assert '"RIDE THE SIGNAL"' in source
    assert source.index("show_splash();") < source.index("draw_static();", source.index("int main(void)"))
    assert "if (x < 140u && y < 28u)" in source


def test_native_live_controls_and_startup_feedback_match_field_workflow():
    source = SOURCE.read_text()

    for label in ('"LISTS"', '"AUDIO"', '"NEXT"', '"PREV"', '"REFRESH"'):
        assert label in source
    assert "WAVERIDER STARTING" in source
    assert "WAITING FOR SDR DATA" in source
    assert "RECEIVER STATUS" in source
    assert "RECEIVER NEEDS ATTENTION" in source
    assert "PRESS REFRESH; CHECK SDR USB" in source
    assert "CHECK OR TAP SDR LIVE = BACK" in source
    assert 'fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider")' in source
    assert 'fb_draw_text(376, 5, 2, COL_GREEN, COL_BG, "SDR LIVE")' in source
    assert "s_cursor = (s_cursor + 1) % s_count" in source
    assert "s_cursor = (s_cursor + s_count - 1) % s_count" in source
    assert '"FREQUENCY LIBRARY"' in source
    assert '"LIVE +/-"' in source
    assert '"ENTER FREQUENCY (MHz)"' in source
    assert '"LEFT/RIGHT SELECTS DIGIT   UP/DOWN CHANGES IT"' in source
    assert '"TOUCH DIGITS TO TYPE   CHECK SAVES"' in source
    assert "s_digit_places_khz" in source
    assert "replace_edit_digit" in source
    assert "UI_DELETE_CONFIRM" in source
    assert '"AUDIO IS NOT AVAILABLE YET"' in source
    assert '"wr_state"' in source
    assert "s_live_count = (int)((membership >> 16u) & 0x1Fu)" in source
    assert "level256 = levels[lower]" in source
    assert "s_ui_mode == UI_STATUS || s_ui_mode == UI_REFRESH" in source


def test_native_led_feedback_uses_seven_visible_pixels_and_field_states():
    source = SOURCE.read_text()

    assert "static void update_leds(void)" in source
    assert source.count("for (int i = 0; i < 7; i++)") >= 3
    assert ".r = 180, .g = 0, .b = 0" in source
    assert ".r = 190, .g = 110, .b = 0" in source
    assert ".r = 0, .g = 190, .b = 75" in source
    assert "now - s_last_row_us > 3000000u" in source
    assert "s_ui_mode = UI_FAULT" in source
    assert "next_led_refresh = now + 250000u" in source
    assert "rssi_color(i * (SCALE_W - 1) / 6)" in source


def test_rssi_marker_repaints_scale_without_retaining_history():
    source = SOURCE.read_text()

    assert "static void draw_rssi_scale(void)" in source
    dynamic = source[source.index("static void draw_dynamic(void)") :]
    clear = dynamic.index(
        "fb_fill_rect(SCALE_X, SCALE_Y - 3, SCALE_W + 72, SCALE_H + 6, COL_BG)"
    )
    repaint = dynamic.index("draw_rssi_scale();", clear)
    marker = dynamic.index(
        "fb_fill_rect(SCALE_X + marker, SCALE_Y - 3, 2, SCALE_H + 6, COL_WHITE)",
        repaint,
    )

    assert clear < repaint < marker


def test_native_pocket_alert_is_nonblocking_battery_conscious_and_user_configurable():
    source = SOURCE.read_text()

    assert "#define PIN_HAPTIC 46u" in source
    assert "#define HAPTIC_GPIO46_EXPERIMENTAL 0u" in source
    assert "#if HAPTIC_GPIO46_EXPERIMENTAL" in source
    assert "gpio_set_dir(PIN_HAPTIC, GPIO_OUT)" in source
    assert "gpio_set_outover(PIN_HAPTIC, GPIO_OVERRIDE_NORMAL)" in source
    assert "gpio_set_inover(PIN_HAPTIC, GPIO_OVERRIDE_NORMAL)" in source
    assert "gpio_set_oeover(PIN_HAPTIC, GPIO_OVERRIDE_NORMAL)" in source
    assert "gpio_set_drive_strength(PIN_HAPTIC, GPIO_DRIVE_STRENGTH_12MA)" in source
    assert "gpio_get_out_level(PIN_HAPTIC)" in source
    assert "gpio_put(PIN_HAPTIC, 0u)" in source
    assert "#define HAPTIC_ALERT_COOLDOWN_US 30000000u" in source
    assert "#define HAPTIC_REARM_HYSTERESIS_TENTHS 30" in source
    assert "static void haptic_task(uint64_t now)" in source
    assert "haptic_task(now);" in source
    assert "haptic_start_three_pulses" in source
    assert "s_haptic_pulses_remaining = 3u" in source
    assert "sleep_ms(HAPTIC" not in source
    assert "UI_POCKET_ALERT" in source
    assert '"POCKET ALERT"' in source
    assert '"3 PULSES   30 SEC COOLDOWN' in source
    assert '"ENABLE"' in source
    assert '"DISABLE"' in source
    assert '"TEST"' in source
    assert '"TEST: GPIO46 OUTPUT HIGH"' in source
    assert '"MOTOR DRIVER NOT PUBLISHED"' in source
    assert '"VISUAL RSSI / WATERFALL / LEDS ARE ACTIVE"' in source
    assert "UARTKBD_BTN_PAGE" in source
    assert "send_command(14" in source
    assert "send_command(15" in source


def test_pocket_alert_live_updates_do_not_clear_or_rebuild_the_full_screen():
    source = SOURCE.read_text()

    poll_frame = source[source.index("static void poll_frame(void)") :]
    poll_frame = poll_frame[: poll_frame.index("static void send_command")]
    assert "draw_pocket_alert();" not in poll_frame
    assert "draw_pocket_alert_dynamic();" not in poll_frame


def test_haptic_pin_probe_is_explicit_input_only_and_restores_each_candidate():
    source = SOURCE.read_text()

    assert "static const uint8_t s_haptic_probe_pins[] = {31u, 36u, 44u, 46u}" in source
    assert "#define HAPTIC_PROBE_TOUCH_US 350000u" in source
    assert "gpio_set_dir(pin, GPIO_IN);" in source
    assert "gpio_pull_up(pin);" in source
    assert "gpio_pull_down(pin);" in source
    assert "gpio_set_dir(pin, GPIO_OUT);" not in source
    assert "io_bank0_hw->io[pin].ctrl = s_haptic_probe_saved_ctrl;" in source
    assert "pads_bank0_hw->io[pin] = s_haptic_probe_saved_pad;" in source
    assert '"INPUT ONLY: PULL-UP, FLOAT, PULL-DOWN, RESTORE"' in source
    assert "haptic_probe_task(now);" in source

    dynamic = source[source.index("static void draw_pocket_alert_dynamic(void) {") :]
    dynamic = dynamic[: dynamic.index("static void draw_pocket_alert(void) {")]
    assert "fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG)" not in dynamic
    assert "fb_fill_rect(36, 94, 408, 150, COL_PANEL)" in dynamic
