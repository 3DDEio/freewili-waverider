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
    assert "static void draw_splash_frame(uint32_t frame)" in source
    assert "static const int8_t whale_bob[]" in source
    assert "static const int8_t sound_wave[]" in source
    assert "#define COL_ORCA_INK" in source
    assert "#define COL_ORCA_SADDLE" in source
    assert "#define COL_ORCA_WHITE" in source
    assert "Procedural surfing orca" in source
    assert "species markings" in source
    assert "Tall, slightly swept dorsal fin" in source
    assert "const uint32_t wave_phase = (frame * 2u) % wave_count;" in source
    assert "draw_splash_frame(frame++);" in source
    assert "uint64_t frame_deadline = time_us_64() + 100000u;" in source
    assert '"RIDE THE SIGNAL"' in source
    assert source.index("show_splash();") < source.index("draw_static();", source.index("int main(void)"))
    assert "if (x < 140u && y < 28u)" in source


def test_native_live_controls_and_startup_feedback_match_field_workflow():
    source = SOURCE.read_text()

    for label in ('"LISTS"', '"MSGS"', '"NEXT"', '"PREV"', '"REFRESH"'):
        assert label in source
    assert "WAVERIDER STARTING" in source
    assert "WAITING FOR CM0 BRIDGE" in source
    assert "STARTING WAVERIDER" in source
    assert "INITIALIZING RTL-SDR" in source
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
    assert '"CW DETECTIONS WILL REMAIN AVAILABLE HERE"' in source
    assert '"wr_state"' in source
    assert "s_live_count = (int)((membership >> 16u) & 0x1Fu)" in source
    assert "level256 = levels[lower]" in source
    assert "s_ui_mode == UI_STATUS || s_ui_mode == UI_REFRESH" in source


def test_native_bridge_recovery_reopens_transport_then_resets_main_once():
    source = SOURCE.read_text()

    assert "#define BRIDGE_REOPEN_AFTER_US 3000000u" in source
    assert "#define BRIDGE_REOPEN_INTERVAL_US 5000000u" in source
    assert "#define BRIDGE_MAIN_RESET_AFTER_US 15000000u" in source
    assert "status == OW_ERR_TIMEOUT || status == OW_ERR_IO" in source
    assert "status == OW_ERR_PROTOCOL" in source
    assert "static void recover_bridge_link(uint64_t now)" in source
    assert "ow_close(&s_dev);" in source
    assert "fw2_app_recovery_open_onewili(&s_dev)" in source
    assert "ow_hardware_settings_home_software_reset(&s_dev)" in source
    assert "!s_main_reset_attempted" in source
    assert "recover_bridge_link(now);" in source
    assert 'bool primary_health = strcmp(name, "wr_seq") == 0;' in source
    assert "if (primary_health && transport_failure)" in source
    assert "else if (primary_health)" in source


def test_native_bridge_failure_becomes_actionable_instead_of_waiting_forever():
    source = SOURCE.read_text()

    assert '"MAIN BRIDGE LOCKED"' in source
    assert '"AUTO RECOVERY DID NOT COMPLETE"' in source
    assert '"HOLD HOME; MAIN SOFTWARE RESET"' in source
    assert "BRIDGE_MAIN_RESET_AFTER_US + 5000000u" in source
    assert '"CM0 DATA STALLED"' in source
    assert '"NO COMPLETE SDR ROW RECEIVED"' in source
    assert '"PRESS REFRESH; THEN MAIN RESET"' in source
    assert "now - s_mode_started_us >= 30000000u" in source
    assert "s_startup_refresh_attempted = true;" in source
    assert "send_command(5, 0);" in source


