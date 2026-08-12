/* WaveRider native display — direct FW2 keyboard input and CM0 SDR data.
 *
 * This is a loadable SRAM app.  It does not replace the stock display image:
 * hold HOME for five seconds to return to the recovery loader.  The CM0 and
 * Display CPU exchange compact values through Main's app-signal mailbox.
 */
#include "fw2.h"
#include "display/font5x7.h"
#include "input/app_recovery_onewili.h"
#include "onewili.h"
#include "platform/diag.h"
#include "platform/psram.h"
#include "hardware/structs/io_bank0.h"
#include "hardware/structs/pads_bank0.h"
#include "pico/stdlib.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define BE16(c) ((uint16_t)(((uint16_t)(c) >> 8) | ((uint16_t)(c) << 8)))
#define RGB565_NATIVE(r, g, b)                                                \
    ((uint16_t)((((uint16_t)(r) & 0xF8u) << 8) |                             \
                (((uint16_t)(g) & 0xFCu) << 3) |                             \
                ((uint16_t)(b) >> 3)))
#define RGB565_BE(r, g, b) BE16(RGB565_NATIVE((r), (g), (b)))

/* Original WaveRider mockup palette.  The display DMA consumes byte-swapped
 * RGB565; defining these from RGB888 prevents abbreviated web hex values from
 * accidentally becoming neon RGB565 colors. */
#define COL_BG       RGB565_BE(7, 16, 20)
#define COL_PANEL    RGB565_BE(10, 25, 31)
#define COL_TEXT     RGB565_BE(236, 244, 246)
#define COL_DIM      RGB565_BE(116, 143, 151)
#define COL_RED      RGB565_BE(255, 119, 102)
#define COL_GREEN    RGB565_BE(49, 230, 178)
#define COL_BLUE     RGB565_BE(77, 163, 255)
#define COL_YELLOW   RGB565_BE(255, 205, 92)
#define COL_WHITE    RGB565_BE(255, 255, 255)
#define COL_SELECT   RGB565_BE(15, 67, 59)
#define COL_BORDER   RGB565_BE(30, 66, 73)
#define COL_SPLASH_WAVE RGB565_BE(28, 141, 210)
#define COL_ORCA_INK  RGB565_BE(3, 8, 14)
#define COL_ORCA_SADDLE RGB565_BE(112, 139, 148)
#define COL_ORCA_WHITE RGB565_BE(238, 246, 247)
#define COL_CYBER_CYAN RGB565_BE(42, 232, 255)
#define COL_CYBER_MAGENTA RGB565_BE(255, 75, 210)
#define COL_CYBER_GRID RGB565_BE(12, 48, 58)

#define WAVERIDER_SPLASH_MS 3000u
#define CREATOR_SPLASH_MS 6000u
#define CREATOR_SEQUENCE_TIMEOUT_US 4000000u

#define LIST_X 4
#define LIST_Y 30
#define LIST_W 136
#define LIST_H 252
#define PLOT_X 148
#define PLOT_Y 86
#define PLOT_W 324
#define PLOT_H 142
#define SCALE_X 140
#define SCALE_Y 237
#define SCALE_W 264
#define SCALE_H 8
#define MAX_FREQS 16
#define VISIBLE_FREQS 10
#define LIBRARY_VISIBLE_FREQS 10
#define WATERFALL_BINS 12
#define MIN_FREQUENCY_KHZ 24000u
#define MAX_FREQUENCY_KHZ 1766000u
#define PIN_HAPTIC 35u
/* Display GPIO35 was independently bench-traced on production FW2 v07 and
 * physically confirmed on FX0177 with WaveRider's three-pulse self-test.
 * Older public material naming GPIO46 is incorrect for this board. */
#define HAPTIC_GPIO35_VERIFIED 1u
#define HAPTIC_PULSE_ON_US 150000u
#define HAPTIC_PULSE_OFF_US 80000u
#define HAPTIC_ALERT_COOLDOWN_US 30000000u
#define HAPTIC_REARM_HYSTERESIS_TENTHS 30
#define HAPTIC_PROBE_TOUCH_US 350000u
#define HAPTIC_PROBE_GAP_US 150000u
#define LED_BRIGHTNESS_NORMAL 48u
#define LED_BRIGHTNESS_POCKET 6u
#define LED_BRIGHTNESS_STARTUP 18u
#define MESSAGE_MAX_BYTES 90u
#define MESSAGE_HEADER_BYTES 11u
#define MESSAGE_TEXT_BYTES (MESSAGE_MAX_BYTES - MESSAGE_HEADER_BYTES)
#define MESSAGE_HISTORY_MAX 16u
#define MESSAGE_OVERLAY_US 8000000u
#define BRIDGE_REOPEN_AFTER_US 3000000u
#define BRIDGE_REOPEN_INTERVAL_US 5000000u
#define BRIDGE_MAIN_RESET_AFTER_US 15000000u

/* Main-shell attach/detach can transiently move device-managed USB rails.
 * Keep every rail that WaveRider or its recovery path needs in the accumulated
 * awake set, so a later reassert can never omit the host, serial, or probe
 * rails merely because one status frame reported them down. */
#define WAVERIDER_KEEP_AWAKE                                                   \
    (picpwr_zone_bit(PICPWR_ZONE_FPGA) |                                      \
     picpwr_zone_bit(PICPWR_ZONE_COMPUTE) |                                   \
     picpwr_zone_bit(PICPWR_ZONE_USB_HUB) |                                   \
     picpwr_zone_bit(PICPWR_ZONE_USB_SERIAL) |                                \
     picpwr_zone_bit(PICPWR_ZONE_DEBUG_PROBE))
#define WAVERIDER_BOOT_RAILS                                                   \
    (picpwr_zone_bit(PICPWR_ZONE_FPGA) |                                      \
     picpwr_zone_bit(PICPWR_ZONE_COMPUTE))

static ow_device s_dev;
static uint16_t __uninitialized_psram("waverider_fb")
    s_fb_store[ST7796_W * ST7796_H];
static uint16_t *const s_fb = s_fb_store;

static uint32_t s_freqs[MAX_FREQS] = {
    147495000u, 147420000u, 147445000u, 147470000u, 147545000u,
    446025000u, 446050000u, 446075000u, 446100000u, 446125000u,
};
static int s_count = 10;
static int s_active;
static int s_cursor;
static uint32_t s_frequency = 147495000u;
static uint32_t s_span = 100000u;
static uint32_t s_requested_span;
static int32_t s_rssi_tenths = -900;
static int32_t s_peak_tenths_khz;
static uint32_t s_row_seq = UINT32_MAX;
static uint32_t s_list_seq = UINT32_MAX;
static uint32_t s_cmd_seq;
static uint32_t s_pending_cmd;
static bool s_cmd_pending;
static bool s_link_ok;
static bool s_fb_dirty;
typedef enum {
    UI_STARTUP,
    UI_LIVE,
    UI_STATUS,
    UI_REFRESH,
    UI_FAULT,
    UI_LISTS_LOADING,
    UI_LISTS,
    UI_DELETE_CONFIRM,
    UI_SETTINGS,
    UI_CREATOR_CREDITS,
    UI_AUDIO,
    UI_WATERFALL_SPAN,
    UI_CW_DECODER,
    UI_MESSAGE_FREQUENCIES,
    UI_MESSAGES,
    UI_MESSAGE_CLEAR_CONFIRM,
    UI_ADD_FREQUENCY,
    UI_POCKET_ALERT,
    UI_HAPTIC_PROBE,
} ui_mode_t;
static ui_mode_t s_ui_mode = UI_STARTUP;
static uint8_t s_startup_stage;
static uint32_t s_refresh_from_seq = UINT32_MAX;
static uint64_t s_last_row_us;
static uint64_t s_mode_started_us;
static uint64_t s_ready_led_until_us;
static bool s_front_led_quiet_active;
static bool s_front_led_restore_enabled = true;
static uint16_t s_library_live_mask;
static uint32_t s_library_total;
static uint32_t s_library_offset;
static uint32_t s_library_notice;
static int s_live_count = 10;
static uint32_t s_edit_frequency_khz;
static uint8_t s_edit_cursor;
static char s_edit_error[40];
static uint32_t s_signal_get_calls;
static uint32_t s_signal_get_ok;
static uint32_t s_signal_get_failed;
static uint32_t s_signal_get_consecutive_failed;
static ow_status s_signal_get_last_status = OW_OK;
static uint64_t s_bridge_failed_since_us;
static uint64_t s_bridge_reopen_at_us;
static bool s_main_reset_attempted;
static bool s_startup_refresh_attempted;
static bool s_alert_enabled;
static int32_t s_alert_threshold_tenths = -500;
static bool s_cw_enabled = true;
static uint8_t s_settings_cursor;
static uint8_t s_creator_sequence_index;
static uint8_t s_creator_sequence_start_cursor;
static uint32_t s_creator_frame;
static uint64_t s_creator_sequence_deadline_us;
static uint64_t s_creator_until_us;
static bool s_alert_armed = true;
static uint64_t s_last_alert_us;
static bool s_haptic_on;
static uint8_t s_haptic_pulses_remaining;
static uint64_t s_haptic_deadline_us;
static const uint8_t s_haptic_probe_pins[] = {31u, 35u, 36u, 44u, 46u};
static uint8_t s_haptic_probe_index;
static uint8_t s_haptic_probe_phase;
static uint64_t s_haptic_probe_deadline_us;
static uint32_t s_haptic_probe_saved_ctrl;
static uint32_t s_haptic_probe_saved_pad;
static bool s_haptic_probe_saved;
static char s_message_staging[MESSAGE_MAX_BYTES + 1u];
static char s_detected_message[MESSAGE_MAX_BYTES + 1u];
static uint8_t s_message_length;
static uint8_t s_message_chunks;
static uint16_t s_message_chunk_mask;
static uint64_t s_message_until_us;
typedef struct {
    char text[MESSAGE_TEXT_BYTES + 1u];
    uint32_t frequency_khz;
    uint8_t repeat_count;
    uint8_t confidence_percent;
    char seen_time[6];
} message_record_t;
static message_record_t s_message_history[MESSAGE_HISTORY_MAX];
static uint8_t s_message_history_count;
static uint8_t s_message_history_cursor;
static uint8_t s_message_frequency_cursor;

static void restore_screen(void);
static void send_command(uint8_t opcode, uint8_t argument);
static void enter_live_view(bool clear_plot);
static void draw_library(void);
static void draw_settings(void);
static void draw_creator_credits_frame(uint32_t frame);
static void draw_audio_page(void);
static void draw_waterfall_span(void);
static void draw_cw_decoder(void);
static void draw_pocket_alert(void);
static void draw_pocket_alert_dynamic(void);
static void draw_haptic_probe(void);
static void draw_message_overlay(void);
static void draw_message_frequencies(void);
static void draw_messages(void);
static void draw_message_clear_confirmation(void);
static bool apply_main_power_mask(uint32_t zone_mask);
static bool apply_main_power_zone(uint8_t zone, bool on,
                                  uint32_t *live_rails);

static const uint32_t s_digit_places_khz[] = {
    1000000u, 100000u, 10000u, 1000u, 100u, 10u, 1u,
};
static const uint32_t s_span_profiles_hz[] = {
    25000u, 100000u, 200000u, 500000u, 1000000u, 2000000u,
};
#define SPAN_PROFILE_COUNT 6u

static uint16_t rgb565_be(uint8_t r, uint8_t g, uint8_t b) {
    return RGB565_BE(r, g, b);
}

static int32_t round_i32(double value) {
    return (int32_t)(value >= 0.0 ? value + 0.5 : value - 0.5);
}

static void fb_fill_rect(int x, int y, int w, int h, uint16_t color) {
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > ST7796_W) w = ST7796_W - x;
    if (y + h > ST7796_H) h = ST7796_H - y;
    if (w <= 0 || h <= 0) return;
    for (int yy = y; yy < y + h; yy++) {
        uint16_t *row = s_fb + (size_t)yy * ST7796_W + x;
        for (int xx = 0; xx < w; xx++) row[xx] = color;
    }
}

static void fb_draw_line(int x0, int y0, int x1, int y1, int width,
                         uint16_t color) {
    int dx = x1 > x0 ? x1 - x0 : x0 - x1;
    int sx = x0 < x1 ? 1 : -1;
    int dy_abs = y1 > y0 ? y1 - y0 : y0 - y1;
    int dy = -dy_abs;
    int sy = y0 < y1 ? 1 : -1;
    int error = dx + dy;
    if (width < 1) width = 1;
    for (;;) {
        fb_fill_rect(x0 - width / 2, y0 - width / 2, width, width, color);
        if (x0 == x1 && y0 == y1) break;
        int twice = 2 * error;
        if (twice >= dy) { error += dy; x0 += sx; }
        if (twice <= dx) { error += dx; y0 += sy; }
    }
}

static int32_t triangle_edge(int ax, int ay, int bx, int by, int px, int py) {
    return (int32_t)(px - ax) * (by - ay) -
           (int32_t)(py - ay) * (bx - ax);
}

static void fb_fill_triangle(int x0, int y0, int x1, int y1, int x2, int y2,
                             uint16_t color) {
    int min_x = x0 < x1 ? x0 : x1;
    int max_x = x0 > x1 ? x0 : x1;
    int min_y = y0 < y1 ? y0 : y1;
    int max_y = y0 > y1 ? y0 : y1;
    if (x2 < min_x) min_x = x2;
    if (x2 > max_x) max_x = x2;
    if (y2 < min_y) min_y = y2;
    if (y2 > max_y) max_y = y2;
    int32_t area = triangle_edge(x0, y0, x1, y1, x2, y2);
    for (int y = min_y; y <= max_y; y++) {
        for (int x = min_x; x <= max_x; x++) {
            int32_t a = triangle_edge(x0, y0, x1, y1, x, y);
            int32_t b = triangle_edge(x1, y1, x2, y2, x, y);
            int32_t c = triangle_edge(x2, y2, x0, y0, x, y);
            bool inside = area < 0 ? (a <= 0 && b <= 0 && c <= 0)
                                   : (a >= 0 && b >= 0 && c >= 0);
            if (inside) fb_fill_rect(x, y, 1, 1, color);
        }
    }
}

static void fb_fill_ellipse(int cx, int cy, int rx, int ry, uint16_t color) {
    int32_t rx2 = (int32_t)rx * rx;
    int32_t ry2 = (int32_t)ry * ry;
    int32_t limit = rx2 * ry2;
    for (int y = -ry; y <= ry; y++) {
        for (int x = -rx; x <= rx; x++) {
            if ((int32_t)x * x * ry2 + (int32_t)y * y * rx2 <= limit)
                fb_fill_rect(cx + x, cy + y, 1, 1, color);
        }
    }
}

static void fb_draw_text(int x, int y, int scale, uint16_t fg, uint16_t bg,
                         const char *text) {
    if (scale < 1) scale = 1;
    if (scale > 4) scale = 4;
    const int cell_w = 6 * scale;
    const int cell_h = 8 * scale;
    for (; *text; text++, x += cell_w) {
        if (x + cell_w > ST7796_W || y + cell_h > ST7796_H) break;
        unsigned char c = (unsigned char)*text;
        const uint8_t *cols = (c >= FONT5X7_FIRST && c <= FONT5X7_LAST)
                                  ? font5x7[c - FONT5X7_FIRST]
                                  : font5x7[0];
        for (int gy = 0; gy < cell_h; gy++) {
            int glyph_y = gy / scale;
            uint16_t *row = s_fb + (size_t)(y + gy) * ST7796_W + x;
            for (int gx = 0; gx < cell_w; gx++) {
                int glyph_x = gx / scale;
                bool on = glyph_x < 5 && glyph_y < 7 &&
                          ((cols[glyph_x] >> glyph_y) & 1u);
                row[gx] = on ? fg : bg;
            }
        }
    }
}

