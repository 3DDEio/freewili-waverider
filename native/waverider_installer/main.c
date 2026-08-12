/* WaveRider self-installer — writes the validated native app UF2 through
 * MAIN's supported SDFS service, avoiding a host-side USB SD-card mount. */
#include "fw2.h"
#include "input/app_recovery_onewili.h"
#include "onewili.h"
#include "onewili_sd.h"
#include "platform/diag.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define APP_DIR  "/apps/Radio"
#define APP_PATH APP_DIR "/waverider_display.uf2"
#define LEGACY_APP_PATH "/apps/waverider/waverider_display.uf2"
#define CHUNK_SIZE 1024u
#define SD_RECLAIM_ATTEMPTS 30u
#define SD_RECLAIM_DELAY_MS 500u

extern const uint8_t waverider_payload[];
extern const size_t waverider_payload_len;
extern const uint8_t waverider_payload_xor;

static ow_device s_dev;
static uint8_t s_decoded[CHUNK_SIZE];

static inline uint16_t be16(uint16_t color) {
    return (uint16_t)((color >> 8) | (color << 8));
}

static void show_status(const char *line1, const char *line2, bool ok) {
    const uint16_t background = be16(0x0710);
    const uint16_t foreground = be16(ok ? 0x2EED : 0xF944);
    st7796_fill_rect(10, 80, 460, 150, background);
    st7796_draw_text(18, 96, 2, foreground, background, line1);
    st7796_draw_text(18, 140, 2, foreground, background, line2);
}

static bool install_payload(void) {
    ow_sd_set_timeout_ms(5000);
    ow_sd_file file;
    bool opened = false;
    for (unsigned attempt = 0; attempt < SD_RECLAIM_ATTEMPTS; ++attempt) {
        /* A previous host-side SD export can leave the mux assigned to USB
         * even across a power cycle. Reassert MAIN ownership while waiting
         * for the card and filesystem service to become available. */
        if ((attempt % 5u) == 0u) {
            ow_status host_status =
                ow_hardware_file_system_set_sd_card_host(&s_dev, 0);
            DIAG("waverider-installer: reclaim attempt=%u host=%d\n",
                 attempt + 1u, (int)host_status);
        }
        (void)ow_sd_mkdir(&s_dev, "/apps");
        fw2_app_recovery_task();
        (void)ow_sd_mkdir(&s_dev, APP_DIR);
        fw2_app_recovery_task();
        if (ow_sd_open(&s_dev, &file, APP_PATH, OW_SD_WRITE) == OW_OK) {
            opened = true;
            break;
        }
        DIAG("waverider-installer: waiting for SD attempt=%u sdfs=%d\n",
             attempt + 1u, (int)ow_sd_last_error());
        fw2_app_recovery_sleep_ms(SD_RECLAIM_DELAY_MS);
    }
    if (!opened) {
        DIAG("waverider-installer: SD unavailable after %u attempts sdfs=%d\n",
             SD_RECLAIM_ATTEMPTS, (int)ow_sd_last_error());
        return false;
    }

    size_t written = 0;
    while (written < waverider_payload_len) {
        size_t remaining = waverider_payload_len - written;
        size_t amount = remaining < CHUNK_SIZE ? remaining : CHUNK_SIZE;
        /* The payload is XOR-obscured only so its embedded FW2AINFO marker
         * cannot be mistaken for a second installer metadata record. */
        for (size_t i = 0; i < amount; ++i) {
            s_decoded[i] = waverider_payload[written + i] ^ waverider_payload_xor;
        }
        if (ow_sd_write(&file, s_decoded, amount) != OW_OK) {
            DIAG("waverider-installer: write failed at %u sdfs=%d\n",
                 (unsigned)written, (int)ow_sd_last_error());
            (void)ow_sd_close(&file);
            return false;
        }
        written += amount;
        fw2_app_recovery_task();
    }
    if (ow_sd_close(&file) != OW_OK) {
        DIAG("waverider-installer: close/verify failed sdfs=%d\n",
             (int)ow_sd_last_error());
        return false;
    }

    bool is_dir = false;
    uint32_t size = 0;
    if (ow_sd_stat(&s_dev, APP_PATH, &is_dir, &size) != OW_OK || is_dir ||
        size != (uint32_t)waverider_payload_len) {
        DIAG("waverider-installer: stat mismatch got=%u want=%u sdfs=%d\n",
             (unsigned)size, (unsigned)waverider_payload_len,
             (int)ow_sd_last_error());
        return false;
    }
    DIAG("waverider-installer: installed %s (%u bytes)\n", APP_PATH,
         (unsigned)size);
    /* Older WaveRider builds installed at /apps/waverider. Remove that file
     * only after the new Radio-category copy has been closed and verified so
     * an upgrade cannot leave the user without a launchable app. */
    ow_status legacy_status = ow_sd_remove(&s_dev, LEGACY_APP_PATH);
    DIAG("waverider-installer: legacy cleanup %s status=%d\n",
         LEGACY_APP_PATH, (int)legacy_status);
    return true;
}

int main(void) {
    board_init();
    fw2_app_recovery_init();
    st7796_init();
    fw2_app_about_use_lcd();
    st7796_fill_screen(be16(0x0710));
    st7796_draw_text(18, 15, 3, be16(0xF7BE), be16(0x0710), "WaveRider");
    st7796_draw_text(18, 52, 1, be16(0x7C10), be16(0x0710),
                     "Native app installer - SRAM only");
    show_status("CONNECTING TO MAIN", "PLEASE WAIT", true);
    board_backlight_set(1);

    while (fw2_app_recovery_open_onewili(&s_dev) != OW_OK) {
        fw2_app_recovery_task();
        fw2_app_recovery_sleep_ms(500);
    }
    ow_set_timeout(&s_dev, 2000);
    ow_status host_status = ow_hardware_file_system_set_sd_card_host(&s_dev, 0);
    DIAG("waverider-installer: initial SD reclaim host=%d\n", (int)host_status);
    /* Give MAIN time to tear down USB export and remount its filesystem before
     * the SDFS transport begins issuing requests. */
    for (unsigned i = 0; i < 10u; ++i) {
        fw2_app_recovery_task();
        fw2_app_recovery_sleep_ms(250);
    }
    if (fw2_app_recovery_wrap_sd() != OW_OK) {
        show_status("SD LINK FAILED", "HOLD HOME TO EXIT", false);
    } else {
        show_status("INSTALLING APP", "DO NOT POWER OFF", true);
        bool installed = install_payload();
        show_status(installed ? "INSTALL COMPLETE" : "INSTALL FAILED",
                    installed ? "HOLD HOME TO EXIT" : "CHECK DIAGNOSTICS",
                    installed);
    }

    for (;;) {
        fw2_app_recovery_task();
        fw2_app_recovery_sleep_ms(20);
    }
}
