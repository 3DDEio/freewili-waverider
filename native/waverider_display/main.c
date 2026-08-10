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

#define WAVERIDER_SPLASH_MS 3000u

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
#define PIN_HAPTIC 46u
#define HAPTIC_GPIO46_EXPERIMENTAL 0u
#define HAPTIC_PULSE_ON_US 450000u
#define HAPTIC_PULSE_OFF_US 220000u
#define HAPTIC_ALERT_COOLDOWN_US 30000000u
#define HAPTIC_REARM_HYSTERESIS_TENTHS 30
#define HAPTIC_PROBE_TOUCH_US 350000u
#define HAPTIC_PROBE_GAP_US 150000u

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
    UI_AUDIO,
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
static ow_status s_signal_get_last_status = OW_OK;
static bool s_alert_enabled;
static int32_t s_alert_threshold_tenths = -500;
static bool s_alert_armed = true;
static uint64_t s_last_alert_us;
static bool s_haptic_on;
static uint8_t s_haptic_pulses_remaining;
static uint64_t s_haptic_deadline_us;
static const uint8_t s_haptic_probe_pins[] = {31u, 36u, 44u, 46u};
static uint8_t s_haptic_probe_index;
static uint8_t s_haptic_probe_phase;
static uint64_t s_haptic_probe_deadline_us;
static uint32_t s_haptic_probe_saved_ctrl;
static uint32_t s_haptic_probe_saved_pad;
static bool s_haptic_probe_saved;

static void restore_screen(void);
static void send_command(uint8_t opcode, uint8_t argument);
static void enter_live_view(bool clear_plot);
static void draw_library(void);
static void draw_pocket_alert(void);
static void draw_pocket_alert_dynamic(void);
static void draw_haptic_probe(void);

static const uint32_t s_digit_places_khz[] = {
    1000000u, 100000u, 10000u, 1000u, 100u, 10u, 1u,
};

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

static void draw_splash(void) {
    static const int wave[][2] = {
        {20, 181}, {54, 181}, {70, 175}, {84, 151}, {98, 105},
        {112, 164}, {128, 180}, {160, 181}, {177, 173}, {190, 150},
        {204, 119}, {219, 168}, {236, 181}, {270, 181}, {289, 171},
        {306, 145}, {322, 91}, {339, 164}, {355, 181}, {460, 181},
    };
    fb_fill_rect(0, 0, ST7796_W, ST7796_H, COL_BG);

    /* A sound wave becomes the surf line beneath the whale. */
    for (size_t i = 1; i < sizeof wave / sizeof wave[0]; i++) {
        fb_draw_line(wave[i - 1][0], wave[i - 1][1],
                     wave[i][0], wave[i][1], 7, COL_SPLASH_WAVE);
        fb_draw_line(wave[i - 1][0], wave[i - 1][1] + 8,
                     wave[i][0], wave[i][1] + 8, 3, COL_BLUE);
    }

    /* Procedural surfing whale: no external image or SD lookup required. */
    fb_fill_ellipse(300, 112, 62, 25, COL_GREEN);
    fb_fill_ellipse(316, 120, 45, 14, COL_SPLASH_WAVE);
    fb_fill_triangle(240, 108, 211, 87, 220, 116, COL_GREEN);
    fb_fill_triangle(240, 116, 214, 138, 221, 111, COL_GREEN);
    fb_fill_triangle(284, 89, 302, 67, 310, 93, COL_GREEN);
    fb_fill_ellipse(337, 105, 4, 4, COL_BG);
    fb_fill_ellipse(338, 104, 1, 1, COL_WHITE);
    fb_draw_line(349, 123, 361, 117, 3, COL_BG);
    fb_draw_line(358, 83, 358, 67, 3, COL_BLUE);
    fb_draw_line(358, 68, 348, 57, 3, COL_BLUE);
    fb_draw_line(358, 68, 368, 57, 3, COL_BLUE);

    fb_draw_text(132, 220, 4, COL_WHITE, COL_BG, "WaveRider");
    fb_draw_text(150, 267, 2, COL_GREEN, COL_BG, "RIDE THE SIGNAL");
    s_fb_dirty = true;
}