static void draw_splash_frame(uint32_t frame) {
    /* Twelve calm animation poses keep the whale's motion readable on the
     * 480 x 320 panel without turning startup into a distracting light show. */
    static const int8_t whale_bob[] = {
        0, -2, -4, -5, -4, -2, 0, 2, 4, 5, 4, 2,
    };
    static const int8_t sound_wave[] = {
        0, 2, 5, 11, 21, 34, 21, 11, 5, 2, 0, -2,
        -5, -11, -21, -34, -21, -11, -5, -2, 0, 1, 2, 1,
    };
    const uint32_t bob_phase = frame %
        (sizeof whale_bob / sizeof whale_bob[0]);
    const int whale_y = whale_bob[bob_phase];
    const int tail_kick = whale_bob[(bob_phase + 3u) %
        (sizeof whale_bob / sizeof whale_bob[0])] / 2;
    const uint32_t wave_count = sizeof sound_wave / sizeof sound_wave[0];
    const uint32_t wave_phase = (frame * 2u) % wave_count;
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);

    /* A moving audio waveform becomes three layers of surf beneath the whale.
     * The phase advances left-to-right while amplitude stays bounded, so the
     * motion reads as signal energy rather than arbitrary rolling water. */
    for (int sample = 1; sample <= 48; sample++) {
        int x0 = (sample - 1) * 10;
        int x1 = sample * 10;
        int y0 = 174 - sound_wave[((uint32_t)(sample - 1) + wave_phase) %
                                  wave_count];
        int y1 = 174 - sound_wave[((uint32_t)sample + wave_phase) %
                                  wave_count];
        fb_draw_line(x0, y0, x1, y1, 6, COL_SPLASH_WAVE);
        fb_draw_line(x0, y0 + 10, x1, y1 + 10, 3, COL_BLUE);
        fb_draw_line(x0, y0 + 17, x1, y1 + 17, 2, COL_BORDER);
    }

    /* Procedural surfing orca: distinctive anatomy without an SD image.
     * Cyan edging preserves the silhouette on the near-black instrument
     * background; eye patch, belly, saddle, dorsal, flukes, and pectoral fin
     * make the animal read as an orca even at 480 x 320. */
    fb_fill_triangle(242, 108 + whale_y,
                     208, 83 + whale_y + tail_kick,
                     220, 116 + whale_y, COL_SPLASH_WAVE);
    fb_fill_triangle(242, 116 + whale_y,
                     211, 141 + whale_y - tail_kick,
                     221, 111 + whale_y, COL_SPLASH_WAVE);
    fb_fill_triangle(240, 108 + whale_y,
                     213, 88 + whale_y + tail_kick,
                     222, 114 + whale_y, COL_ORCA_INK);
    fb_fill_triangle(240, 115 + whale_y,
                     215, 136 + whale_y - tail_kick,
                     222, 112 + whale_y, COL_ORCA_INK);

    /* Tall, slightly swept dorsal fin and lower pectoral fin. */
    fb_fill_triangle(279, 95 + whale_y, 292, 53 + whale_y,
                     312, 96 + whale_y, COL_SPLASH_WAVE);
    fb_fill_triangle(283, 94 + whale_y, 293, 58 + whale_y,
                     308, 95 + whale_y, COL_ORCA_INK);
    fb_fill_triangle(313, 126 + whale_y, 342, 153 + whale_y,
                     332, 121 + whale_y, COL_SPLASH_WAVE);
    fb_fill_triangle(316, 126 + whale_y, 338, 148 + whale_y,
                     330, 122 + whale_y, COL_ORCA_INK);

    /* Body, rounded head, and species markings. */
    fb_fill_ellipse(300, 112 + whale_y, 65, 28, COL_SPLASH_WAVE);
    fb_fill_ellipse(301, 112 + whale_y, 62, 25, COL_ORCA_INK);
    fb_fill_ellipse(347, 111 + whale_y, 20, 18, COL_ORCA_INK);
    fb_fill_ellipse(305, 96 + whale_y, 18, 7, COL_ORCA_SADDLE);
    fb_fill_ellipse(315, 125 + whale_y, 40, 9, COL_ORCA_WHITE);
    fb_fill_ellipse(345, 119 + whale_y, 16, 9, COL_ORCA_WHITE);
    fb_fill_ellipse(337, 101 + whale_y, 12, 5, COL_ORCA_WHITE);
    fb_fill_ellipse(341, 101 + whale_y, 2, 2, COL_ORCA_INK);
    fb_draw_line(347, 120 + whale_y, 362, 116 + whale_y,
                 2, COL_ORCA_INK);

    /* A small blow and a wave-colored highlight reinforce upward motion. */
    fb_draw_line(358, 83 + whale_y, 358, 67 + whale_y, 3, COL_BLUE);
    fb_draw_line(358, 68 + whale_y, 348, 57 + whale_y, 3, COL_BLUE);
    fb_draw_line(358, 68 + whale_y, 368, 57 + whale_y, 3, COL_BLUE);

    fb_draw_text(132, 220, 4, COL_WHITE, COL_BG, "WaveRider");
    fb_draw_text(150, 267, 2, COL_GREEN, COL_BG, "RIDE THE SIGNAL");
    s_fb_dirty = true;
}

static void show_splash(void) {
    board_backlight_set(1);
    uint64_t deadline = time_us_64() +
                        (uint64_t)WAVERIDER_SPLASH_MS * 1000u;
    uint32_t frame = 0u;
    while (time_us_64() < deadline) {
        draw_splash_frame(frame++);
        restore_screen();
        uint64_t frame_deadline = time_us_64() + 100000u;
        if (frame_deadline > deadline) frame_deadline = deadline;
        while (time_us_64() < frame_deadline) {
            fw2_app_recovery_task();
            agentio_task();
            fw2_app_recovery_sleep_ms(10);
        }
    }
}

static void draw_creator_credits_frame(uint32_t frame) {
    /* This is intentionally an RF operations console, not a generic neon
     * title card: the animated trace resolves into two equal creator nodes. */
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);

    for (int x = 14; x < ST7796_W - 10; x += 30)
        fb_fill_rect(x, 12, 1, 296, COL_CYBER_GRID);
    for (int y = 12; y < ST7796_H - 10; y += 24)
        fb_fill_rect(12, y, 456, 1, COL_CYBER_GRID);

    int scan_y = 14 + (int)((frame * 9u) % 290u);
    fb_fill_rect(12, scan_y, 456, 1, COL_CYBER_CYAN);
    if (scan_y + 1 < 308)
        fb_fill_rect(12, scan_y + 1, 456, 1, COL_CYBER_GRID);

    fb_fill_rect(10, 10, 460, 2, COL_CYBER_CYAN);
    fb_fill_rect(10, 308, 460, 2, COL_CYBER_MAGENTA);
    fb_fill_rect(10, 10, 2, 300, COL_CYBER_CYAN);
    fb_fill_rect(468, 10, 2, 300, COL_CYBER_MAGENTA);
    fb_draw_text(18, 18, 1, COL_CYBER_CYAN, COL_BG,
                 "// WAVERIDER::CREATOR UPLINK");
    fb_draw_text(372, 18, 1, COL_CYBER_MAGENTA, COL_BG,
                 "ACCESS OK");
    fb_draw_text(84, 40, 4, COL_WHITE, COL_BG, "SIGNAL ORIGIN");

    /* Animated frequency trace: phase motion provides energy while mirrored
     * peaks lead the eye into the two equal-weight creator cards below. */
    static const int8_t trace[] = {
        0, 1, -1, 2, -2, 4, -4, 8, -12, 20, -12, 8, -4, 3, -2, 1,
        0, -1, 2, -2, 4, -7, 11, -18, 26, -18, 11, -7, 4, -2, 2, -1,
    };
    int last_x = 16;
    int last_y = 112 + trace[frame % (sizeof trace / sizeof trace[0])];
    for (int x = 17; x < 464; x++) {
        uint32_t index = ((uint32_t)x / 4u + frame) %
                         (sizeof trace / sizeof trace[0]);
        int y = 112 + trace[index];
        fb_draw_line(last_x, last_y, x, y, 1,
                     x < 240 ? COL_CYBER_CYAN : COL_CYBER_MAGENTA);
        last_x = x;
        last_y = y;
    }
    int pulse_x = 18 + (int)((frame * 13u) % 444u);
    fb_fill_ellipse(pulse_x, 112, 4, 4,
                    pulse_x < 240 ? COL_WHITE : COL_YELLOW);

    fb_fill_rect(24, 144, 204, 96, COL_PANEL);
    fb_fill_rect(252, 144, 204, 96, COL_PANEL);
    fb_fill_rect(24, 144, 204, 2, COL_CYBER_CYAN);
    fb_fill_rect(252, 144, 204, 2, COL_CYBER_MAGENTA);
    fb_fill_rect(24, 238, 204, 2, COL_CYBER_CYAN);
    fb_fill_rect(252, 238, 204, 2, COL_CYBER_MAGENTA);
    fb_fill_rect(24, 144, 2, 96, COL_CYBER_CYAN);
    fb_fill_rect(226, 144, 2, 96, COL_CYBER_CYAN);
    fb_fill_rect(252, 144, 2, 96, COL_CYBER_MAGENTA);
    fb_fill_rect(454, 144, 2, 96, COL_CYBER_MAGENTA);
    fb_draw_text(38, 156, 1, COL_CYBER_CYAN, COL_PANEL,
                 "ORIGIN NODE // 01");
    fb_draw_text(266, 156, 1, COL_CYBER_MAGENTA, COL_PANEL,
                 "ORIGIN NODE // 02");
    fb_draw_text(72, 184, 3, COL_WHITE, COL_PANEL, "KO6FQY");
    fb_draw_text(300, 184, 3, COL_WHITE, COL_PANEL, "KO6FQJ");
    fb_draw_text(84, 219, 1, COL_CYBER_CYAN, COL_PANEL, "CREATOR");
    fb_draw_text(312, 219, 1, COL_CYBER_MAGENTA, COL_PANEL, "CREATOR");

    fb_fill_rect(228, 190, 24, 2, COL_BORDER);
    fb_fill_triangle(236, 184, 244, 191, 236, 198, COL_WHITE);
    fb_fill_triangle(244, 184, 252, 191, 244, 198, COL_WHITE);
    fb_draw_text(126, 260, 2, COL_TEXT, COL_BG,
                 "CREATED FOR THE HUNT");
    fb_draw_text(154, 284, 1, COL_GREEN, COL_BG,
                 "RIDE THE SIGNAL // TOGETHER");
    fb_draw_text(174, 299, 1, COL_DIM, COL_BG,
                 "ANY KEY OR TAP TO RETURN");
    s_fb_dirty = true;
}

static void show_creator_credits(void) {
    s_ui_mode = UI_CREATOR_CREDITS;
    s_creator_frame = 0u;
    s_creator_until_us = time_us_64() +
                         (uint64_t)CREATOR_SPLASH_MS * 1000u;
    draw_creator_credits_frame(s_creator_frame++);
}

static bool creator_sequence_step(uint8_t button, uint64_t now) {
    static const uint8_t sequence[] = {
        UARTKBD_BTN_NAV_UP, UARTKBD_BTN_NAV_UP,
        UARTKBD_BTN_NAV_DOWN, UARTKBD_BTN_NAV_DOWN,
        UARTKBD_BTN_NAV_LEFT, UARTKBD_BTN_NAV_RIGHT,
        UARTKBD_BTN_NAV_LEFT, UARTKBD_BTN_NAV_RIGHT,
    };
    if (s_creator_sequence_index != 0u &&
        now > s_creator_sequence_deadline_us)
        s_creator_sequence_index = 0u;

    if (button == sequence[s_creator_sequence_index]) {
        if (s_creator_sequence_index == 0u)
            s_creator_sequence_start_cursor = s_settings_cursor;
        s_creator_sequence_index++;
        s_creator_sequence_deadline_us = now + CREATOR_SEQUENCE_TIMEOUT_US;
    } else if (button == sequence[0]) {
        s_creator_sequence_start_cursor = s_settings_cursor;
        s_creator_sequence_index = 1u;
        s_creator_sequence_deadline_us = now + CREATOR_SEQUENCE_TIMEOUT_US;
    } else {
        s_creator_sequence_index = 0u;
        return false;
    }

    if (s_creator_sequence_index < sizeof sequence) return false;
    s_creator_sequence_index = 0u;
    /* Navigation performed while entering the secret sequence must not leave
     * Settings on a surprising row after the credits page closes. */
    s_settings_cursor = s_creator_sequence_start_cursor;
    show_creator_credits();
    return true;
}

static void format_frequency(char *out, size_t cap, uint32_t hz) {
    snprintf(out, cap, "%lu.%03lu", (unsigned long)(hz / 1000000u),
             (unsigned long)((hz / 1000u) % 1000u));
}

static void format_tenths(char *out, size_t cap, int32_t value) {
    bool negative = value < 0;
    uint32_t magnitude = (uint32_t)(negative ? -value : value);
    snprintf(out, cap, "%s%lu.%lu", negative ? "-" : "",
             (unsigned long)(magnitude / 10u),
             (unsigned long)(magnitude % 10u));
}

static uint16_t waterfall_color(uint8_t level) {
    if (level > 15u) level = 15u;
    if (level <= 5u) {
        uint8_t t = (uint8_t)(level * 51u);
        return rgb565_be(0, (uint8_t)(t / 3u), (uint8_t)(70u + t * 185u / 255u));
    }
    if (level <= 10u) {
        uint8_t t = (uint8_t)((level - 5u) * 51u);
        return rgb565_be(t, (uint8_t)(85u - t / 3u), 255u - t / 2u);
    }
    uint8_t t = (uint8_t)((level - 10u) * 51u);
    return rgb565_be(255u, (uint8_t)(50u + t * 205u / 255u),
                     (uint8_t)(127u - t / 2u));
}

static uint16_t rssi_color(int pixel) {
    int level = pixel * 15 / (SCALE_W - 1);
    return waterfall_color((uint8_t)level);
}

static void draw_rssi_scale(void) {
    for (int x = 0; x < SCALE_W; x++)
        fb_fill_rect(SCALE_X + x, SCALE_Y, 1, SCALE_H, rssi_color(x));
}

static void draw_button(int index, const char *label, uint16_t color) {
    const int x = 4 + index * 96;
    fb_fill_rect(x, 289, 88, 27, COL_PANEL);
    fb_fill_rect(x, 289, 88, 1, color);
    fb_fill_rect(x, 315, 88, 1, color);
    fb_fill_rect(x, 289, 1, 27, color);
    fb_fill_rect(x + 87, 289, 1, 27, color);
    int width = (int)strlen(label) * 12;
    fb_draw_text(x + (88 - width) / 2, 295, 2, color, COL_PANEL, label);
}

static void draw_static(void) {
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_fill_rect(LIST_X, LIST_Y, LIST_W, LIST_H, COL_PANEL);
    fb_fill_rect(LIST_X + LIST_W, LIST_Y, 1, LIST_H, COL_BORDER);
    fb_fill_rect(0, 27, ST7796_W, 1, COL_BORDER);
    fb_fill_rect(PLOT_X, PLOT_Y, PLOT_W, PLOT_H, rgb565_be(0, 0, 35));
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(376, 5, 2, COL_GREEN, COL_BG, "SDR LIVE");
    fb_draw_text(8, 272, 1, COL_DIM, COL_PANEL,
                 "CHECK=TUNE  PAGE=SETTINGS");
    draw_rssi_scale();
    fb_draw_text(SCALE_X, 248, 1, COL_DIM, COL_BG,
                 "-70          -50          -30          -10");
    draw_button(0, "LISTS", COL_TEXT);
    draw_button(1, "MSGS", COL_YELLOW);
    draw_button(2, "NEXT", COL_GREEN);
    draw_button(3, "PREV", COL_BLUE);
    draw_button(4, "REFRESH", COL_RED);
}

static void draw_list(void) {
    fb_fill_rect(LIST_X, LIST_Y, LIST_W, LIST_H - 15, COL_PANEL);
    int first = 0;
    if (s_cursor >= VISIBLE_FREQS) first = s_cursor - VISIBLE_FREQS + 1;
    if (first + VISIBLE_FREQS > s_count) first = s_count - VISIBLE_FREQS;
    if (first < 0) first = 0;
    for (int row = 0; row < VISIBLE_FREQS && first + row < s_count; row++) {
        int i = first + row;
        char frequency[16];
        int y = LIST_Y + row * 23;
        if (i == s_cursor)
            fb_fill_rect(6, y - 1, 130, 21, COL_SELECT);
        format_frequency(frequency, sizeof frequency, s_freqs[i]);
        uint16_t fg = i == s_active ? COL_GREEN : COL_DIM;
        if (i == s_cursor) fg = COL_WHITE;
        fb_draw_text(14, y + 1, 2, fg,
                     i == s_cursor ? COL_SELECT : COL_PANEL, frequency);
    }
    if (s_count > VISIBLE_FREQS) {
        char page[16];
        snprintf(page, sizeof page, "%d-%d/%d", first + 1,
                 first + VISIBLE_FREQS < s_count ? first + VISIBLE_FREQS : s_count,
                 s_count);
        fb_fill_rect(80, 271, 56, 9, COL_PANEL);
        fb_draw_text(80, 271, 1, COL_DIM, COL_PANEL, page);
    }
    s_fb_dirty = true;
}

static void draw_message_overlay(void) {
    if (s_detected_message[0] == '\0' ||
        time_us_64() >= s_message_until_us || s_ui_mode != UI_LIVE)
        return;
    fb_fill_rect(LIST_X + 2, LIST_Y + 2, LIST_W - 4, LIST_H - 19, COL_SELECT);
    fb_fill_rect(LIST_X + 2, LIST_Y + 2, LIST_W - 4, 2, COL_GREEN);
    fb_draw_text(14, 39, 2, COL_GREEN, COL_SELECT, "MESSAGE");
    fb_draw_text(14, 58, 2, COL_GREEN, COL_SELECT, "DETECTED");
    int offset = 0;
    for (int line_index = 0;
         line_index < 8 && s_detected_message[offset] != '\0';
         line_index++) {
        char line[20];
        int count = 0;
        while (count < 19 && s_detected_message[offset] != '\0') {
            line[count++] = s_detected_message[offset++];
        }
        line[count] = '\0';
        fb_draw_text(12, 87 + line_index * 16, 1, COL_TEXT, COL_SELECT, line);
    }
    fb_draw_text(12, 221, 1, COL_DIM, COL_SELECT, "MORSE / NFM 800 HZ");
    fb_draw_text(12, 256, 1, COL_GREEN, COL_PANEL, "AUTO-CLOSE 8 SEC");
    s_fb_dirty = true;
}

static void draw_dynamic(void) {
    char line[48];
    char value[20];
    fb_fill_rect(142, 27, 338, 58, COL_BG);
    format_frequency(value, sizeof value, s_frequency);
    fb_draw_text(148, 29, 4, COL_WHITE, COL_BG, value);
    snprintf(line, sizeof line, "SPAN %lu kHz", (unsigned long)(s_span / 1000u));
    fb_draw_text(354, 34, 1, COL_DIM, COL_BG, line);
    format_tenths(value, sizeof value, s_rssi_tenths);
    snprintf(line, sizeof line, "RSSI %s dBFS", value);
    fb_draw_text(148, 66, 2, COL_YELLOW, COL_BG, line);
    format_tenths(value, sizeof value, s_peak_tenths_khz);
    snprintf(line, sizeof line, "PK %s kHz", value);
    fb_draw_text(354, 68, 1, COL_DIM, COL_BG, line);

    /* The scale is an instantaneous meter, not a peak/history display. Clear
     * the complete old marker footprint and restore every gradient pixel
     * before drawing the current position. Otherwise each marker update leaves
     * a permanent white stripe over the color range. */
    fb_fill_rect(SCALE_X, SCALE_Y - 3, SCALE_W + 72, SCALE_H + 6, COL_BG);
    draw_rssi_scale();
    int marker = (s_rssi_tenths + 700) * (SCALE_W - 1) / 600;
    if (marker < 0) marker = 0;
    if (marker >= SCALE_W - 1) marker = SCALE_W - 2;
    fb_fill_rect(SCALE_X + marker, SCALE_Y - 3, 2, SCALE_H + 6, COL_WHITE);
    format_tenths(value, sizeof value, s_rssi_tenths);
    fb_draw_text(414, 235, 1, COL_YELLOW, COL_BG, value);

    fb_fill_rect(405, 259, 67, 12, COL_BG);
    fb_draw_text(405, 259, 1, s_link_ok ? COL_GREEN : COL_RED, COL_BG,
                 s_link_ok ? "CM0 LINK" : "WAIT CM0");
    s_fb_dirty = true;
}