def test_native_led_feedback_uses_seven_visible_pixels_and_field_states():
    source = SOURCE.read_text()

    assert "static void update_leds(void)" in source
    assert "#define LED_BRIGHTNESS_NORMAL 48u" in source
    assert "#define LED_BRIGHTNESS_POCKET 6u" in source
    assert "#define LED_BRIGHTNESS_STARTUP 18u" in source
    assert "s_ui_mode == UI_POCKET_ALERT" in source
    assert "? LED_BRIGHTNESS_POCKET" in source
    assert ": LED_BRIGHTNESS_NORMAL" in source
    assert "static void update_front_status_led(void)" in source
    front_led = source[source.index("static void update_front_status_led(void)") :]
    front_led = front_led[: front_led.index("static void update_leds(void)")]
    assert "picpwr_apply_main_awake_mask" not in front_led
    assert "RTL-SDR hub" in front_led
    assert source.count("for (int i = 0; i < 7; i++)") >= 3
    assert ".r = 0, .g = 70, .b = 28" in source
    assert "int completed = (int)s_startup_stage + 1" in source
    assert "elapsed > 45000000u" not in source
    assert ".r = 0, .g = 190, .b = 75" in source
    assert "s_ready_led_until_us = time_us_64() + 3000000u" in source
    led_body = source[source.index("static void update_leds(void)") :]
    led_branches = led_body[led_body.index("ws2812_clear();") :]
    assert led_branches.index("now < s_ready_led_until_us") < led_branches.index(
        "s_ui_mode == UI_STARTUP"
    )
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
    cmake = (SOURCE.parent / "CMakeLists.txt").read_text()

    assert "#define PIN_HAPTIC 46u" in source
    assert "#define HAPTIC_GPIO46_SOURCE_VERIFIED 1u" in source
    assert "#define HAPTIC_PULSE_ON_US 150000u" in source
    assert "#define HAPTIC_PULSE_OFF_US 80000u" in source
    assert "#if HAPTIC_GPIO46_SOURCE_VERIFIED" in source
    assert "gpio_set_dir(PIN_HAPTIC, GPIO_OUT)" in source
    assert "gpio_set_drive_strength(PIN_HAPTIC, GPIO_DRIVE_STRENGTH_12MA)" in source
    assert "gpio_get_out_level(PIN_HAPTIC)" in source
    assert "gpio_put(PIN_HAPTIC, 0u)" in source
    assert "POWER_ZONES DISPLAY RGB_LEDS USB_HUB" in cmake
    assert "#define HAPTIC_ALERT_COOLDOWN_US 30000000u" in source
    assert "#define HAPTIC_REARM_HYSTERESIS_TENTHS 30" in source
    assert "static void haptic_task(uint64_t now)" in source
    assert "haptic_task(now);" in source
    assert "haptic_start_three_pulses" in source
    assert "s_haptic_pulses_remaining = 3u" in source
    assert "sleep_ms(HAPTIC" not in source
    assert "static void haptic_test_meshtastic_exact(void)" in source
    haptic_test = source[source.index("static void haptic_test_meshtastic_exact(void)") :]
    haptic_test = haptic_test[: haptic_test.index("static void haptic_task")]
    assert '"waverider: nonblocking Meshtastic haptic TEST begin\\n"' in haptic_test
    assert "haptic_start_three_pulses();" in haptic_test
    assert "sleep_ms(" not in haptic_test
    assert source.count("haptic_test_meshtastic_exact();") == 2
    assert "UI_POCKET_ALERT" in source
    assert '"POCKET ALERT"' in source
    assert '"3 X 150 MS   30 SEC COOLDOWN' in source
    assert '"ENABLE"' in source
    assert '"DISABLE"' in source
    assert '"TEST"' in source
    assert '"TEST: GPIO46 OUTPUT HIGH"' in source
    assert '"GPIO46 ACTIVE-HIGH / 12mA"' in source
    assert '"VISUAL RSSI / WATERFALL / LEDS ARE ACTIVE"' in source
    assert "UARTKBD_BTN_PAGE" in source
    assert "send_command(14" in source
    assert "send_command(15" in source


def test_native_morse_message_overlay_uses_bounded_sideband_and_keeps_plot_live():
    source = SOURCE.read_text()

    assert "#define MESSAGE_MAX_BYTES 90u" in source
    assert "#define MESSAGE_OVERLAY_US 8000000u" in source
    assert "static void receive_message_chunk" in source
    assert "static void draw_message_overlay(void)" in source
    assert '"MESSAGE"' in source
    assert '"DETECTED"' in source
    assert '"MORSE / NFM 800 HZ"' in source
    assert "if (span <= 1u)" in source
    assert "receive_message_chunk(frequency, row_values, span == 1u);" in source
    assert "draw_message_overlay();" in source
    overlay = source[source.index("static void draw_message_overlay(void) {") :]
    overlay = overlay[: overlay.index("static void draw_dynamic(void)")]
    assert "PLOT_X" not in overlay
    assert "LIST_X" in overlay


def test_native_morse_history_is_bounded_browsable_and_replay_aware():
    source = SOURCE.read_text()

    assert "#define MESSAGE_HISTORY_MAX 16u" in source
    assert "#define MESSAGE_HEADER_BYTES 11u" in source
    assert "static message_record_t s_message_history[MESSAGE_HISTORY_MAX]" in source
    assert "UI_MESSAGE_FREQUENCIES" in source
    assert "UI_MESSAGE_CLEAR_CONFIRM" in source
    assert "static void draw_message_frequencies(void)" in source
    assert "static void draw_messages(void)" in source
    assert '"MESSAGE %u OF %u ON THIS FREQUENCY"' in source
    assert '"SEEN %s   REPEATS %u   QUALITY %u%%"' in source
    assert '"UP/DOWN OR PREV/NEXT STAYS ON THIS FREQUENCY"' in source
    assert '"CLEAR ALL MESSAGE HISTORY?"' in source
    assert '"THIS REMOVES VERIFIED MESSAGES AND CANDIDATES"' in source
    assert "send_command(0u, 1u);" in source
    assert "if (!replay)" in source
    assert "s_ui_mode == UI_MESSAGES" in source


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