static void show_splash(void) {
    draw_splash();
    restore_screen();
    board_backlight_set(1);
    uint32_t elapsed_ms = 0;
    while (elapsed_ms < WAVERIDER_SPLASH_MS) {
        fw2_app_recovery_task();
        agentio_task();
        fw2_app_recovery_sleep_ms(10);
        elapsed_ms += 10u;
    }
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
                 "CHECK=TUNE  PAGE=POCKET ALERT");
    draw_rssi_scale();
    fb_draw_text(SCALE_X, 248, 1, COL_DIM, COL_BG,
                 "-70          -50          -30          -10");
    draw_button(0, "LISTS", COL_TEXT);
    draw_button(1, "AUDIO", COL_YELLOW);
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
    default: return "WAITING FOR SDR DATA";
    }
}

static void draw_startup_status(void) {
    char line[40];
    uint32_t elapsed = s_mode_started_us == 0
                           ? 0u
                           : (uint32_t)((time_us_64() - s_mode_started_us) /
                                        1000000u);
    int progress = 35 + (int)s_startup_stage * 55;
    if (progress > 250) progress = 250;
    fb_fill_rect(PLOT_X, PLOT_Y, PLOT_W, PLOT_H, COL_PANEL);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 13, 2, COL_TEXT, COL_PANEL,
                 "WAVERIDER STARTING");
    fb_fill_rect(PLOT_X + 16, PLOT_Y + 43, 260, 10, COL_BORDER);
    fb_fill_rect(PLOT_X + 16, PLOT_Y + 43, progress, 10, COL_GREEN);
    int pulse = (int)((elapsed * 23u) % 250u);
    fb_fill_rect(PLOT_X + 16 + pulse, PLOT_Y + 41, 5, 14, COL_WHITE);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 66, 2, COL_YELLOW, COL_PANEL,
                 startup_stage_text());
    snprintf(line, sizeof line, "ELAPSED %lu SEC", (unsigned long)elapsed);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 93, 1, COL_DIM, COL_PANEL, line);
    fb_draw_text(PLOT_X + 16, PLOT_Y + 111, 1, COL_DIM, COL_PANEL,
                 "LIST BROWSING IS READY");
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
    fb_fill_rect(24, 54, 432, 196, COL_PANEL);
    fb_draw_text(62, 78, 2, COL_YELLOW, COL_PANEL, "AUDIO IS NOT AVAILABLE YET");
    fb_draw_text(62, 118, 1, COL_TEXT, COL_PANEL,
                 "THE SDR RECEIVER REMAINS MUTED.");
    fb_draw_text(62, 142, 1, COL_DIM, COL_PANEL,
                 "A BOUNDED PCM BRIDGE IS REQUIRED BEFORE");
    fb_draw_text(62, 158, 1, COL_DIM, COL_PANEL,
                 "SPEAKER OR HEADPHONE OUTPUT CAN BE SAFE.");
    fb_draw_text(62, 202, 1, COL_BLUE, COL_PANEL,
                 "CHECK, RED, OR CANCEL = BACK");
    draw_button(0, "BACK", COL_TEXT);
    s_fb_dirty = true;
}