static const char *startup_stage_text(void) {
    switch (s_startup_stage) {
    case 0: return "POWERING CM0";
    case 1: return "CONNECTING MAIN";
    case 2: return "STARTING CM0 LINUX";
    case 3: return "WAITING FOR CM0 BRIDGE";
    case 4: return "STARTING WAVERIDER";
    default: return "INITIALIZING RTL-SDR";
    }
}

static void draw_startup_status(void) {
    char line[40];
    uint32_t elapsed = s_mode_started_us == 0
                           ? 0u
                           : (uint32_t)((time_us_64() - s_mode_started_us) /
                                        1000000u);
    /* Six verified milestones occupy six sevenths of the bar. The final
     * seventh is earned only when poll_frame receives the first SDR row and
     * replaces this view with the live waterfall. */
    int progress = ((int)s_startup_stage + 1) * 260 / 7;
    if (progress > 250) progress = 250;
    bool bridge_locked = s_main_reset_attempted &&
                         s_bridge_failed_since_us != 0u &&
                         time_us_64() - s_bridge_failed_since_us >=
                             BRIDGE_MAIN_RESET_AFTER_US + 5000000u;
    bool data_stalled = s_last_row_us == 0u && elapsed >= 60u;
    fb_fill_rect(PLOT_X, PLOT_Y, PLOT_W, PLOT_H, COL_PANEL);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 13,
                 bridge_locked || data_stalled ? 1 : 2,
                 bridge_locked || data_stalled ? COL_YELLOW : COL_TEXT,
                 COL_PANEL,
                 bridge_locked ? "MAIN BRIDGE LOCKED"
                               : (data_stalled ? "CM0 DATA STALLED"
                                               : "WAVERIDER STARTING"));
    fb_fill_rect(PLOT_X + 16, PLOT_Y + 43, 260, 10, COL_BORDER);
    fb_fill_rect(PLOT_X + 16, PLOT_Y + 43, progress, 10, COL_GREEN);
    int pulse = (int)((elapsed * 23u) % 250u);
    fb_fill_rect(PLOT_X + 16 + pulse, PLOT_Y + 41, 5, 14, COL_WHITE);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 66,
                 bridge_locked || data_stalled ? 1 : 2,
                 bridge_locked || data_stalled ? COL_YELLOW : COL_GREEN,
                 COL_PANEL,
                 bridge_locked ? "AUTO RECOVERY DID NOT COMPLETE"
                               : (data_stalled ? "NO COMPLETE SDR ROW RECEIVED"
                                               : startup_stage_text()));
    snprintf(line, sizeof line, "ELAPSED %lu SEC", (unsigned long)elapsed);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 93, 1, COL_DIM, COL_PANEL, line);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 111, 1,
                 bridge_locked || data_stalled ? COL_YELLOW : COL_DIM,
                 COL_PANEL,
                 bridge_locked ? "HOLD HOME; MAIN SOFTWARE RESET"
                               : (data_stalled
                                      ? "PRESS REFRESH; THEN MAIN RESET"
                                      : "LIST BROWSING IS READY"));
    s_fb_dirty = true;
}

static void draw_receiver_status(void) {
    char line[48];
    uint32_t age_ms = s_last_row_us == 0
                          ? UINT32_MAX
                          : (uint32_t)((time_us_64() - s_last_row_us) / 1000u);
    bool streaming = age_ms < 2000u;
    fb_fill_rect(PLOT_X, PLOT_Y, PLOT_W, PLOT_H, COL_PANEL);
    const char *title = s_ui_mode == UI_REFRESH
                            ? "REFRESHING SDR"
                            : (s_ui_mode == UI_FAULT
                                   ? "RECEIVER NEEDS ATTENTION"
                                   : "RECEIVER STATUS");
    fb_draw_text(PLOT_X + 14, PLOT_Y + 9,
                 s_ui_mode == UI_FAULT ? 1 : 2,
                 s_ui_mode == UI_FAULT ? COL_YELLOW : COL_TEXT,
                 COL_PANEL, title);
    snprintf(line, sizeof line, "CM0 LINK   %s", s_link_ok ? "ONLINE" : "WAITING");
    fb_draw_text(PLOT_X + 14, PLOT_Y + 35, 1,
                 s_link_ok ? COL_GREEN : COL_YELLOW, COL_PANEL, line);
    snprintf(line, sizeof line, "SDR DATA   %s", streaming ? "STREAMING" : "WAITING");
    fb_draw_text(PLOT_X + 14, PLOT_Y + 52, 1,
                 streaming ? COL_GREEN : COL_YELLOW, COL_PANEL, line);
    if (age_ms == UINT32_MAX)
        snprintf(line, sizeof line, "LAST ROW   NONE YET");
    else
        snprintf(line, sizeof line, "LAST ROW   %lu MS AGO", (unsigned long)age_ms);
    fb_draw_text(PLOT_X + 14, PLOT_Y + 69, 1, COL_DIM, COL_PANEL, line);
    snprintf(line, sizeof line, "ROWS %lu   LINK GET %lu/%lu",
             (unsigned long)(s_row_seq == UINT32_MAX ? 0u : s_row_seq),
             (unsigned long)s_signal_get_ok,
             (unsigned long)s_signal_get_failed);
    fb_draw_text(PLOT_X + 14, PLOT_Y + 86, 1, COL_DIM, COL_PANEL, line);
    snprintf(line, sizeof line, "COMMAND    %s",
             s_cmd_pending ? "WAITING FOR CM0" : "SYNCED");
    fb_draw_text(PLOT_X + 14, PLOT_Y + 103, 1,
                 s_cmd_pending ? COL_YELLOW : COL_GREEN, COL_PANEL, line);
    if (s_ui_mode == UI_FAULT) {
        fb_draw_text(PLOT_X + 14, PLOT_Y + 118, 1, COL_YELLOW, COL_PANEL,
                     s_link_ok ? "PRESS REFRESH; CHECK SDR USB"
                               : "WAIT FOR CM0 OR PRESS REFRESH");
    } else {
        fb_draw_text(PLOT_X + 14, PLOT_Y + 121, 1, COL_BLUE, COL_PANEL,
                     "CHECK OR TAP SDR LIVE = BACK");
    }
    s_fb_dirty = true;
}

static void draw_library_loading(const char *message) {
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(406, 5, 2, COL_GREEN, COL_BG, "LISTS");
    fb_fill_rect(8, 42, 464, 218, COL_PANEL);
    fb_draw_text(48, 92, 3, COL_YELLOW, COL_PANEL, message);
    fb_draw_text(48, 132, 1, COL_DIM, COL_PANEL,
                 "SYNCING SAVED AND LIVE FREQUENCIES");
    fb_draw_text(48, 154, 1, COL_DIM, COL_PANEL,
                 "CM0 STORAGE CHANGES ARE WRITTEN ATOMICALLY");
    draw_button(0, "BACK", COL_TEXT);
    s_fb_dirty = true;
}

static void draw_library(void) {
    char line[48];
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(406, 5, 2, COL_GREEN, COL_BG, "LISTS");
    fb_draw_text(12, 34, 2, COL_TEXT, COL_BG, "FREQUENCY LIBRARY");
    snprintf(line, sizeof line, "SAVED %lu   LIVE %d/16",
             (unsigned long)s_library_total, s_live_count);
    fb_draw_text(286, 38, 1, COL_DIM, COL_BG, line);
    fb_fill_rect(8, 56, 464, 222, COL_PANEL);

    int first = 0;
    if (s_cursor >= LIBRARY_VISIBLE_FREQS)
        first = s_cursor - LIBRARY_VISIBLE_FREQS + 1;
    if (first + LIBRARY_VISIBLE_FREQS > s_count)
        first = s_count - LIBRARY_VISIBLE_FREQS;
    if (first < 0) first = 0;
    for (int row = 0; row < LIBRARY_VISIBLE_FREQS && first + row < s_count;
         row++) {
        int index = first + row;
        int y = 61 + row * 21;
        char frequency[16];
        if (index == s_cursor)
            fb_fill_rect(14, y - 2, 450, 20, COL_SELECT);
        format_frequency(frequency, sizeof frequency, s_freqs[index]);
        fb_draw_text(26, y, 2,
                     index == s_cursor ? COL_WHITE : COL_TEXT,
                     index == s_cursor ? COL_SELECT : COL_PANEL,
                     frequency);
        if ((s_library_live_mask & (1u << index)) != 0u) {
            fb_fill_rect(218, y - 1, 58, 17, COL_GREEN);
            fb_draw_text(228, y + 2, 1, COL_BG, COL_GREEN, "LIVE");
        } else {
            fb_draw_text(225, y + 2, 1, COL_DIM,
                         index == s_cursor ? COL_SELECT : COL_PANEL, "SAVED");
        }
        snprintf(line, sizeof line, "%lu",
                 (unsigned long)(s_library_offset + (uint32_t)index + 1u));
        fb_draw_text(422, y + 2, 1, COL_DIM,
                     index == s_cursor ? COL_SELECT : COL_PANEL, line);
    }
    const char *notice = NULL;
    switch (s_library_notice) {
    case 1: notice = "LIVE LIST FULL (16)"; break;
    case 2: notice = "KEEP ONE LIVE FREQUENCY"; break;
    case 3: notice = "SAVED LIBRARY FULL (100)"; break;
    case 4: notice = "FREQUENCY OUT OF RANGE"; break;
    case 5: notice = "ALREADY SAVED"; break;
    case 6: notice = "SAVED"; break;
    case 7: notice = "LIVE LIST UPDATED"; break;
    case 8: notice = "DELETED"; break;
    default: break;
    }
    if (notice != NULL) {
        fb_draw_text(18, 265, 1,
                     s_library_notice >= 6u ? COL_GREEN : COL_YELLOW,
                     COL_PANEL, notice);
    } else if (s_library_total > (uint32_t)s_count) {
        snprintf(line, sizeof line, "%lu-%lu OF %lu",
                 (unsigned long)(s_library_offset + 1u),
                 (unsigned long)(s_library_offset + (uint32_t)s_count),
                 (unsigned long)s_library_total);
        fb_draw_text(335, 265, 1, COL_DIM, COL_PANEL, line);
    }
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, "NEW", COL_YELLOW);
    draw_button(2, "LIVE +/-", COL_GREEN);
    draw_button(3, "TUNE", COL_BLUE);
    draw_button(4, "DELETE", COL_RED);
    s_fb_dirty = true;
}

static uint8_t edit_digit(void) {
    return (uint8_t)((s_edit_frequency_khz /
                      s_digit_places_khz[s_edit_cursor]) % 10u);
}

static void replace_edit_digit(uint8_t digit) {
    uint32_t place = s_digit_places_khz[s_edit_cursor];
    uint32_t old = (s_edit_frequency_khz / place) % 10u;
    s_edit_frequency_khz = s_edit_frequency_khz - old * place +
                           (uint32_t)(digit % 10u) * place;
    s_edit_error[0] = '\0';
}

static void draw_add_frequency(void) {
    char digits[8];
    char line[48];
    snprintf(digits, sizeof digits, "%07lu",
             (unsigned long)s_edit_frequency_khz);
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(356, 5, 2, COL_GREEN, COL_BG, "NEW FREQ");
    fb_draw_text(22, 38, 2, COL_TEXT, COL_BG, "ENTER FREQUENCY (MHz)");

    for (int index = 0; index < 7; index++) {
        int x = 24 + index * 44 + (index >= 4 ? 16 : 0);
        uint16_t background = index == s_edit_cursor ? COL_SELECT : COL_PANEL;
        uint16_t foreground = index == s_edit_cursor ? COL_WHITE : COL_GREEN;
        char digit[2] = {digits[index], '\0'};
        fb_fill_rect(x, 68, 36, 42, background);
        fb_draw_text(x + 9, 76, 3, foreground, background, digit);
        if (index == s_edit_cursor)
            fb_fill_rect(x, 108, 36, 2, COL_YELLOW);
    }
    fb_draw_text(189, 76, 3, COL_TEXT, COL_BG, ".");
    fb_draw_text(354, 78, 2, COL_DIM, COL_BG, "MHz");

    for (int slot = 0; slot < 10; slot++) {
        int digit = slot < 9 ? slot + 1 : 0;
        int column = slot % 5;
        int row = slot / 5;
        int x = 28 + column * 88;
        int y = 135 + row * 48;
        char label[2] = {(char)('0' + digit), '\0'};
        fb_fill_rect(x, y, 72, 36, COL_PANEL);
        fb_fill_rect(x, y, 72, 1, COL_BORDER);
        fb_fill_rect(x, y + 35, 72, 1, COL_BORDER);
        fb_draw_text(x + 28, y + 8, 2, COL_TEXT, COL_PANEL, label);
    }
    snprintf(line, sizeof line,
             "LEFT/RIGHT SELECTS DIGIT   UP/DOWN CHANGES IT");
    fb_draw_text(28, 235, 1, COL_DIM, COL_BG, line);
    fb_draw_text(28, 253, 1, COL_BLUE, COL_BG,
                 "TOUCH DIGITS TO TYPE   CHECK SAVES");
    if (s_edit_error[0] != '\0')
        fb_draw_text(28, 270, 1, COL_RED, COL_BG, s_edit_error);
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, "LEFT", COL_YELLOW);
    draw_button(2, "RIGHT", COL_GREEN);
    draw_button(3, "CLEAR", COL_BLUE);
    draw_button(4, "CANCEL", COL_RED);
    s_fb_dirty = true;
}

static void begin_add_frequency(void) {
    s_ui_mode = UI_ADD_FREQUENCY;
    s_edit_frequency_khz = 0u;
    s_edit_cursor = 1u;
    s_edit_error[0] = '\0';
    draw_add_frequency();
}

static void commit_add_frequency(void) {
    if (s_edit_frequency_khz < MIN_FREQUENCY_KHZ ||
        s_edit_frequency_khz > MAX_FREQUENCY_KHZ) {
        snprintf(s_edit_error, sizeof s_edit_error,
                 "ENTER 024.000 TO 1766.000 MHz");
        draw_add_frequency();
        return;
    }
    ow_status status = ow_scripting_app_signals_app_signal_set(
        &s_dev, "wr_state", (double)s_edit_frequency_khz);
    DIAG("waverider: add saved request khz=%u status=%d\n",
         (unsigned)s_edit_frequency_khz, (int)status);
    if (status != OW_OK) {
        s_link_ok = false;
        snprintf(s_edit_error, sizeof s_edit_error, "CM0 LINK FAILED; TRY AGAIN");
        draw_add_frequency();
        return;
    }
    s_ui_mode = UI_LISTS_LOADING;
    draw_library_loading("SAVING FREQUENCY");
    send_command(1, 0);
}

static void draw_delete_confirmation(void) {
    char frequency[16];
    format_frequency(frequency, sizeof frequency, s_freqs[s_cursor]);
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(384, 5, 2, COL_RED, COL_BG, "DELETE");
    fb_fill_rect(24, 58, 432, 176, COL_PANEL);
    fb_draw_text(58, 78, 2, COL_RED, COL_PANEL, "DELETE SAVED FREQUENCY?");
    fb_draw_text(138, 120, 3, COL_WHITE, COL_PANEL, frequency);
    fb_draw_text(64, 166, 1, COL_YELLOW, COL_PANEL,
                 "THIS ALSO REMOVES IT FROM THE LIVE LIST");
    fb_draw_text(96, 198, 1, COL_BLUE, COL_PANEL,
                 "CHECK = DELETE     RED = CANCEL");
    s_fb_dirty = true;
}

static void draw_audio_page(void) {
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(396, 5, 2, COL_YELLOW, COL_BG, "AUDIO");
    fb_fill_rect(20, 48, 440, 208, COL_PANEL);
    fb_draw_text(42, 66, 2, COL_TEXT, COL_PANEL, "LIVE AUDIO MONITOR");
    fb_draw_text(42, 104, 2, COL_YELLOW, COL_PANEL,
                 "MONITOR     UNAVAILABLE");
    fb_draw_text(42, 135, 2, COL_DIM, COL_PANEL,
                 "VOLUME      --");
    fb_draw_text(42, 174, 1, COL_TEXT, COL_PANEL,
                 "THE SDR RECEIVER REMAINS MUTED.");
    fb_draw_text(42, 194, 1, COL_DIM, COL_PANEL,
                 "SAFE SPEAKER/HEADPHONE PCM TRANSPORT");
    fb_draw_text(42, 210, 1, COL_DIM, COL_PANEL,
                 "IS REQUIRED BEFORE CONTROLS UNLOCK.");
    fb_draw_text(42, 232, 1, COL_BLUE, COL_PANEL,
                 "WATERFALL AND CW DECODING STAY LIVE");
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, "OFF", COL_DIM);
    draw_button(2, "VOL-", COL_DIM);
    draw_button(3, "VOL+", COL_DIM);
    draw_button(4, "LOCKED", COL_YELLOW);
    s_fb_dirty = true;
}

static uint8_t span_profile_index(void) {
    uint32_t active_span = s_requested_span != 0u ? s_requested_span : s_span;
    uint8_t nearest = 0u;
    uint32_t nearest_delta = UINT32_MAX;
    for (uint8_t index = 0u; index < SPAN_PROFILE_COUNT; index++) {
        if (s_span_profiles_hz[index] == active_span) return index;
        uint32_t value = s_span_profiles_hz[index];
        uint32_t delta = value > active_span ? value - active_span
                                             : active_span - value;
        if (delta < nearest_delta) {
            nearest = index;
            nearest_delta = delta;
        }
    }
    return nearest;
}

static void format_span_label(char *out, size_t cap, uint32_t span_hz) {
    if (span_hz >= 1000000u)
        snprintf(out, cap, "%lu MHz", (unsigned long)(span_hz / 1000000u));
    else
        snprintf(out, cap, "%lu kHz", (unsigned long)(span_hz / 1000u));
}

static void draw_waterfall_span(void) {
    static const char *labels[SPAN_PROFILE_COUNT] = {
        "25K", "100K", "200K", "500K", "1M", "2M",
    };
    const int track_x = 52;
    const int track_y = 151;
    const int track_step = 75;
    uint8_t selected = span_profile_index();
    int marker_x = track_x + selected * track_step;
    char value[24];

    format_span_label(value, sizeof value, s_span_profiles_hz[selected]);
    int value_width = (int)strlen(value) * 18;
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(294, 5, 2, COL_BLUE, COL_BG, "WATERFALL SPAN");
    fb_fill_rect(20, 48, 440, 208, COL_PANEL);
    fb_draw_text(42, 63, 1, COL_DIM, COL_PANEL, "VISIBLE RECEIVER BANDWIDTH");
    fb_draw_text(240 - value_width / 2, 82, 3, COL_WHITE, COL_PANEL, value);

    for (int x = track_x; x <= track_x + 5 * track_step; x++) {
        int relative = x - track_x;
        uint16_t color = rssi_color(relative * (SCALE_W - 1) /
                                    (5 * track_step));
        fb_fill_rect(x, track_y, 1, 6, color);
    }
    for (uint8_t index = 0u; index < SPAN_PROFILE_COUNT; index++) {
        int x = track_x + index * track_step;
        uint16_t tick = index == selected ? COL_WHITE : COL_BORDER;
        fb_fill_rect(x - 2, track_y - 6, 5, 18, tick);
        int label_width = (int)strlen(labels[index]) * 6;
        fb_draw_text(x - label_width / 2, 169, 1,
                     index == selected ? COL_WHITE : COL_DIM,
                     COL_PANEL, labels[index]);
    }
    fb_fill_triangle(marker_x, track_y - 16, marker_x - 7, track_y - 25,
                     marker_x + 7, track_y - 25, COL_WHITE);
    fb_draw_text(50, 202, 1, COL_BLUE, COL_PANEL,
                 "NARROW = MORE DETAIL    WIDE = MORE CONTEXT");
    fb_draw_text(72, 226, 1, COL_DIM, COL_PANEL,
                 "LEFT/RIGHT RETUNES AND SAVES THIS FREQUENCY");
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, "NARROW", COL_YELLOW);
    draw_button(2, "DONE", COL_GREEN);
    draw_button(3, "WIDER", COL_BLUE);
    draw_button(4, "LIVE", COL_RED);
    s_fb_dirty = true;
}

static void set_span_profile(uint8_t index) {
    if (index >= SPAN_PROFILE_COUNT) return;
    uint32_t requested = s_span_profiles_hz[index];
    uint32_t current = s_requested_span != 0u ? s_requested_span : s_span;
    if (requested == current) {
        draw_waterfall_span();
        return;
    }
    s_requested_span = requested;
    /* Opcode zero reserves arguments 4-9 for the six documented spans. */
    send_command(0u, (uint8_t)(4u + index));
    draw_waterfall_span();
}

static void adjust_span_profile(int delta) {
    int index = (int)span_profile_index() + delta;
    if (index < 0) index = 0;
    if (index >= (int)SPAN_PROFILE_COUNT) index = SPAN_PROFILE_COUNT - 1;
    if ((uint8_t)index != span_profile_index())
        set_span_profile((uint8_t)index);
    else
        draw_waterfall_span();
}

static void draw_setting_row(int row, const char *title, const char *detail,
                             uint16_t accent) {
    int y = 43 + row * 53;
    uint16_t background = row == (int)s_settings_cursor ? COL_SELECT : COL_PANEL;
    fb_fill_rect(24, y, 432, 46, background);
    fb_fill_rect(24, y, 4, 46, accent);
    fb_draw_text(42, y + 4, 2, COL_TEXT, background, title);
    fb_draw_text(42, y + 28, 1, accent, background, detail);
    if (row == (int)s_settings_cursor)
        fb_draw_text(430, y + 14, 2, COL_WHITE, background, ">");
}

static void draw_settings(void) {
    char detail[48];
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(350, 5, 2, COL_GREEN, COL_BG, "SETTINGS");
    draw_setting_row(0, "AUDIO MONITOR",
                     "LOCKED - PCM BRIDGE REQUIRED", COL_YELLOW);
    format_span_label(detail, sizeof detail,
                      s_requested_span != 0u ? s_requested_span : s_span);
    char span_detail[48];
    snprintf(span_detail, sizeof span_detail, "VISIBLE WIDTH %s", detail);
    draw_setting_row(1, "WATERFALL SPAN", span_detail, COL_BLUE);
    snprintf(detail, sizeof detail, "%s  THRESHOLD %ld dBFS",
             s_alert_enabled ? "ON " : "OFF",
             (long)(s_alert_threshold_tenths / 10));
    draw_setting_row(2, "POCKET ALERT", detail,
                     s_alert_enabled ? COL_GREEN : COL_DIM);
    snprintf(detail, sizeof detail, "%s  AUTO TONE 450-1150 HZ",
             s_cw_enabled ? "ON " : "OFF");
    draw_setting_row(3, "CW DECODER", detail,
                     s_cw_enabled ? COL_BLUE : COL_DIM);
    fb_draw_text(24, 264, 1, COL_DIM, COL_BG,
                 "UP/DOWN SELECT   CHECK OPEN   PAGE BACK");
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, "PREV", COL_YELLOW);
    draw_button(2, "OPEN", COL_GREEN);
    draw_button(3, "NEXT", COL_BLUE);
    draw_button(4, "LIVE", COL_RED);
    s_fb_dirty = true;
}

static void open_selected_setting(void) {
    if (s_settings_cursor == 0u) {
        s_ui_mode = UI_AUDIO;
        draw_audio_page();
    } else if (s_settings_cursor == 1u) {
        s_ui_mode = UI_WATERFALL_SPAN;
        draw_waterfall_span();
    } else if (s_settings_cursor == 2u) {
        s_ui_mode = UI_POCKET_ALERT;
        draw_pocket_alert();
    } else {
        s_ui_mode = UI_CW_DECODER;
        draw_cw_decoder();
    }
}

static void move_settings_cursor(int delta) {
    s_settings_cursor = (uint8_t)((s_settings_cursor + 4 + delta) % 4);
    draw_settings();
}

static void set_cw_enabled(bool enabled) {
    s_cw_enabled = enabled;
    /* Opcode zero carries infrequent global actions. Argument one already
     * clears message history; two/three persist decoder off/on on CM0. */
    send_command(0u, enabled ? 3u : 2u);
    draw_cw_decoder();
}

static void draw_cw_decoder(void) {
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(330, 5, 2, COL_BLUE, COL_BG, "CW DECODER");
    fb_fill_rect(20, 48, 440, 208, COL_PANEL);
    fb_draw_text(42, 66, 2, COL_TEXT, COL_PANEL,
                 "MORSE MESSAGE DETECTION");
    fb_draw_text(42, 106, 2,
                 s_cw_enabled ? COL_GREEN : COL_DIM, COL_PANEL,
                 s_cw_enabled ? "DECODER     ENABLED" : "DECODER     DISABLED");
    fb_draw_text(42, 141, 1, COL_TEXT, COL_PANEL,
                 "NFM TONE    AUTO 450-1150 HZ");
    fb_draw_text(42, 166, 1, COL_DIM, COL_PANEL,
                 "DISABLING STOPS NEW MESSAGE PROCESSING.");
    fb_draw_text(42, 184, 1, COL_DIM, COL_PANEL,
                 "EXISTING VERIFIED HISTORY IS RETAINED.");
    fb_draw_text(42, 220, 1, COL_BLUE, COL_PANEL,
                 "CHECK OR TOGGLE CHANGES THIS SETTING");
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, s_cw_enabled ? "DISABLE" : "ENABLE", COL_YELLOW);
    draw_button(2, "TOGGLE", COL_GREEN);
    draw_button(3, "", COL_BLUE);
    draw_button(4, "LIVE", COL_RED);
    s_fb_dirty = true;
}

static uint8_t message_frequency_count(void) {
    uint32_t seen[MESSAGE_HISTORY_MAX];
    uint8_t count = 0u;
    for (int history = (int)s_message_history_count - 1; history >= 0; history--) {
        uint32_t frequency = s_message_history[history].frequency_khz;
        bool duplicate = false;
        for (uint8_t index = 0u; index < count; index++) {
            if (seen[index] == frequency) {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) seen[count++] = frequency;
    }
    return count;
}

static uint32_t message_frequency_at(uint8_t selected) {
    uint32_t seen[MESSAGE_HISTORY_MAX];
    uint8_t count = 0u;
    for (int history = (int)s_message_history_count - 1; history >= 0; history--) {
        uint32_t frequency = s_message_history[history].frequency_khz;
        bool duplicate = false;
        for (uint8_t index = 0u; index < count; index++) {
            if (seen[index] == frequency) {
                duplicate = true;
                break;
            }
        }
        if (duplicate) continue;
        if (count == selected) return frequency;
        seen[count++] = frequency;
    }
    return 0u;
}

static uint8_t message_count_for_frequency(uint32_t frequency_khz) {
    uint8_t count = 0u;
    for (uint8_t index = 0u; index < s_message_history_count; index++) {
        if (s_message_history[index].frequency_khz == frequency_khz) count++;
    }
    return count;
}

static void select_latest_message_for_frequency(uint32_t frequency_khz) {
    for (int index = (int)s_message_history_count - 1; index >= 0; index--) {
        if (s_message_history[index].frequency_khz == frequency_khz) {
            s_message_history_cursor = (uint8_t)index;
            return;
        }
    }
}

static void step_message_for_frequency(int delta) {
    if (s_message_history_count == 0u) return;
    uint32_t frequency =
        s_message_history[s_message_history_cursor].frequency_khz;
    int index = s_message_history_cursor;
    for (uint8_t attempts = 0u; attempts < s_message_history_count; attempts++) {
        index = (index + delta + s_message_history_count) % s_message_history_count;
        if (s_message_history[index].frequency_khz == frequency) {
            s_message_history_cursor = (uint8_t)index;
            return;
        }
    }
}

static void draw_message_frequencies(void) {
    char line[48];
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(300, 5, 2, COL_GREEN, COL_BG, "MSG FREQUENCIES");
    fb_fill_rect(14, 38, 452, 235, COL_PANEL);
    uint8_t frequency_count = message_frequency_count();
    if (frequency_count == 0u) {
        s_message_frequency_cursor = 0u;
        fb_draw_text(82, 88, 3, COL_YELLOW, COL_PANEL, "NO MESSAGES YET");
        fb_draw_text(58, 142, 1, COL_TEXT, COL_PANEL,
                     "VERIFIED CW MESSAGES WILL BE GROUPED BY FREQUENCY");
        fb_draw_text(58, 162, 1, COL_DIM, COL_PANEL,
                     "UNVERIFIED CANDIDATES ARE NOT SHOWN");
    } else {
        if (s_message_frequency_cursor >= frequency_count)
            s_message_frequency_cursor = frequency_count - 1u;
        uint8_t first = s_message_frequency_cursor >= 7u
                            ? s_message_frequency_cursor - 7u
                            : 0u;
        for (uint8_t row = 0u; row < 8u && first + row < frequency_count; row++) {
            uint8_t selected = first + row;
            uint32_t frequency_khz = message_frequency_at(selected);
            uint16_t y = (uint16_t)(48u + row * 25u);
            bool active = selected == s_message_frequency_cursor;
            if (active) fb_fill_rect(24, y - 2u, 432, 23, COL_SELECT);
            char frequency[16];
            format_frequency(frequency, sizeof frequency, frequency_khz * 1000u);
            fb_draw_text(36, y, 2, active ? COL_WHITE : COL_TEXT,
                         active ? COL_SELECT : COL_PANEL, frequency);
            snprintf(line, sizeof line, "%u MESSAGE%s",
                     (unsigned)message_count_for_frequency(frequency_khz),
                     message_count_for_frequency(frequency_khz) == 1u ? "" : "S");
            fb_draw_text(292, y + 3u, 1, active ? COL_GREEN : COL_DIM,
                         active ? COL_SELECT : COL_PANEL, line);
        }
        fb_draw_text(26, 253, 1, COL_DIM, COL_PANEL,
                     "SELECT A FREQUENCY, THEN OPEN ITS MESSAGE LIST");
    }
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, "PREV", COL_YELLOW);
    draw_button(2, "OPEN", COL_GREEN);
    draw_button(3, "NEXT", COL_BLUE);
    draw_button(4, "CLEAR", COL_RED);
    s_fb_dirty = true;
}

static void draw_messages(void) {
    char line[64];
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(370, 5, 2, COL_GREEN, COL_BG, "MESSAGES");
    fb_fill_rect(14, 38, 452, 235, COL_PANEL);
    if (s_message_history_count == 0u) {
        fb_draw_text(82, 88, 3, COL_YELLOW, COL_PANEL, "NO MESSAGES YET");
        fb_draw_text(68, 142, 1, COL_TEXT, COL_PANEL,
                     "CW DETECTIONS WILL REMAIN AVAILABLE HERE");
        fb_draw_text(68, 162, 1, COL_DIM, COL_PANEL,
                     "THE CM0 RESTORES RECENT HISTORY AFTER REBOOT");
    } else {
        if (s_message_history_cursor >= s_message_history_count)
            s_message_history_cursor = s_message_history_count - 1u;
        message_record_t *record =
            &s_message_history[s_message_history_cursor];
        uint32_t selected_frequency = record->frequency_khz;
        uint8_t frequency_total = message_count_for_frequency(selected_frequency);
        uint8_t frequency_position = 0u;
        for (uint8_t index = 0u; index <= s_message_history_cursor; index++) {
            if (s_message_history[index].frequency_khz == selected_frequency)
                frequency_position++;
        }
        snprintf(line, sizeof line, "MESSAGE %u OF %u ON THIS FREQUENCY",
                 (unsigned)frequency_position, (unsigned)frequency_total);
        fb_draw_text(26, 49, 1, COL_DIM, COL_PANEL, line);
        char frequency[16];
        format_frequency(frequency, sizeof frequency,
                         record->frequency_khz * 1000u);
        fb_draw_text(26, 68, 3, COL_WHITE, COL_PANEL, frequency);
        snprintf(line, sizeof line, "SEEN %s   REPEATS %u   QUALITY %u%%",
                 record->seen_time, (unsigned)record->repeat_count,
                 (unsigned)record->confidence_percent);
        fb_draw_text(244, 76, 1, COL_GREEN, COL_PANEL, line);
        fb_fill_rect(26, 108, 420, 1, COL_BORDER);
        /* The decoded payload is the reason this page exists.  Render it at
         * the larger glance-readable size and wrap on words when possible.
         * Five 34-character rows can still hold every byte transported by
         * MESSAGE_TEXT_BYTES, so readability does not truncate history. */
        int offset = 0;
        for (int row = 0; row < 5 && record->text[offset] != '\0'; row++) {
            char text_line[35];
            int remaining = (int)strlen(&record->text[offset]);
            int count = remaining < 34 ? remaining : 34;
            if (remaining > 34) {
                int word_break = count;
                while (word_break > 0 &&
                       record->text[offset + word_break] != ' ')
                    word_break--;
                if (word_break > 0) count = word_break;
            }
            memcpy(text_line, &record->text[offset], (size_t)count);
            text_line[count] = '\0';
            fb_draw_text(26, 118 + row * 25, 2, COL_TEXT, COL_PANEL,
                         text_line);
            offset += count;
            while (record->text[offset] == ' ') offset++;
        }
        fb_draw_text(26, 253, 1, COL_DIM, COL_PANEL,
                     "UP/DOWN OR PREV/NEXT STAYS ON THIS FREQUENCY");
    }
    draw_button(0, "FREQS", COL_TEXT);
    draw_button(1, "PREV", COL_YELLOW);
    draw_button(2, "NEXT", COL_GREEN);
    draw_button(3, "", COL_BLUE);
    draw_button(4, "LIVE", COL_RED);
    s_fb_dirty = true;
}

static void draw_message_clear_confirmation(void) {
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(368, 5, 2, COL_RED, COL_BG, "CLEAR");
    fb_fill_rect(24, 58, 432, 176, COL_PANEL);
    fb_draw_text(78, 82, 2, COL_RED, COL_PANEL, "CLEAR ALL MESSAGE HISTORY?");
    fb_draw_text(58, 126, 1, COL_TEXT, COL_PANEL,
                 "THIS REMOVES VERIFIED MESSAGES AND CANDIDATES");
    fb_draw_text(58, 150, 1, COL_YELLOW, COL_PANEL,
                 "THE ACTION CANNOT BE UNDONE");
    fb_draw_text(74, 198, 1, COL_BLUE, COL_PANEL,
                 "CHECK = CLEAR     RED OR BACK = CANCEL");
    draw_button(0, "CANCEL", COL_TEXT);
    draw_button(1, "", COL_YELLOW);
    draw_button(2, "CLEAR", COL_RED);
    draw_button(3, "", COL_BLUE);
    draw_button(4, "CANCEL", COL_RED);
    s_fb_dirty = true;
}

static void clear_message_history(void) {
    memset(s_message_history, 0, sizeof s_message_history);
    s_message_history_count = 0u;
    s_message_history_cursor = 0u;
    s_message_frequency_cursor = 0u;
    s_detected_message[0] = '\0';
    s_message_until_us = 0u;
    /* Opcode zero was deliberately left unused by the existing command
     * protocol. Argument one means clear the complete CM0 message store,
     * including candidates that are intentionally hidden from this page. */
    send_command(0u, 1u);
    s_ui_mode = UI_MESSAGE_FREQUENCIES;
    draw_message_frequencies();
}

static void haptic_set(bool on) {
#if HAPTIC_GPIO35_VERIFIED
    s_haptic_on = on;
    gpio_put(PIN_HAPTIC, on ? 1u : 0u);
    busy_wait_us_32(5u);
    DIAG("waverider: haptic gpio=%u requested=%u latch=%u pad=%u\n",
         (unsigned)PIN_HAPTIC, on ? 1u : 0u,
         (unsigned)gpio_get_out_level(PIN_HAPTIC),
         (unsigned)gpio_get(PIN_HAPTIC));
#else
    (void)on;
    s_haptic_on = false;
#endif
}

static void haptic_start_three_pulses(void) {
#if HAPTIC_GPIO35_VERIFIED
    s_haptic_pulses_remaining = 3u;
    haptic_set(true);
    s_haptic_deadline_us = time_us_64() + HAPTIC_PULSE_ON_US;
#else
    s_haptic_pulses_remaining = 0u;
    haptic_set(false);
    DIAG("waverider: haptic unavailable; GPIO35 field path is disabled\n");
#endif
}