static void haptic_set(bool on) {
#if HAPTIC_GPIO46_EXPERIMENTAL
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
#if HAPTIC_GPIO46_EXPERIMENTAL
    s_haptic_pulses_remaining = 3u;
    haptic_set(true);
    s_haptic_deadline_us = time_us_64() + HAPTIC_PULSE_ON_US;
#else
    s_haptic_pulses_remaining = 0u;
    haptic_set(false);
    DIAG("waverider: haptic unavailable; GPIO46 path is not verified\n");
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
#if !HAPTIC_GPIO46_EXPERIMENTAL
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
             HAPTIC_GPIO46_EXPERIMENTAL
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

    const char *state = "HARDWARE PATH NOT VERIFIED";
    uint16_t state_color = COL_YELLOW;
    if (!HAPTIC_GPIO46_EXPERIMENTAL) {
        state = "MOTOR DRIVER NOT PUBLISHED";
    } else if (s_haptic_pulses_remaining > 0u) {
        state = s_haptic_on ? "TEST: GPIO46 OUTPUT HIGH" : "TEST: PULSE GAP";
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
    if (HAPTIC_GPIO46_EXPERIMENTAL)
        snprintf(line, sizeof line,
                 "3 PULSES   30 SEC COOLDOWN   READY IN %lu SEC",
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
    draw_button(1, HAPTIC_GPIO46_EXPERIMENTAL
                       ? (s_alert_enabled ? "DISABLE" : "ENABLE")
                       : "UNAVAILABLE", COL_YELLOW);
    draw_button(2, "-1 dB", COL_GREEN);
    draw_button(3, "+1 dB", COL_BLUE);
    draw_button(4, HAPTIC_GPIO46_EXPERIMENTAL ? "TEST" : "INFO", COL_RED);
    s_fb_dirty = true;
}

static void set_alert_enabled(bool enabled) {
#if !HAPTIC_GPIO46_EXPERIMENTAL
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
    bool stale = s_last_row_us == 0 || now - s_last_row_us > 3000000u;
    if (s_ui_mode == UI_LIVE && stale) {
        s_ui_mode = UI_FAULT;
        s_mode_started_us = now;
        draw_receiver_status();
    }
}

static void enter_live_view(bool clear_plot) {
    bool first_ready = s_ui_mode == UI_STARTUP;
    s_ui_mode = UI_LIVE;
    if (first_ready) s_ready_led_until_us = time_us_64() + 1500000u;
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

static void update_leds(void) {
    uint64_t now = time_us_64();
    ws2812_clear();
    if (s_ui_mode == UI_STARTUP) {
        uint64_t elapsed = s_mode_started_us == 0 ? 0 : now - s_mode_started_us;
        bool overdue = elapsed > 45000000u;
        rgb_t color = s_startup_stage == 0
                          ? (rgb_t){.r = 180, .g = 0, .b = 0}
                          : (rgb_t){.r = 190, .g = 110, .b = 0};
        if (!overdue || ((now / 400000u) & 1u) == 0u) {
            for (int i = 0; i < 7; i++) ws2812_set_pixel((uint)i, color);
        }
        ws2812_show();
        return;
    }
    if (s_ui_mode == UI_REFRESH) {
        int active = (int)((now / 150000u) % 7u);
        ws2812_set_pixel((uint)active, (rgb_t){.r = 220, .g = 150, .b = 0});
        ws2812_show();
        return;
    }
    if (s_ui_mode == UI_LISTS_LOADING || s_ui_mode == UI_LISTS ||
        s_ui_mode == UI_DELETE_CONFIRM || s_ui_mode == UI_ADD_FREQUENCY ||
        s_ui_mode == UI_AUDIO) {
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
    if (now < s_ready_led_until_us) {
        for (int i = 0; i < 7; i++)
            ws2812_set_pixel((uint)i, (rgb_t){.r = 0, .g = 190, .b = 75});
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
    s_signal_get_calls++;
    ow_status status = ow_scripting_app_signals_app_signal_get(
        &s_dev, name, returned, sizeof returned, value);
    s_signal_get_last_status = status;
    if (status == OW_OK && strcmp(returned, name) == 0) {
        s_signal_get_ok++;
        return true;
    }
    s_signal_get_failed++;
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
        s_ui_mode == UI_DELETE_CONFIRM || s_ui_mode == UI_ADD_FREQUENCY ||
        s_ui_mode == UI_AUDIO)
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

    s_frequency = frequency;
    s_span = span;
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
                if (HAPTIC_GPIO46_EXPERIMENTAL) {
                    haptic_start_three_pulses();
                    draw_pocket_alert_dynamic();
                } else {
                    s_ui_mode = UI_HAPTIC_PROBE;
                    draw_haptic_probe();
                }
                break;
            case UARTKBD_BTN_GREY:
            case UARTKBD_BTN_CANCEL:
            case UARTKBD_BTN_PAGE:
                enter_live_view(false);
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
        if (s_ui_mode == UI_AUDIO) {
            if (event.btn == UARTKBD_BTN_NAV_CENTER ||
                event.btn == UARTKBD_BTN_OK ||
                event.btn == UARTKBD_BTN_RED ||
                event.btn == UARTKBD_BTN_CANCEL ||
                event.btn == UARTKBD_BTN_GREY)
                enter_live_view(false);
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
            s_ui_mode = UI_POCKET_ALERT;
            draw_pocket_alert();
            break;
        case UARTKBD_BTN_GREY:
            s_ui_mode = UI_LISTS_LOADING;
            draw_library_loading("LOADING LIBRARY");
            send_command(7, 0);
            break;
        case UARTKBD_BTN_YELLOW:
            s_ui_mode = UI_AUDIO;
            draw_audio_page();
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
        if (s_ui_mode == UI_ADD_FREQUENCY) {
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
                if (button == 0) enter_live_view(false);
                else if (button == 1) set_alert_enabled(!s_alert_enabled);
                else if (button == 2) adjust_alert_threshold(-1);
                else if (button == 3) adjust_alert_threshold(1);
                else if (button == 4) {
                    if (HAPTIC_GPIO46_EXPERIMENTAL) {
                        haptic_start_three_pulses();
                        draw_pocket_alert_dynamic();
                    } else {
                        s_ui_mode = UI_HAPTIC_PROBE;
                        draw_haptic_probe();
                    }
                }
            }
        } else if (s_ui_mode == UI_AUDIO) {
            enter_live_view(false);
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
            s_ui_mode = UI_POCKET_ALERT;
            draw_pocket_alert();
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
                s_ui_mode = UI_AUDIO;
                draw_audio_page();
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
#if HAPTIC_GPIO46_EXPERIMENTAL
    gpio_init(PIN_HAPTIC);
    /* Loadable apps inherit IO_BANK0 overrides from the stock loader. GPIO46
     * arrived with inverted input/output behavior on the connected unit, so
     * normalize every override before treating it as the haptic control. */
    gpio_set_outover(PIN_HAPTIC, GPIO_OVERRIDE_NORMAL);
    gpio_set_inover(PIN_HAPTIC, GPIO_OVERRIDE_NORMAL);
    gpio_set_oeover(PIN_HAPTIC, GPIO_OVERRIDE_NORMAL);
    gpio_set_irqover(PIN_HAPTIC, GPIO_OVERRIDE_NORMAL);
    gpio_set_dir(PIN_HAPTIC, GPIO_OUT);
    gpio_set_drive_strength(PIN_HAPTIC, GPIO_DRIVE_STRENGTH_12MA);
    gpio_pull_down(PIN_HAPTIC);
    gpio_put(PIN_HAPTIC, 0u);
#endif
    fw2_app_about_use_lcd_restore(restore_screen);
    ws2812_init(pio1, 0, PIN_LED_DATA);
    ws2812_set_brightness(48);
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
            if (s_ui_mode == UI_STARTUP)
                draw_startup_status();
            else if (s_ui_mode == UI_STATUS || s_ui_mode == UI_REFRESH ||
                     s_ui_mode == UI_FAULT)
                draw_receiver_status();
            else if (s_ui_mode == UI_POCKET_ALERT && !st7796_flush_busy())
                draw_pocket_alert_dynamic();
            next_ui_refresh = now + 500000u;
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