static void haptic_test_three_pulses(void) {
#if HAPTIC_GPIO35_VERIFIED
    /* Use three 150 ms pulses and 80 ms gaps, scheduled through WaveRider's
     * nonblocking state machine. The former sleep loop stopped servicing
     * OneWili for 690 ms and could discard live SDR/command traffic. */
    DIAG("waverider: nonblocking GPIO35 haptic TEST begin\n");
    haptic_start_three_pulses();
#endif
}

static void haptic_task(uint64_t now) {
    if (s_haptic_pulses_remaining == 0u || now < s_haptic_deadline_us) return;
    if (s_haptic_on) {
        haptic_set(false);
        s_haptic_pulses_remaining--;
        if (s_haptic_pulses_remaining > 0u)
            s_haptic_deadline_us = now + HAPTIC_PULSE_OFF_US;
    } else {
        haptic_set(true);
        s_haptic_deadline_us = now + HAPTIC_PULSE_ON_US;
    }
}

static uint8_t haptic_probe_pin(void) {
    return s_haptic_probe_pins[s_haptic_probe_index];
}

static void haptic_probe_restore(void) {
    if (!s_haptic_probe_saved) return;
    uint8_t pin = haptic_probe_pin();
    /* Restore the complete IO mux and pad state captured before the touch.
     * The probe never enables SIO output, so no output latch needs changing. */
    io_bank0_hw->io[pin].ctrl = s_haptic_probe_saved_ctrl;
    pads_bank0_hw->io[pin] = s_haptic_probe_saved_pad;
    s_haptic_probe_saved = false;
}

static void haptic_probe_apply_pull(bool pull_up) {
    uint8_t pin = haptic_probe_pin();
    haptic_probe_restore();
    s_haptic_probe_saved_ctrl = io_bank0_hw->io[pin].ctrl;
    s_haptic_probe_saved_pad = pads_bank0_hw->io[pin];
    s_haptic_probe_saved = true;
    gpio_set_function(pin, GPIO_FUNC_SIO);
    gpio_set_dir(pin, GPIO_IN);
    gpio_disable_pulls(pin);
    if (pull_up)
        gpio_pull_up(pin);
    else
        gpio_pull_down(pin);
    DIAG("waverider: weak haptic probe gpio=%u pull=%s pad=%u\n",
         (unsigned)pin, pull_up ? "up" : "down", (unsigned)gpio_get(pin));
}

static void haptic_probe_start(void) {
    if (s_haptic_probe_phase != 0u) return;
    haptic_probe_apply_pull(true);
    s_haptic_probe_phase = 1u;
    s_haptic_probe_deadline_us = time_us_64() + HAPTIC_PROBE_TOUCH_US;
    draw_haptic_probe();
}

static void haptic_probe_task(uint64_t now) {
    if (s_haptic_probe_phase == 0u || now < s_haptic_probe_deadline_us) return;
    if (s_haptic_probe_phase == 1u) {
        haptic_probe_restore();
        s_haptic_probe_phase = 2u;
        s_haptic_probe_deadline_us = now + HAPTIC_PROBE_GAP_US;
    } else if (s_haptic_probe_phase == 2u) {
        haptic_probe_apply_pull(false);
        s_haptic_probe_phase = 3u;
        s_haptic_probe_deadline_us = now + HAPTIC_PROBE_TOUCH_US;
    } else {
        haptic_probe_restore();
        s_haptic_probe_phase = 0u;
    }
    draw_haptic_probe();
}

static void haptic_probe_select(int delta) {
    if (s_haptic_probe_phase != 0u) return;
    int count = (int)(sizeof s_haptic_probe_pins / sizeof s_haptic_probe_pins[0]);
    s_haptic_probe_index = (uint8_t)((s_haptic_probe_index + count + delta) % count);
    draw_haptic_probe();
}

static void leave_haptic_probe(void) {
    haptic_probe_restore();
    s_haptic_probe_phase = 0u;
    s_ui_mode = UI_POCKET_ALERT;
    draw_pocket_alert();
}

static void draw_haptic_probe(void) {
    char line[48];
    const char *phase = "READY - PRESS TEST";
    uint16_t phase_color = COL_GREEN;
    if (s_haptic_probe_phase == 1u) {
        phase = "WEAK PULL-UP TOUCH";
        phase_color = COL_YELLOW;
    } else if (s_haptic_probe_phase == 2u) {
        phase = "FLOATING GAP";
        phase_color = COL_DIM;
    } else if (s_haptic_probe_phase == 3u) {
        phase = "WEAK PULL-DOWN TOUCH";
        phase_color = COL_BLUE;
    }
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(310, 5, 2, COL_YELLOW, COL_BG, "PIN PROBE");
    fb_fill_rect(20, 48, 440, 208, COL_PANEL);
    fb_draw_text(42, 66, 2, COL_TEXT, COL_PANEL, "HAPTIC WEAK-PULL DIAGNOSTIC");
    snprintf(line, sizeof line, "CANDIDATE      GPIO %u", (unsigned)haptic_probe_pin());
    fb_draw_text(42, 108, 3, COL_WHITE, COL_PANEL, line);
    snprintf(line, sizeof line, "PIN %u OF %u", (unsigned)s_haptic_probe_index + 1u,
             (unsigned)(sizeof s_haptic_probe_pins / sizeof s_haptic_probe_pins[0]));
    fb_draw_text(42, 145, 1, COL_DIM, COL_PANEL, line);
    fb_draw_text(42, 174, 2, phase_color, COL_PANEL, phase);
    fb_draw_text(42, 207, 1, COL_DIM, COL_PANEL,
                 "INPUT ONLY: PULL-UP, FLOAT, PULL-DOWN, RESTORE");
    fb_draw_text(42, 225, 1, COL_DIM, COL_PANEL,
                 "LEFT/RIGHT SELECT   GREEN OR RED TEST");
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, "PREV", COL_YELLOW);
    draw_button(2, "TEST", COL_GREEN);
    draw_button(3, "NEXT", COL_BLUE);
    draw_button(4, "TEST", COL_RED);
    s_fb_dirty = true;
}

static void pocket_alert_sample(uint64_t now) {
#if !HAPTIC_GPIO35_VERIFIED
    (void)now;
    s_alert_enabled = false;
    s_alert_armed = true;
    return;
#endif
    if (!s_alert_enabled) {
        s_alert_armed = true;
        return;
    }
    if (s_rssi_tenths <=
        s_alert_threshold_tenths - HAPTIC_REARM_HYSTERESIS_TENTHS) {
        s_alert_armed = true;
        return;
    }
    if (s_alert_armed && s_rssi_tenths >= s_alert_threshold_tenths) {
        /* Consume this crossing even during cooldown. A steady carrier can
         * never wake the motor every 30 seconds; RSSI must first fall 3 dB
         * below the threshold and cross it again after the cooldown. */
        s_alert_armed = false;
        if (s_last_alert_us == 0u ||
            now - s_last_alert_us >= HAPTIC_ALERT_COOLDOWN_US) {
            s_last_alert_us = now;
            haptic_start_three_pulses();
        }
    }
}

static void draw_pocket_alert_dynamic(void) {
    char line[48];
    char value[20];
    uint64_t now = time_us_64();
    /* Repaint only live values. Clearing the complete framebuffer for every
     * SDR row exposed a blank intermediate frame during the asynchronous LCD
     * transfer, which made this page flash continuously. */
    fb_fill_rect(36, 94, 408, 150, COL_PANEL);

    snprintf(line, sizeof line, "ALERT       %s",
             HAPTIC_GPIO35_VERIFIED
                 ? (s_alert_enabled ? "ENABLED" : "DISABLED")
                 : "UNAVAILABLE");
    fb_draw_text(42, 101, 2,
                 s_alert_enabled ? COL_GREEN : COL_DIM, COL_PANEL, line);
    format_tenths(value, sizeof value, s_alert_threshold_tenths);
    snprintf(line, sizeof line, "THRESHOLD   %s dBFS", value);
    fb_draw_text(42, 132, 2, COL_YELLOW, COL_PANEL, line);
    format_tenths(value, sizeof value, s_rssi_tenths);
    snprintf(line, sizeof line, "CURRENT     %s dBFS", value);
    fb_draw_text(42, 163, 2, COL_TEXT, COL_PANEL, line);

    const char *state = "GPIO35 VERIFIED / 12mA";
    uint16_t state_color = COL_YELLOW;
    if (!HAPTIC_GPIO35_VERIFIED) {
        state = "DRIVER DISABLED";
    } else if (s_haptic_pulses_remaining > 0u) {
        state = s_haptic_on ? "TEST: GPIO35 OUTPUT HIGH" : "TEST: PULSE GAP";
        state_color = COL_YELLOW;
    } else if (s_alert_enabled) {
        state = s_alert_armed ? "ARMED" : "WAITING FOR SIGNAL TO FALL";
        state_color = s_alert_armed ? COL_GREEN : COL_BLUE;
    }
    snprintf(line, sizeof line, "STATE       %s", state);
    fb_draw_text(42, 195, 1, state_color, COL_PANEL, line);
    uint32_t cooldown = 0u;
    if (s_last_alert_us != 0u && now - s_last_alert_us < HAPTIC_ALERT_COOLDOWN_US)
        cooldown = (uint32_t)((HAPTIC_ALERT_COOLDOWN_US -
                              (now - s_last_alert_us) + 999999u) / 1000000u);
    if (HAPTIC_GPIO35_VERIFIED)
        snprintf(line, sizeof line,
                 "3 X 150 MS   30 SEC COOLDOWN   READY %lu SEC",
                 (unsigned long)cooldown);
    else
        snprintf(line, sizeof line,
                 "VISUAL RSSI / WATERFALL / LEDS ARE ACTIVE");
    fb_draw_text(42, 223, 1, COL_DIM, COL_PANEL, line);
    s_fb_dirty = true;
}

static void draw_pocket_alert(void) {
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);
    fb_draw_text(8, 2, 3, COL_TEXT, COL_BG, "WaveRider");
    fb_draw_text(316, 5, 2, COL_GREEN, COL_BG, "POCKET ALERT");
    fb_fill_rect(20, 48, 440, 208, COL_PANEL);
    fb_draw_text(42, 66, 2, COL_TEXT, COL_PANEL, "HAPTIC SIGNAL DETECTOR");
    draw_pocket_alert_dynamic();
    draw_button(0, "BACK", COL_TEXT);
    draw_button(1, HAPTIC_GPIO35_VERIFIED
                       ? (s_alert_enabled ? "DISABLE" : "ENABLE")
                       : "UNAVAILABLE", COL_YELLOW);
    draw_button(2, "-1 dB", COL_GREEN);
    draw_button(3, "+1 dB", COL_BLUE);
    draw_button(4, HAPTIC_GPIO35_VERIFIED ? "TEST" : "INFO", COL_RED);
    s_fb_dirty = true;
}

static void set_alert_enabled(bool enabled) {
#if !HAPTIC_GPIO35_VERIFIED
    (void)enabled;
    s_alert_enabled = false;
    s_alert_armed = true;
    draw_pocket_alert();
    return;
#endif
    s_alert_enabled = enabled;
    s_alert_armed = true;
    send_command(14, enabled ? 1u : 0u);
    draw_pocket_alert();
}

static void adjust_alert_threshold(int delta_db) {
    int32_t next = s_alert_threshold_tenths + delta_db * 10;
    if (next < -700) next = -700;
    if (next > -100) next = -100;
    s_alert_threshold_tenths = next;
    s_alert_armed = true;
    /* wr_state is the established one-shot value channel; encode the integer
     * threshold as an offset from -90 dBFS and then commit with opcode 15. */
    ow_status status = ow_scripting_app_signals_app_signal_set(
        &s_dev, "wr_state", (double)(s_alert_threshold_tenths / 10 + 90));
    s_link_ok = status == OW_OK;
    if (status == OW_OK) send_command(15, 0);
    draw_pocket_alert_dynamic();
}

static void update_health_ui(void) {
    uint64_t now = time_us_64();
    if (s_message_until_us != 0u && now >= s_message_until_us) {
        s_message_until_us = 0u;
        s_detected_message[0] = '\0';
        if (s_ui_mode == UI_LIVE) draw_list();
    }
    bool stale = s_last_row_us == 0 || now - s_last_row_us > 3000000u;
    if (s_ui_mode == UI_STARTUP && s_last_row_us == 0u &&
        !s_startup_refresh_attempted && s_mode_started_us != 0u &&
        now - s_mode_started_us >= 30000000u) {
        /* A refresh command is idempotent and remains in wr_cmd until CM0
         * acknowledges it. Queue one automatically before declaring startup
         * stalled, so a live-but-idle service gets a recovery opportunity
         * without making the user guess whether Refresh is safe. */
        s_startup_refresh_attempted = true;
        send_command(5, 0);
    }
    if (s_ui_mode == UI_LIVE && stale) {
        s_ui_mode = UI_FAULT;
        s_mode_started_us = now;
        draw_receiver_status();
    }
}

static void enter_live_view(bool clear_plot) {
    bool first_ready = s_ui_mode == UI_STARTUP;
    s_ui_mode = UI_LIVE;
    /* Confirm the seventh/final milestone independently of the waterfall.
     * Fast warm boots can cross mailbox, list, and first-row milestones
     * between two 250 ms LED refreshes, so keep all seven green long enough
     * to be unmistakable without delaying live rendering. */
    if (first_ready) s_ready_led_until_us = time_us_64() + 3000000u;
    draw_static();
    draw_list();
    draw_dynamic();
    if (clear_plot)
        fb_fill_rect(PLOT_X, PLOT_Y, PLOT_W, PLOT_H, rgb565_be(0, 0, 35));
    s_fb_dirty = true;
}

static void begin_refresh(void) {
    s_ui_mode = UI_REFRESH;
    s_mode_started_us = time_us_64();
    s_refresh_from_seq = s_row_seq;
    draw_receiver_status();
    send_command(5, 0);
}

static void push_waterfall_row(uint16_t words[3]) {
    size_t row_bytes = (size_t)PLOT_W * sizeof(uint16_t);
    /* The plot sits inside a full-width framebuffer.  Preserve its 480-pixel
     * row stride by scrolling bottom-up one row at a time. */
    for (int y = PLOT_H - 1; y > 0; y--) {
        memmove(s_fb + (size_t)(PLOT_Y + y) * ST7796_W + PLOT_X,
                s_fb + (size_t)(PLOT_Y + y - 1) * ST7796_W + PLOT_X,
                row_bytes);
    }
    uint16_t *row = s_fb + (size_t)PLOT_Y * ST7796_W + PLOT_X;
    uint8_t levels[WATERFALL_BINS];
    for (int bin = 0; bin < WATERFALL_BINS; bin++) {
        levels[bin] =
            (uint8_t)((words[bin / 4] >> ((bin % 4) * 4)) & 0xFu);
    }
    /* Twelve mailbox bins are enough for narrowband hunting data but drawing
     * them as twelve 27-pixel rectangles exaggerates single-bin noise and
     * makes a clean carrier look like mismatched slabs. Interpolate between
     * measured bin centers so real peaks remain at their actual offset while
     * their visible energy cools continuously into neighboring frequencies. */
    for (int x = 0; x < PLOT_W; x++) {
        int position256 = x * (WATERFALL_BINS - 1) * 256 / (PLOT_W - 1);
        int lower = position256 / 256;
        int upper = lower + 1 < WATERFALL_BINS ? lower + 1 : lower;
        int fraction = position256 & 255;
        int level256 = levels[lower] * (256 - fraction) +
                       levels[upper] * fraction;
        row[x] = waterfall_color((uint8_t)((level256 + 128) / 256));
    }
    for (int y = PLOT_Y; y < PLOT_Y + PLOT_H; y++) {
        uint16_t *center = s_fb + (size_t)y * ST7796_W + PLOT_X + PLOT_W / 2;
        center[0] = COL_WHITE;
        center[1] = COL_WHITE;
    }
    s_fb_dirty = true;
}

static void receive_message_chunk(uint32_t metadata, uint32_t words[3],
                                  bool replay) {
    uint8_t length = (uint8_t)(metadata & 0xFFu);
    uint8_t index = (uint8_t)((metadata >> 8u) & 0xFFu);
    uint8_t chunks = (uint8_t)((metadata >> 16u) & 0xFFu);
    if (length <= MESSAGE_HEADER_BYTES || length > MESSAGE_MAX_BYTES || chunks == 0u ||
        chunks > 15u || index >= chunks)
        return;
    if (index == 0u || length != s_message_length ||
        chunks != s_message_chunks) {
        memset(s_message_staging, 0, sizeof s_message_staging);
        s_message_length = length;
        s_message_chunks = chunks;
        s_message_chunk_mask = 0u;
    }
    for (int word = 0; word < 3; word++) {
        for (int byte = 0; byte < 2; byte++) {
            uint32_t destination = (uint32_t)index * 6u +
                                   (uint32_t)word * 2u + (uint32_t)byte;
            if (destination < length)
                s_message_staging[destination] =
                    (char)((words[word] >> (byte * 8)) & 0xFFu);
        }
    }
    s_message_chunk_mask |= (uint16_t)(1u << index);
    uint16_t complete_mask = (uint16_t)((1u << chunks) - 1u);
    if (s_message_chunk_mask != complete_mask) return;
    s_message_staging[length] = '\0';
    const uint8_t *payload = (const uint8_t *)s_message_staging;
    uint32_t frequency_khz = (uint32_t)payload[0] |
                             ((uint32_t)payload[1] << 8u) |
                             ((uint32_t)payload[2] << 16u) |
                             ((uint32_t)payload[3] << 24u);
    if (frequency_khz < MIN_FREQUENCY_KHZ ||
        frequency_khz > MAX_FREQUENCY_KHZ)
        return;
    const char *text = s_message_staging + MESSAGE_HEADER_BYTES;
    uint8_t history_index = MESSAGE_HISTORY_MAX;
    for (uint8_t candidate = 0u; candidate < s_message_history_count;
         candidate++) {
        if (s_message_history[candidate].frequency_khz == frequency_khz &&
            strcmp(s_message_history[candidate].text, text) == 0) {
            history_index = candidate;
            break;
        }
    }
    if (history_index == MESSAGE_HISTORY_MAX) {
        if (s_message_history_count < MESSAGE_HISTORY_MAX) {
            history_index = s_message_history_count++;
        } else {
            memmove(&s_message_history[0], &s_message_history[1],
                    sizeof s_message_history[0] * (MESSAGE_HISTORY_MAX - 1u));
            history_index = MESSAGE_HISTORY_MAX - 1u;
        }
    }
    message_record_t *record = &s_message_history[history_index];
    memset(record, 0, sizeof *record);
    record->frequency_khz = frequency_khz;
    record->repeat_count = payload[4];
    record->confidence_percent = payload[5] > 100u ? 100u : payload[5];
    memcpy(record->seen_time, payload + 6u, 5u);
    record->seen_time[5] = '\0';
    strncpy(record->text, text, MESSAGE_TEXT_BYTES);
    record->text[MESSAGE_TEXT_BYTES] = '\0';
    s_message_history_cursor = history_index;
    if (!replay) {
        strncpy(s_detected_message, record->text, MESSAGE_TEXT_BYTES);
        s_detected_message[MESSAGE_TEXT_BYTES] = '\0';
        s_message_until_us = time_us_64() + MESSAGE_OVERLAY_US;
        DIAG("waverider: decoded Morse message '%s'\n", s_detected_message);
        if (s_ui_mode == UI_LIVE) draw_message_overlay();
    }
    if (s_ui_mode == UI_MESSAGES) draw_messages();
    else if (s_ui_mode == UI_MESSAGE_FREQUENCIES)
        draw_message_frequencies();
}

static void update_front_status_led(void) {
    /* Do not rebuild a complete Main awake mask from the live status bitmap.
     * USB-hub and CM0 control bits can be absent or transient while their
     * hardware is still active. Echoing that incomplete snapshot back merely
     * to clear the front status-LED bit can power down the RTL-SDR hub or
     * disturb the CM0 route. Pocket Alert therefore dims only WaveRider's
     * seven RGB LEDs; the independent front indicator remains unchanged until
     * Main exposes a dedicated, non-mask brightness/enable operation. */
    s_front_led_quiet_active = false;
    s_front_led_restore_enabled = false;
}

static void update_leds(void) {
    uint64_t now = time_us_64();
    /* Pocket Alert is intended for close, low-attention use. Preserve the
     * status/RSSI colors while reducing the strip to one eighth of the normal
     * brightness so the armed indicator does not destroy night vision. */
    ws2812_set_brightness(s_ui_mode == UI_POCKET_ALERT
                              ? LED_BRIGHTNESS_POCKET
                              : (s_ui_mode == UI_STARTUP
                                     ? LED_BRIGHTNESS_STARTUP
                                     : LED_BRIGHTNESS_NORMAL));
    update_front_status_led();
    ws2812_clear();
    if (now < s_ready_led_until_us) {
        for (int i = 0; i < 7; i++)
            ws2812_set_pixel((uint)i, (rgb_t){.r = 0, .g = 190, .b = 75});
        ws2812_show();
        return;
    }
    if (s_ui_mode == UI_STARTUP) {
        /* Calm, evidence-based startup progress. Each completed subsystem
         * adds one soft-green LED from left to right. Do not flash during a
         * healthy boot: yellow flashing is reserved for a real fault after
         * startup. The seventh LED appears with the ready/live transition. */
        int completed = (int)s_startup_stage + 1;
        if (completed < 1) completed = 1;
        if (completed > 6) completed = 6;
        rgb_t color = {.r = 0, .g = 70, .b = 28};
        for (int i = 0; i < completed; i++)
            ws2812_set_pixel((uint)i, color);
        ws2812_show();
        return;
    }
    if (s_ui_mode == UI_REFRESH) {
        int active = (int)((now / 150000u) % 7u);
        ws2812_set_pixel((uint)active, (rgb_t){.r = 220, .g = 150, .b = 0});
        ws2812_show();
        return;
    }
    if (s_ui_mode == UI_CREATOR_CREDITS) {
        int active = (int)((now / 100000u) % 12u);
        if (active > 6) active = 12 - active;
        for (int i = 0; i < 7; i++) {
            rgb_t color = {
                .r = (uint8_t)(18 + i * 21),
                .g = (uint8_t)(95 - i * 8),
                .b = (uint8_t)(130 - i * 4),
            };
            if (i == active)
                color = (rgb_t){.r = 180, .g = 180, .b = 180};
            ws2812_set_pixel((uint)i, color);
        }
        ws2812_show();
        return;
    }
    if (s_ui_mode == UI_LISTS_LOADING || s_ui_mode == UI_LISTS ||
        s_ui_mode == UI_DELETE_CONFIRM || s_ui_mode == UI_ADD_FREQUENCY ||
        s_ui_mode == UI_SETTINGS || s_ui_mode == UI_AUDIO ||
        s_ui_mode == UI_WATERFALL_SPAN || s_ui_mode == UI_CW_DECODER) {
        for (int i = 0; i < 7; i++)
            ws2812_set_pixel((uint)i, (rgb_t){.r = 0, .g = 70, .b = 110});
        ws2812_show();
        return;
    }
    if (s_last_row_us == 0 || now - s_last_row_us > 3000000u) {
        if (((now / 400000u) & 1u) == 0u) {
            for (int i = 0; i < 7; i++)
                ws2812_set_pixel((uint)i, (rgb_t){.r = 220, .g = 150, .b = 0});
        }
        ws2812_show();
        return;
    }
    int count = (s_rssi_tenths + 700) * 7 / 600;
    if (count < 0) count = 0;
    if (count > 7) count = 7;
    for (int i = 0; i < count; i++) {
        uint16_t color = rssi_color(i * (SCALE_W - 1) / 6);
        uint16_t native = BE16(color);
        rgb_t rgb = {
            .r = (uint8_t)(((native >> 11) & 0x1Fu) * 255u / 31u),
            .g = (uint8_t)(((native >> 5) & 0x3Fu) * 255u / 63u),
            .b = (uint8_t)((native & 0x1Fu) * 255u / 31u),
        };
        ws2812_set_pixel((uint)i, rgb);
    }
    ws2812_show();
}

static bool signal_get(const char *name, double *value) {
    char returned[32];
    bool primary_health = strcmp(name, "wr_seq") == 0;
    s_signal_get_calls++;
    ow_status status = ow_scripting_app_signals_app_signal_get(
        &s_dev, name, returned, sizeof returned, value);
    s_signal_get_last_status = status;
    if (status == OW_OK && strcmp(returned, name) == 0) {
        s_signal_get_ok++;
        /* Only a committed live-row sequence proves the receiver mailbox path
         * is healthy. List and settings signals can remain readable from
         * Main's cache while wr_seq is wedged; letting those replies clear the
         * recovery timer leaves the app on WAITING FOR CM0 BRIDGE forever. */
        if (primary_health) {
            s_signal_get_consecutive_failed = 0u;
            s_bridge_failed_since_us = 0u;
            s_main_reset_attempted = false;
        }
        s_link_ok = true;
        if (s_ui_mode == UI_STARTUP && s_startup_stage < 4u)
            s_startup_stage = 4u;
        return true;
    }
    s_signal_get_failed++;
    /* A normal "signal not found" response means Main is alive and CM0 has
     * not created the mailbox yet. Recover only transport-level failures;
     * otherwise a healthy, slow cold boot could be reset unnecessarily. */
    bool transport_failure = status == OW_ERR_TIMEOUT || status == OW_ERR_IO ||
                             status == OW_ERR_PROTOCOL;
    if (primary_health && transport_failure) {
        s_signal_get_consecutive_failed++;
        if (s_bridge_failed_since_us == 0u)
            s_bridge_failed_since_us = time_us_64();
        s_link_ok = false;
    } else if (primary_health) {
        s_signal_get_consecutive_failed = 0u;
        s_bridge_failed_since_us = 0u;
        s_link_ok = true;
    }
    if (s_signal_get_failed <= 4u || (s_signal_get_failed & 63u) == 0u) {
        uint8_t raw[48];
        size_t raw_len = ow_fwgui_last_response(raw, sizeof raw);
        DIAG("waverider: signal_get %s failed status=%d calls=%u ok=%u fail=%u rx=%u len=%u raw=",
             name, (int)status, (unsigned)s_signal_get_calls,
             (unsigned)s_signal_get_ok, (unsigned)s_signal_get_failed,
             (unsigned)ow_fwgui_response_frames(), (unsigned)raw_len);
        for (size_t i = 0; i < raw_len; i++) DIAG("%02x", raw[i]);
        DIAG("\n");
    }
    return false;
}

static void recover_bridge_link(uint64_t now) {
    if (s_bridge_failed_since_us == 0u ||
        s_signal_get_consecutive_failed < 8u)
        return;

    uint64_t elapsed = now - s_bridge_failed_since_us;
    if (elapsed >= BRIDGE_MAIN_RESET_AFTER_US && !s_main_reset_attempted) {
        /* WaveRider is still executing on Display, so this is not a user who
         * left for Linux Terminal. Reset Main only once; CM0 Linux, lists,
         * SDR capture, and Display all remain powered. The reset command may
         * time out because a successful reset intentionally drops its reply. */
        s_main_reset_attempted = true;
        DIAG("waverider: bridge transport stale; requesting Main-only reset\n");
        ow_status status = ow_hardware_settings_home_software_reset(&s_dev);
        DIAG("waverider: Main-only reset request status=%d\n", (int)status);
        s_bridge_reopen_at_us = now + 2000000u;
        return;
    }

    if (elapsed < BRIDGE_REOPEN_AFTER_US || now < s_bridge_reopen_at_us)
        return;

    /* Reinitialize the Display-to-Main UART parser before escalating to the
     * bounded Main-only reset. This is enough for ordinary USB/link loss and
     * avoids touching either processor when only the local transport wedged. */
    ow_close(&s_dev);
    ow_status status = fw2_app_recovery_open_onewili(&s_dev);
    if (status == OW_OK) {
        ow_set_timeout(&s_dev, 250u);
        ow_fwgui_set_power_mask_handler(apply_main_power_mask);
        ow_fwgui_set_power_zone_handler(apply_main_power_zone);
    }
    DIAG("waverider: bridge transport reopen status=%d\n", (int)status);
    s_bridge_reopen_at_us = now + BRIDGE_REOPEN_INTERVAL_US;
}

static bool signal_get_u32(const char *name, uint32_t *value) {
    double raw;
    if (!signal_get(name, &raw) || raw < 0.0) return false;
    *value = (uint32_t)(raw + 0.5);
    return true;
}

static void poll_list(void) {
    uint32_t sequence;
    if (!signal_get_u32("wr_lseq", &sequence) || sequence == s_list_seq) return;
    uint32_t state = 1u;
    uint32_t count;
    uint32_t selected = 0u;
    if (!signal_get_u32("wr_state", &state) ||
        !signal_get_u32("wr_count", &count) ||
        !signal_get_u32("wr_sel", &selected)) return;
    if (state == 1u) {
        s_alert_enabled = ((count >> 8u) & 1u) != 0u;
        s_cw_enabled = ((count >> 16u) & 1u) != 0u;
        int32_t threshold_dbfs = (int32_t)((count >> 9u) & 0x7Fu) - 90;
        if (threshold_dbfs >= -70 && threshold_dbfs <= -10)
            s_alert_threshold_tenths = threshold_dbfs * 10;
        count &= 0xFFu;
    }
    if (count > MAX_FREQS) count = MAX_FREQS;
    for (uint32_t i = 0; i < count; i++) {
        char name[12];
        uint32_t frequency;
        snprintf(name, sizeof name, "wr_f%lu", (unsigned long)i);
        if (signal_get_u32(name, &frequency) && frequency != 0) {
            s_freqs[i] = state == 2u ? frequency * 1000u : frequency;
        }
    }
    s_count = (int)count;
    if (s_count < 1) s_count = 1;
    if (selected >= (uint32_t)s_count) selected = 0u;
    s_cursor = (int)selected;
    s_list_seq = sequence;
    s_link_ok = true;
    if (s_ui_mode == UI_STARTUP && s_startup_stage < 5u)
        s_startup_stage = 5u;
    if (state == 2u) {
        uint32_t membership = 0u;
        uint32_t total = count;
        uint32_t offset = 0u;
        uint32_t notice = 0u;
        if (!signal_get_u32("wr_row0", &membership) ||
            !signal_get_u32("wr_row1", &total) ||
            !signal_get_u32("wr_row2", &offset) ||
            !signal_get_u32("wr_freq", &notice)) return;
        s_library_live_mask = (uint16_t)(membership & 0xFFFFu);
        s_live_count = (int)((membership >> 16u) & 0x1Fu);
        s_library_total = total;
        s_library_offset = offset;
        s_library_notice = notice;
        s_ui_mode = UI_LISTS;
        draw_library();
    } else {
        s_live_count = s_count;
        s_active = (int)selected;
        if (s_ui_mode == UI_LISTS || s_ui_mode == UI_LISTS_LOADING ||
            s_ui_mode == UI_DELETE_CONFIRM)
            enter_live_view(false);
        else if (s_ui_mode == UI_SETTINGS)
            draw_settings();
        else if (s_ui_mode == UI_CREATOR_CREDITS) {
            /* The 10 fps UI timer owns this animation. A list-state commit
             * must not replace the Easter egg with the frequency list. */
        }
        else if (s_ui_mode == UI_AUDIO)
            draw_audio_page();
        else if (s_ui_mode == UI_WATERFALL_SPAN)
            draw_waterfall_span();
        else if (s_ui_mode == UI_CW_DECODER)
            draw_cw_decoder();
        else if (s_ui_mode == UI_POCKET_ALERT)
            draw_pocket_alert();
        else
            draw_list();
    }
}

static void poll_frame(void) {
    /* Library metadata temporarily reuses the three waterfall row signals.
     * Do not read or render row commits until a Live-list commit returns the
     * UI to Live. This also avoids adding a mailbox read to every 50 ms frame
     * poll and preserves the proven waterfall cadence. */
    if (s_ui_mode == UI_LISTS_LOADING || s_ui_mode == UI_LISTS ||
        s_ui_mode == UI_DELETE_CONFIRM || s_ui_mode == UI_ADD_FREQUENCY)
        return;
    uint32_t sequence;
    if (!signal_get_u32("wr_seq", &sequence) || sequence == s_row_seq) return;
    double rssi;
    double peak;
    uint32_t frequency;
    uint32_t span;
    uint32_t selected;
    uint32_t row_values[3];
    if (!signal_get_u32("wr_freq", &frequency) ||
        !signal_get_u32("wr_span", &span) ||
        !signal_get("wr_rssi", &rssi) ||
        !signal_get("wr_peak", &peak) ||
        !signal_get_u32("wr_sel", &selected) ||
        !signal_get_u32("wr_row0", &row_values[0]) ||
        !signal_get_u32("wr_row1", &row_values[1]) ||
        !signal_get_u32("wr_row2", &row_values[2]))
        return;

    if (span <= 1u) {
        receive_message_chunk(frequency, row_values, span == 1u);
        s_last_row_us = time_us_64();
        s_row_seq = sequence;
        s_link_ok = true;
        update_leds();
        return;
    }

    if (frequency != s_frequency && s_message_until_us != 0u) {
        s_message_until_us = 0u;
        s_detected_message[0] = '\0';
        if (s_ui_mode == UI_LIVE) draw_list();
    }

    s_frequency = frequency;
    s_span = span;
    if (s_requested_span == span) s_requested_span = 0u;
    s_rssi_tenths = round_i32(rssi * 10.0);
    s_peak_tenths_khz = round_i32(peak / 100.0);
    s_last_row_us = time_us_64();
    pocket_alert_sample(s_last_row_us);
    bool refresh_complete = s_ui_mode == UI_REFRESH && !s_cmd_pending &&
                            sequence != s_refresh_from_seq;
    if (s_ui_mode == UI_STARTUP || s_ui_mode == UI_FAULT || refresh_complete)
        enter_live_view(true);
    if ((int)selected != s_active && selected < (uint32_t)s_count) {
        s_active = (int)selected;
        s_cursor = s_active;
        draw_list();
    }
    uint16_t rows[3] = {
        (uint16_t)row_values[0], (uint16_t)row_values[1], (uint16_t)row_values[2]
    };
    if (s_ui_mode == UI_LIVE) {
        push_waterfall_row(rows);
        draw_dynamic();
        draw_message_overlay();
    } else if (s_ui_mode == UI_STATUS || s_ui_mode == UI_REFRESH ||
               s_ui_mode == UI_FAULT) {
        draw_receiver_status();
    }
    update_leds();
    s_row_seq = sequence;
    s_link_ok = true;
}

static void send_command(uint8_t opcode, uint8_t argument) {
    s_cmd_seq = (s_cmd_seq + 1u) & 0xFFFFu;
    if (s_cmd_seq == 0u) s_cmd_seq = 1u;
    s_pending_cmd = (s_cmd_seq << 8) | ((uint32_t)(opcode & 0xFu) << 4) |
                    (uint32_t)(argument & 0xFu);
    s_cmd_pending = true;
    ow_status status = ow_scripting_app_signals_app_signal_set(
        &s_dev, "wr_cmd", (double)s_pending_cmd);
    s_link_ok = status == OW_OK;
    if (s_ui_mode == UI_LIVE) draw_dynamic();
    DIAG("waverider: command op=%u arg=%u seq=%u status=%d\n",
         (unsigned)opcode, (unsigned)argument, (unsigned)s_cmd_seq, (int)status);
}

static void retry_pending_command(void) {
    if (!s_cmd_pending) return;
    uint32_t ack;
    if (signal_get_u32("wr_ack", &ack) && (ack & 0xFFFFu) == s_cmd_seq) {
        s_cmd_pending = false;
        s_link_ok = true;
        return;
    }
    /* Main's app-signal service can transiently reject a write while the CM0
     * is publishing a waterfall row.  Keep the same sequence/value pending
     * until CM0 records wr_ack; never turn one press into multiple actions. */
    s_link_ok = ow_scripting_app_signals_app_signal_set(
                    &s_dev, "wr_cmd", (double)s_pending_cmd) == OW_OK;
}

static void handle_buttons(void) {
    uartkbd_event_t event;
    while (uartkbd_next_event(&event)) {
        DIAG("waverider: button id=%u pressed=%u\n",
             (unsigned)event.btn, event.pressed ? 1u : 0u);
        if (!event.pressed) continue;
        if (s_ui_mode == UI_CREATOR_CREDITS) {
            s_ui_mode = UI_SETTINGS;
            draw_settings();
            continue;
        }
        if (s_ui_mode == UI_SETTINGS) {
            if (creator_sequence_step(event.btn, time_us_64())) continue;
            switch (event.btn) {
            case UARTKBD_BTN_NAV_LEFT:
            case UARTKBD_BTN_NAV_UP:
            case UARTKBD_BTN_YELLOW:
                move_settings_cursor(-1);
                break;
            case UARTKBD_BTN_NAV_RIGHT:
            case UARTKBD_BTN_NAV_DOWN:
            case UARTKBD_BTN_BLUE:
                move_settings_cursor(1);
                break;
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
            case UARTKBD_BTN_GREEN:
                open_selected_setting();
                break;
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_CANCEL:
            case UARTKBD_BTN_PAGE:
            case UARTKBD_BTN_RED:
                enter_live_view(false);
                break;
            default:
                break;
            }
            continue;
        }
        if (s_ui_mode == UI_HAPTIC_PROBE) {
            switch (event.btn) {
            case UARTKBD_BTN_NAV_LEFT:
            case UARTKBD_BTN_NAV_UP:
            case UARTKBD_BTN_YELLOW:
                haptic_probe_select(-1);
                break;
            case UARTKBD_BTN_NAV_RIGHT:
            case UARTKBD_BTN_NAV_DOWN:
            case UARTKBD_BTN_BLUE:
                haptic_probe_select(1);
                break;
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
            case UARTKBD_BTN_GREEN:
            case UARTKBD_BTN_RED:
                haptic_probe_start();
                break;
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_CANCEL:
            case UARTKBD_BTN_PAGE:
                leave_haptic_probe();
                break;
            default:
                break;
            }
            continue;
        }
        if (s_ui_mode == UI_POCKET_ALERT) {
            switch (event.btn) {
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
            case UARTKBD_BTN_YELLOW:
                set_alert_enabled(!s_alert_enabled);
                break;
            case UARTKBD_BTN_NAV_LEFT:
            case UARTKBD_BTN_NAV_DOWN:
            case UARTKBD_BTN_GREEN:
                adjust_alert_threshold(-1);
                break;
            case UARTKBD_BTN_NAV_RIGHT:
            case UARTKBD_BTN_NAV_UP:
            case UARTKBD_BTN_BLUE:
                adjust_alert_threshold(1);
                break;
            case UARTKBD_BTN_RED:
                if (HAPTIC_GPIO35_VERIFIED) {
                    haptic_test_three_pulses();
                    draw_pocket_alert_dynamic();
                } else {
                    s_ui_mode = UI_HAPTIC_PROBE;
                    draw_haptic_probe();
                }
                break;
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_CANCEL:
            case UARTKBD_BTN_PAGE:
                s_ui_mode = UI_SETTINGS;
                draw_settings();
                break;
            default:
                break;
            }
            continue;
        }
        if (s_ui_mode == UI_ADD_FREQUENCY) {
            switch (event.btn) {
            case UARTKBD_BTN_NAV_LEFT:
            case UARTKBD_BTN_YELLOW:
                if (s_edit_cursor > 0u) s_edit_cursor--;
                draw_add_frequency();
                break;
            case UARTKBD_BTN_NAV_RIGHT:
            case UARTKBD_BTN_GREEN:
                if (s_edit_cursor < 6u) s_edit_cursor++;
                draw_add_frequency();
                break;
            case UARTKBD_BTN_NAV_UP:
                replace_edit_digit((uint8_t)((edit_digit() + 1u) % 10u));
                draw_add_frequency();
                break;
            case UARTKBD_BTN_NAV_DOWN:
                replace_edit_digit((uint8_t)((edit_digit() + 9u) % 10u));
                draw_add_frequency();
                break;
            case UARTKBD_BTN_BLUE:
                replace_edit_digit(0u);
                draw_add_frequency();
                break;
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
                commit_add_frequency();
                break;
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_RED:
            case UARTKBD_BTN_CANCEL:
                s_ui_mode = UI_LISTS;
                draw_library();
                break;
            default:
                break;
            }
            continue;
        }
        if (s_ui_mode == UI_DELETE_CONFIRM) {
            if (event.btn == UARTKBD_BTN_NAV_CENTER ||
                event.btn == UARTKBD_BTN_OK) {
                s_ui_mode = UI_LISTS_LOADING;
                draw_library_loading("DELETING FREQUENCY");
                send_command(11, (uint8_t)s_cursor);
            } else if (event.btn == UARTKBD_BTN_RED ||
                       event.btn == UARTKBD_BTN_CANCEL ||
                       event.btn == UARTKBD_BTN_GREY) {
                s_ui_mode = UI_LISTS;
                draw_library();
            }
            continue;
        }
        if (s_ui_mode == UI_MESSAGE_CLEAR_CONFIRM) {
            if (event.btn == UARTKBD_BTN_NAV_CENTER ||
                event.btn == UARTKBD_BTN_OK) {
                clear_message_history();
            } else if (event.btn == UARTKBD_BTN_RED ||
                       event.btn == UARTKBD_BTN_CANCEL ||
                       event.btn == UARTKBD_BTN_GREY) {
                s_ui_mode = UI_MESSAGE_FREQUENCIES;
                draw_message_frequencies();
            }
            continue;
        }
        if (s_ui_mode == UI_MESSAGE_FREQUENCIES) {
            uint8_t frequency_count = message_frequency_count();
            switch (event.btn) {
            case UARTKBD_BTN_NAV_LEFT:
            case UARTKBD_BTN_NAV_UP:
            case UARTKBD_BTN_YELLOW:
                if (frequency_count > 0u)
                    s_message_frequency_cursor =
                        (uint8_t)((s_message_frequency_cursor +
                                   frequency_count - 1u) % frequency_count);
                draw_message_frequencies();
                break;
            case UARTKBD_BTN_NAV_RIGHT:
            case UARTKBD_BTN_NAV_DOWN:
            case UARTKBD_BTN_BLUE:
                if (frequency_count > 0u)
                    s_message_frequency_cursor =
                        (uint8_t)((s_message_frequency_cursor + 1u) %
                                  frequency_count);
                draw_message_frequencies();
                break;
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
            case UARTKBD_BTN_GREEN:
                if (frequency_count > 0u) {
                    uint32_t frequency =
                        message_frequency_at(s_message_frequency_cursor);
                    select_latest_message_for_frequency(frequency);
                    s_ui_mode = UI_MESSAGES;
                    draw_messages();
                }
                break;
            case UARTKBD_BTN_RED:
                if (s_message_history_count > 0u) {
                    s_ui_mode = UI_MESSAGE_CLEAR_CONFIRM;
                    draw_message_clear_confirmation();
                }
                break;
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_CANCEL:
                enter_live_view(false);
                break;
            default:
                break;
            }
            continue;
        }
        if (s_ui_mode == UI_MESSAGES) {
            switch (event.btn) {
            case UARTKBD_BTN_NAV_LEFT:
            case UARTKBD_BTN_NAV_UP:
            case UARTKBD_BTN_YELLOW:
                step_message_for_frequency(-1);
                draw_messages();
                break;
            case UARTKBD_BTN_NAV_RIGHT:
            case UARTKBD_BTN_NAV_DOWN:
            case UARTKBD_BTN_GREEN:
                step_message_for_frequency(1);
                draw_messages();
                break;
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
            case UARTKBD_BTN_GREY:
                s_ui_mode = UI_MESSAGE_FREQUENCIES;
                draw_message_frequencies();
                break;
            case UARTKBD_BTN_RED:
            case UARTKBD_BTN_CANCEL:
                enter_live_view(false);
                break;
            default:
                break;
            }
            continue;
        }
        if (s_ui_mode == UI_AUDIO) {
            if (event.btn == UARTKBD_BTN_RED)
                enter_live_view(false);
            else if (event.btn == UARTKBD_BTN_NAV_CENTER ||
                     event.btn == UARTKBD_BTN_OK ||
                     event.btn == UARTKBD_BTN_CANCEL ||
                     event.btn == UARTKBD_BTN_GREY ||
                     event.btn == UARTKBD_BTN_PAGE) {
                s_ui_mode = UI_SETTINGS;
                draw_settings();
            }
            continue;
        }
        if (s_ui_mode == UI_WATERFALL_SPAN) {
            switch (event.btn) {
            case UARTKBD_BTN_NAV_LEFT:
            case UARTKBD_BTN_NAV_DOWN:
            case UARTKBD_BTN_YELLOW:
                adjust_span_profile(-1);
                break;
            case UARTKBD_BTN_NAV_RIGHT:
            case UARTKBD_BTN_NAV_UP:
            case UARTKBD_BTN_BLUE:
                adjust_span_profile(1);
                break;
            case UARTKBD_BTN_RED:
                enter_live_view(false);
                break;
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
            case UARTKBD_BTN_GREEN:
            case UARTKBD_BTN_CANCEL:
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_PAGE:
                s_ui_mode = UI_SETTINGS;
                draw_settings();
                break;
            default:
                break;
            }
            continue;
        }
        if (s_ui_mode == UI_CW_DECODER) {
            if (event.btn == UARTKBD_BTN_RED)
                enter_live_view(false);
            else if (event.btn == UARTKBD_BTN_YELLOW ||
                     event.btn == UARTKBD_BTN_GREEN ||
                     event.btn == UARTKBD_BTN_NAV_CENTER ||
                     event.btn == UARTKBD_BTN_OK)
                set_cw_enabled(!s_cw_enabled);
            else if (event.btn == UARTKBD_BTN_CANCEL ||
                     event.btn == UARTKBD_BTN_GREY ||
                     event.btn == UARTKBD_BTN_PAGE) {
                s_ui_mode = UI_SETTINGS;
                draw_settings();
            }
            continue;
        }
        if (s_ui_mode == UI_LISTS_LOADING) {
            if (event.btn == UARTKBD_BTN_GREY ||
                event.btn == UARTKBD_BTN_CANCEL) {
                draw_library_loading("RETURNING TO LIVE");
                send_command(13, 0);
            }
            continue;
        }
        if (s_ui_mode == UI_LISTS) {
            switch (event.btn) {
            case UARTKBD_BTN_NAV_UP:
                if (s_cursor > 0) {
                    s_cursor--;
                    draw_library();
                } else if (s_library_offset > 0u) {
                    s_ui_mode = UI_LISTS_LOADING;
                    draw_library_loading("LOADING PREVIOUS PAGE");
                    send_command(8, 0);
                }
                break;
            case UARTKBD_BTN_NAV_DOWN:
                if (s_cursor + 1 < s_count) {
                    s_cursor++;
                    draw_library();
                } else if (s_library_offset + (uint32_t)s_count <
                           s_library_total) {
                    s_ui_mode = UI_LISTS_LOADING;
                    draw_library_loading("LOADING NEXT PAGE");
                    send_command(9, 0);
                }
                break;
            case UARTKBD_BTN_NAV_LEFT:
                if (s_library_offset > 0u) {
                    s_ui_mode = UI_LISTS_LOADING;
                    draw_library_loading("LOADING PREVIOUS PAGE");
                    send_command(8, 0);
                }
                break;
            case UARTKBD_BTN_NAV_RIGHT:
                if (s_library_offset + (uint32_t)s_count < s_library_total) {
                    s_ui_mode = UI_LISTS_LOADING;
                    draw_library_loading("LOADING NEXT PAGE");
                    send_command(9, 0);
                }
                break;
            case UARTKBD_BTN_NAV_CENTER:
            case UARTKBD_BTN_OK:
            case UARTKBD_BTN_GREEN:
                s_ui_mode = UI_LISTS_LOADING;
                draw_library_loading("UPDATING LIVE LIST");
                send_command(10, (uint8_t)s_cursor);
                break;
            case UARTKBD_BTN_YELLOW:
                begin_add_frequency();
                break;
            case UARTKBD_BTN_BLUE:
                s_ui_mode = UI_LISTS_LOADING;
                draw_library_loading("TUNING FREQUENCY");
                send_command(12, (uint8_t)s_cursor);
                break;
            case UARTKBD_BTN_RED:
                s_ui_mode = UI_DELETE_CONFIRM;
                draw_delete_confirmation();
                break;
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_CANCEL:
                s_ui_mode = UI_LISTS_LOADING;
                draw_library_loading("RETURNING TO LIVE");
                send_command(13, 0);
                break;
            default:
                break;
            }
            continue;
        }
        if ((s_ui_mode == UI_STATUS || s_ui_mode == UI_REFRESH ||
             s_ui_mode == UI_FAULT) &&
            (event.btn == UARTKBD_BTN_NAV_CENTER ||
             event.btn == UARTKBD_BTN_OK ||
             event.btn == UARTKBD_BTN_CANCEL)) {
            if (s_ui_mode != UI_FAULT) enter_live_view(false);
            continue;
        }
        if (s_ui_mode == UI_STATUS &&
            (event.btn == UARTKBD_BTN_NAV_UP ||
             event.btn == UARTKBD_BTN_NAV_DOWN ||
             event.btn == UARTKBD_BTN_NAV_LEFT ||
             event.btn == UARTKBD_BTN_NAV_RIGHT)) {
            enter_live_view(false);
        }
        switch (event.btn) {
        case UARTKBD_BTN_PAGE:
            s_ui_mode = UI_SETTINGS;
            draw_settings();
            break;
        case UARTKBD_BTN_GREY:
            s_ui_mode = UI_LISTS_LOADING;
            draw_library_loading("LOADING LIBRARY");
            send_command(7, 0);
            break;
        case UARTKBD_BTN_YELLOW:
            s_ui_mode = UI_MESSAGE_FREQUENCIES;
            s_message_frequency_cursor = 0u;
            draw_message_frequencies();
            break;
        case UARTKBD_BTN_GREEN:
            if (s_count > 0) s_cursor = (s_cursor + 1) % s_count;
            draw_list();
            /* Green is the supported v07 quick-tune key.  Send the absolute
             * row rather than a relative Next request so retries and delayed
             * CM0 acknowledgement cannot apply the wrong channel. Advance
             * from the visible cursor so a just-restored persisted selection
             * cannot make Next jump farther than one row during startup. */
            send_command(6, (uint8_t)s_cursor);
            break;
        case UARTKBD_BTN_BLUE:
            if (s_count > 0) s_cursor = (s_cursor + s_count - 1) % s_count;
            draw_list();
            send_command(6, (uint8_t)s_cursor);
            break;
        case UARTKBD_BTN_RED: begin_refresh(); break;
        case UARTKBD_BTN_CANCEL: enter_live_view(false); break;
        case UARTKBD_BTN_NAV_UP:
        case UARTKBD_BTN_NAV_LEFT:
            if (s_count > 0) s_cursor = (s_cursor + s_count - 1) % s_count;
            draw_list();
            /* This unit's D-pad is the physically verified input path. Tune
             * immediately when the cursor moves so a foxhunter never needs a
             * second context-key press that their keyboard firmware may not
             * report. Opcode 6 is absolute/idempotent, so command retries are
             * safe and cannot skip a channel. */
            send_command(6, (uint8_t)s_cursor);
            break;
        case UARTKBD_BTN_NAV_DOWN:
        case UARTKBD_BTN_NAV_RIGHT:
            if (s_count > 0) s_cursor = (s_cursor + 1) % s_count;
            draw_list();
            send_command(6, (uint8_t)s_cursor);
            break;
        case UARTKBD_BTN_NAV_CENTER:
        case UARTKBD_BTN_OK:
            send_command(6, (uint8_t)s_cursor);
            break;
        default:
            break;
        }
    }
}

static void handle_touch(void) {
    static bool was_down;
    uint16_t x = 0, y = 0;
    bool down = ft6336_poll(&x, &y);
    if (down && !was_down) {
        DIAG("waverider: touch x=%u y=%u\n", (unsigned)x, (unsigned)y);
        if (s_ui_mode == UI_CREATOR_CREDITS) {
            s_ui_mode = UI_SETTINGS;
            draw_settings();
        } else if (s_ui_mode == UI_ADD_FREQUENCY) {
            bool handled = false;
            for (int index = 0; index < 7; index++) {
                int box_x = 24 + index * 44 + (index >= 4 ? 16 : 0);
                if (x >= (uint16_t)box_x && x < (uint16_t)(box_x + 36) &&
                    y >= 68u && y < 110u) {
                    s_edit_cursor = (uint8_t)index;
                    draw_add_frequency();
                    handled = true;
                    break;
                }
            }
            if (!handled && y >= 135u && y < 219u && x >= 28u && x < 468u) {
                int column = (int)(x - 28u) / 88;
                int row = (int)(y - 135u) / 48;
                if (column >= 0 && column < 5 && row >= 0 && row < 2) {
                    int slot = row * 5 + column;
                    int digit = slot < 9 ? slot + 1 : 0;
                    replace_edit_digit((uint8_t)digit);
                    if (s_edit_cursor < 6u) s_edit_cursor++;
                    draw_add_frequency();
                }
                handled = true;
            }
            if (!handled && y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 0 || button == 4) {
                    s_ui_mode = UI_LISTS;
                    draw_library();
                } else if (button == 1 && s_edit_cursor > 0u) {
                    s_edit_cursor--;
                    draw_add_frequency();
                } else if (button == 2 && s_edit_cursor < 6u) {
                    s_edit_cursor++;
                    draw_add_frequency();
                } else if (button == 3) {
                    replace_edit_digit(0u);
                    draw_add_frequency();
                }
            }
        } else if (s_ui_mode == UI_DELETE_CONFIRM) {
            if (y >= 170u && y < 235u && x < 300u) {
                s_ui_mode = UI_LISTS_LOADING;
                draw_library_loading("DELETING FREQUENCY");
                send_command(11, (uint8_t)s_cursor);
            } else if (y >= 286u || x >= 300u) {
                s_ui_mode = UI_LISTS;
                draw_library();
            }
        } else if (s_ui_mode == UI_SETTINGS) {
            if (y >= 43u && y < 249u && x >= 24u && x < 456u) {
                int row = (int)(y - 43u) / 53;
                if (row >= 0 && row < 4) {
                    s_settings_cursor = (uint8_t)row;
                    draw_settings();
                }
            } else if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 0 || button == 4) enter_live_view(false);
                else if (button == 1) move_settings_cursor(-1);
                else if (button == 2) open_selected_setting();
                else if (button == 3) move_settings_cursor(1);
            }
        } else if (s_ui_mode == UI_WATERFALL_SPAN) {
            if (y >= 120u && y < 190u && x >= 40u && x <= 440u) {
                int index = ((int)x - 52 + 37) / 75;
                if (index < 0) index = 0;
                if (index >= (int)SPAN_PROFILE_COUNT)
                    index = SPAN_PROFILE_COUNT - 1;
                set_span_profile((uint8_t)index);
            } else if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 0 || button == 2) {
                    s_ui_mode = UI_SETTINGS;
                    draw_settings();
                } else if (button == 1) {
                    adjust_span_profile(-1);
                } else if (button == 3) {
                    adjust_span_profile(1);
                } else if (button == 4) {
                    enter_live_view(false);
                }
            }
        } else if (s_ui_mode == UI_HAPTIC_PROBE) {
            if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 0) leave_haptic_probe();
                else if (button == 1) haptic_probe_select(-1);
                else if (button == 2 || button == 4) haptic_probe_start();
                else if (button == 3) haptic_probe_select(1);
            }
        } else if (s_ui_mode == UI_POCKET_ALERT) {
            if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 0) {
                    s_ui_mode = UI_SETTINGS;
                    draw_settings();
                }
                else if (button == 1) set_alert_enabled(!s_alert_enabled);
                else if (button == 2) adjust_alert_threshold(-1);
                else if (button == 3) adjust_alert_threshold(1);
                else if (button == 4) {
                    if (HAPTIC_GPIO35_VERIFIED) {
                        haptic_test_three_pulses();
                        draw_pocket_alert_dynamic();
                    } else {
                        s_ui_mode = UI_HAPTIC_PROBE;
                        draw_haptic_probe();
                    }
                }
            }
        } else if (s_ui_mode == UI_MESSAGE_CLEAR_CONFIRM) {
            if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 2) clear_message_history();
                else if (button == 0 || button == 4) {
                    s_ui_mode = UI_MESSAGE_FREQUENCIES;
                    draw_message_frequencies();
                }
            }
        } else if (s_ui_mode == UI_MESSAGE_FREQUENCIES) {
            if (y >= 48u && y < 248u) {
                uint8_t frequency_count = message_frequency_count();
                uint8_t first = s_message_frequency_cursor >= 7u
                                    ? s_message_frequency_cursor - 7u
                                    : 0u;
                uint8_t row = (uint8_t)((y - 48u) / 25u);
                if (first + row < frequency_count) {
                    s_message_frequency_cursor = first + row;
                    draw_message_frequencies();
                }
            } else if (y >= 286u) {
                int button = (int)(x / 96u);
                uint8_t frequency_count = message_frequency_count();
                if (button == 0) {
                    enter_live_view(false);
                } else if (button == 1 && frequency_count > 0u) {
                    s_message_frequency_cursor =
                        (uint8_t)((s_message_frequency_cursor +
                                   frequency_count - 1u) % frequency_count);
                    draw_message_frequencies();
                } else if (button == 2 && frequency_count > 0u) {
                    uint32_t frequency =
                        message_frequency_at(s_message_frequency_cursor);
                    select_latest_message_for_frequency(frequency);
                    s_ui_mode = UI_MESSAGES;
                    draw_messages();
                } else if (button == 3 && frequency_count > 0u) {
                    s_message_frequency_cursor =
                        (uint8_t)((s_message_frequency_cursor + 1u) %
                                  frequency_count);
                    draw_message_frequencies();
                } else if (button == 4 && s_message_history_count > 0u) {
                    s_ui_mode = UI_MESSAGE_CLEAR_CONFIRM;
                    draw_message_clear_confirmation();
                }
            }
        } else if (s_ui_mode == UI_MESSAGES) {
            if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 0) {
                    s_ui_mode = UI_MESSAGE_FREQUENCIES;
                    draw_message_frequencies();
                } else if (button == 4) {
                    enter_live_view(false);
                } else if (button == 1 && s_message_history_count > 0u) {
                    step_message_for_frequency(-1);
                    draw_messages();
                } else if (button == 2 && s_message_history_count > 0u) {
                    step_message_for_frequency(1);
                    draw_messages();
                }
            }
        } else if (s_ui_mode == UI_AUDIO) {
            if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 4) enter_live_view(false);
                else {
                    s_ui_mode = UI_SETTINGS;
                    draw_settings();
                }
            }
        } else if (s_ui_mode == UI_CW_DECODER) {
            if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 4) enter_live_view(false);
                else if (button == 1 || button == 2)
                    set_cw_enabled(!s_cw_enabled);
                else {
                    s_ui_mode = UI_SETTINGS;
                    draw_settings();
                }
            }
        } else if (s_ui_mode == UI_LISTS_LOADING) {
            if (y >= 286u && x < 96u) {
                draw_library_loading("RETURNING TO LIVE");
                send_command(13, 0);
            }
        } else if (s_ui_mode == UI_LISTS) {
            if (y >= 56u && y < 278u) {
                int first = s_cursor >= LIBRARY_VISIBLE_FREQS
                                ? s_cursor - LIBRARY_VISIBLE_FREQS + 1
                                : 0;
                if (first + LIBRARY_VISIBLE_FREQS > s_count)
                    first = s_count - LIBRARY_VISIBLE_FREQS;
                if (first < 0) first = 0;
                int row = (int)(y - 61u) / 21;
                int selected = first + row;
                if (row >= 0 && selected >= 0 && selected < s_count) {
                    s_cursor = selected;
                    draw_library();
                }
            } else if (y >= 286u) {
                int button = (int)(x / 96u);
                if (button == 0) {
                    s_ui_mode = UI_LISTS_LOADING;
                    draw_library_loading("RETURNING TO LIVE");
                    send_command(13, 0);
                } else if (button == 1) {
                    begin_add_frequency();
                } else if (button == 2) {
                    s_ui_mode = UI_LISTS_LOADING;
                    draw_library_loading("UPDATING LIVE LIST");
                    send_command(10, (uint8_t)s_cursor);
                } else if (button == 3) {
                    s_ui_mode = UI_LISTS_LOADING;
                    draw_library_loading("TUNING FREQUENCY");
                    send_command(12, (uint8_t)s_cursor);
                } else if (button == 4) {
                    s_ui_mode = UI_DELETE_CONFIRM;
                    draw_delete_confirmation();
                }
            }
        } else if (x >= SCALE_X && x < SCALE_X + SCALE_W + 72 &&
                   y >= 228u && y < 278u) {
            s_ui_mode = UI_SETTINGS;
            draw_settings();
        } else if (x < 140u && y < 28u) {
            /* The title doubles as a harmless splash replay target for field
             * verification; launch still shows the same artwork exactly once. */
            show_splash();
            draw_static();
            draw_list();
            draw_dynamic();
            restore_screen();
        } else if (x >= 340u && y < 28u) {
            if (s_ui_mode == UI_STATUS)
                enter_live_view(false);
            else if (s_ui_mode == UI_FAULT)
                begin_refresh();
            else {
                s_ui_mode = UI_STATUS;
                s_mode_started_us = time_us_64();
                draw_receiver_status();
            }
        } else if (x >= LIST_X && x < LIST_X + LIST_W && y >= LIST_Y &&
            y < LIST_Y + VISIBLE_FREQS * 23) {
            int first = s_cursor >= VISIBLE_FREQS
                            ? s_cursor - VISIBLE_FREQS + 1
                            : 0;
            if (first + VISIBLE_FREQS > s_count)
                first = s_count - VISIBLE_FREQS;
            if (first < 0) first = 0;
            s_cursor = first + (int)((y - LIST_Y) / 23u);
            if (s_cursor >= s_count) s_cursor = s_count - 1;
            draw_list();
            send_command(6, (uint8_t)s_cursor);
        } else if (y >= 286u) {
            int button = (int)(x / 96u);
            switch (button) {
            case 0:
                s_ui_mode = UI_LISTS_LOADING;
                draw_library_loading("LOADING LIBRARY");
                send_command(7, 0);
                break;
            case 1:
                s_ui_mode = UI_MESSAGE_FREQUENCIES;
                s_message_frequency_cursor = 0u;
                draw_message_frequencies();
                break;
            case 2:
                if (s_count > 0) s_cursor = (s_cursor + 1) % s_count;
                draw_list();
                send_command(6, (uint8_t)s_cursor);
                break;
            case 3:
                if (s_count > 0) s_cursor = (s_cursor + s_count - 1) % s_count;
                draw_list();
                send_command(6, (uint8_t)s_cursor);
                break;
            case 4: begin_refresh(); break;
            default: break;
            }
        }
    }
    was_down = down;
}

static void restore_screen(void) {
    st7796_flush_wait();
    st7796_blit_rect(0, 0, ST7796_W - 1, ST7796_H - 1, s_fb);
}

static bool apply_main_power_mask(uint32_t zone_mask) {
    static uint32_t sent_mask;
    static absolute_time_t sent_at;
    static bool settling;
    bool applied = false;
    if (!settling || sent_mask != zone_mask) {
        applied = picpwr_apply_main_awake_mask(zone_mask);
        if (applied) {
            sent_mask = zone_mask;
            sent_at = get_absolute_time();
            settling = true;
        }
    }
    if (applied) {
        DIAG("waverider: MAIN power mask=0x%x applied=%u\n",
             (unsigned)zone_mask, applied ? 1u : 0u);
    }
    if (!settling || sent_mask != zone_mask ||
        absolute_time_diff_us(sent_at, get_absolute_time()) < 1200000) {
        return false;
    }
    settling = false;
    DIAG("waverider: MAIN power mask=0x%x settled\n",
         (unsigned)zone_mask);
    return true;
}

static bool apply_main_power_zone(uint8_t zone, bool on,
                                  uint32_t *live_rails) {
    uint32_t rails = 0;
    if (zone < 1u || zone > 17u || live_rails == NULL ||
        !picpwr_rails(&rails)) {
        return false;
    }
    uint32_t bit = picpwr_zone_bit(zone);
    if (((rails & bit) != 0u) != on) {
        if (!on) return false;
        (void)picpwr_keep_awake(bit);
        if (!picpwr_rails(&rails) || (rails & bit) == 0u) return false;
    }
    *live_rails = rails;
    return true;
}

int main(void) {
    board_init();
    fw2_app_recovery_init();
    (void)picpwr_keep_awake(WAVERIDER_KEEP_AWAKE);
    uint32_t boot_rails = 0;
    uint32_t boot_wait_ms = 0;
    while (boot_wait_ms < 30000u &&
           (!picpwr_rails(&boot_rails) ||
            (boot_rails & WAVERIDER_BOOT_RAILS) != WAVERIDER_BOOT_RAILS)) {
        fw2_app_recovery_task();
        fw2_app_recovery_sleep_ms(10);
        boot_wait_ms += 10u;
        if ((boot_wait_ms % 5000u) == 0u) {
            DIAG("waverider: waiting for boot rails have=0x%x need=0x%x\n",
                 (unsigned)boot_rails, (unsigned)WAVERIDER_BOOT_RAILS);
        }
    }
    DIAG("waverider: boot rails %s=0x%x\n",
         (boot_rails & WAVERIDER_BOOT_RAILS) == WAVERIDER_BOOT_RAILS
             ? "ready"
             : "timeout",
         (unsigned)boot_rails);
    size_t psram_bytes = psram_init();
    if (psram_bytes < (size_t)ST7796_W * ST7796_H * 2u) {
        DIAG("waverider: PSRAM missing (%u bytes)\n", (unsigned)psram_bytes);
        for (;;) {
            fw2_app_recovery_task();
            tight_loop_contents();
        }
    }

    st7796_init();
    ft6336_init();
    agentio_init();
#if HAPTIC_GPIO35_VERIFIED
    gpio_init(PIN_HAPTIC);
    /* Physically verified FW2 v07 motor path: Display GPIO35, active high,
     * direct SIO output at a bounded 12 mA drive. */
    gpio_set_dir(PIN_HAPTIC, GPIO_OUT);
    gpio_set_drive_strength(PIN_HAPTIC, GPIO_DRIVE_STRENGTH_12MA);
    gpio_put(PIN_HAPTIC, 0u);
#endif
    fw2_app_about_use_lcd_restore(restore_screen);
    ws2812_init(pio1, 0, PIN_LED_DATA);
    ws2812_set_brightness(LED_BRIGHTNESS_NORMAL);
    update_leds();
    show_splash();
    s_ui_mode = UI_STARTUP;
    s_startup_stage = 0;
    s_mode_started_us = time_us_64();
    draw_static();
    draw_list();
    draw_dynamic();
    draw_startup_status();
    restore_screen();
    board_backlight_set(1);

    while (fw2_app_recovery_open_onewili(&s_dev) != OW_OK) {
        s_link_ok = false;
        s_startup_stage = 1;
        draw_startup_status();
        restore_screen();
        /* Keep the debug/validation surface responsive even while MAIN is
         * still negotiating the internal link. */
        agentio_task();
        fw2_app_recovery_sleep_ms(500);
    }
    DIAG("waverider: native Display link open\n");
    ow_fwgui_set_power_mask_handler(apply_main_power_mask);
    ow_fwgui_set_power_zone_handler(apply_main_power_zone);
    /* The board-manager path above powers FPGA + compute before this internal
     * link is opened. Now release CM0_RUNPG and invoke Main's stock Linux
     * enable action. Both operations are idempotent on a warm CM0. */
    ow_set_timeout(&s_dev, 5000u);
    uint32_t announced_rails = 0;
    if (picpwr_rails(&announced_rails)) {
        ow_fwgui_send_power_zones(announced_rails);
        fw2_app_recovery_sleep_ms(100);
    }
    s_startup_stage = 2;
    draw_startup_status();
    restore_screen();
    ow_status cm0_power =
        ow_hardware_power_management_set_zone(&s_dev, 17, 1);
    ow_status cm0_run =
        ow_hardware_power_management_set_cm0_run_line(
            &s_dev, OW_RESET_LINE_STATE_RELEASE);
    ow_status linux_enable = ow_linux_enable_linux_cpu(&s_dev);
    DIAG("waverider: CM0 enable power=%d run=%d linux=%d\n",
         (int)cm0_power, (int)cm0_run, (int)linux_enable);
    s_startup_stage = 3;
    draw_startup_status();
    restore_screen();
    /* The live mailbox is local and normally answers in a few milliseconds.
     * A short per-device timeout keeps the UI, HOME recovery, and AgentIO
     * responsive if one response is lost; other OneWili users retain the
     * library's conservative five-second default. */
    ow_set_timeout(&s_dev, 250u);

    /* App signals outlive this volatile Display process. Continue after the
     * last CM0 acknowledgement so a power cycle/reload cannot reuse an old
     * sequence number and have a valid press mistaken for stale traffic. */
    uint32_t persisted_sequence;
    if (signal_get_u32("wr_ack", &persisted_sequence)) {
        s_cmd_seq = persisted_sequence & 0xFFFFu;
    } else if (signal_get_u32("wr_cmd", &persisted_sequence)) {
        s_cmd_seq = (persisted_sequence >> 8) & 0xFFFFu;
    }

    uint64_t next_data_poll = 0;
    uint64_t next_list_poll = 0;
    uint64_t next_command_retry = 0;
    uint64_t next_led_refresh = 0;
    uint64_t next_ui_refresh = 0;
    uint64_t next_diag = 0;
    for (;;) {
        fw2_app_recovery_task();
        agentio_task();
        handle_buttons();
        handle_touch();
        uint64_t now = time_us_64();
        haptic_task(now);
        haptic_probe_task(now);
        recover_bridge_link(now);
        if (now >= next_data_poll) {
            poll_frame();
            next_data_poll = now + 50000u;
        }
        if (now >= next_list_poll) {
            poll_list();
            next_list_poll = now + 250000u;
        }
        if (now >= next_command_retry) {
            retry_pending_command();
            next_command_retry = now + 50000u;
        }
        if (s_fb_dirty && !st7796_flush_busy()) {
            s_fb_dirty = false;
            st7796_flush_async(0, 0, ST7796_W - 1, ST7796_H - 1, s_fb, NULL);
        }
        if (now >= next_led_refresh) {
            update_health_ui();
            update_leds();
            next_led_refresh = now + 250000u;
        }
        if (now >= next_ui_refresh) {
            if (s_ui_mode == UI_CREATOR_CREDITS) {
                if (now >= s_creator_until_us) {
                    s_ui_mode = UI_SETTINGS;
                    draw_settings();
                    next_ui_refresh = now + 500000u;
                } else {
                    if (!st7796_flush_busy())
                        draw_creator_credits_frame(s_creator_frame++);
                    next_ui_refresh = now + 100000u;
                }
            } else {
                if (s_ui_mode == UI_STARTUP)
                    draw_startup_status();
                else if (s_ui_mode == UI_STATUS || s_ui_mode == UI_REFRESH ||
                         s_ui_mode == UI_FAULT)
                    draw_receiver_status();
                else if (s_ui_mode == UI_POCKET_ALERT &&
                         !st7796_flush_busy())
                    draw_pocket_alert_dynamic();
                next_ui_refresh = now + 500000u;
            }
        }
        if (now >= next_diag) {
            DIAG("waverider: link calls=%u ok=%u fail=%u last=%d drop=%u gui=%u/%02x kbd=%u/%u row=%u list=%u pending=%u\n",
                 (unsigned)s_signal_get_calls, (unsigned)s_signal_get_ok,
                 (unsigned)s_signal_get_failed, (int)s_signal_get_last_status,
                 (unsigned)ow_fwgui_dropped_frames(),
                 (unsigned)ow_fwgui_gui_command_frames(),
                 (unsigned)ow_fwgui_last_gui_command(),
                 (unsigned)uartkbd_frames(), (unsigned)uartkbd_errors(),
                 (unsigned)s_row_seq, (unsigned)s_list_seq,
                 s_cmd_pending ? 1u : 0u);
            next_diag = now + 1000000u;
        }
        fw2_app_recovery_sleep_ms(2);
    }
}
