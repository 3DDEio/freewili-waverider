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
#define APP_STAGE APP_DIR "/waverider_display.new"
#define APPDATA_DIR "/appdata"
#define APPDATA_APP_DIR APPDATA_DIR "/waverider"
#define APP_BACKUP APPDATA_APP_DIR "/waverider_display.previous.uf2"
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

static bool verified_payload_at(const char *path) {
    bool is_dir = false;
    uint32_t size = 0;
    if (ow_sd_stat(&s_dev, path, &is_dir, &size) != OW_OK || is_dir ||
        size != (uint32_t)waverider_payload_len) {
        return false;
    }

    ow_sd_file file;
    if (ow_sd_open(&s_dev, &file, path, OW_SD_READ) != OW_OK) {
        return false;
    }
    size_t checked = 0;
    while (checked < waverider_payload_len) {
        size_t remaining = waverider_payload_len - checked;
        size_t amount = remaining < CHUNK_SIZE ? remaining : CHUNK_SIZE;
        size_t got = 0;
        if (ow_sd_read(&file, s_decoded, amount, &got) != OW_OK || got != amount) {
            (void)ow_sd_close(&file);
            return false;
        }
        for (size_t i = 0; i < got; ++i) {
            if (s_decoded[i] !=
                (uint8_t)(waverider_payload[checked + i] ^ waverider_payload_xor)) {
                DIAG("waverider-installer: content mismatch at %u\n",
                     (unsigned)(checked + i));
                (void)ow_sd_close(&file);
                return false;
            }
        }
        checked += got;
        fw2_app_recovery_task();
    }
    return ow_sd_close(&file) == OW_OK;
}

static bool path_is_regular_file(const char *path, bool *exists) {
    bool is_dir = false;
    uint32_t ignored_size = 0;
    ow_status status = ow_sd_stat(&s_dev, path, &is_dir, &ignored_size);
    if (status == OW_OK) {
        *exists = true;
        return !is_dir;
    }
    if (status == OW_ERR_FAILED && ow_sd_last_error() == SDFS_ERR_NOT_FOUND) {
        *exists = false;
        return true;
    }
    DIAG("waverider-installer: stat failed path=%s status=%d sdfs=%d\n",
         path, (int)status, (int)ow_sd_last_error());
    return false;
}

static bool recover_interrupted_upgrade(void) {
    bool current_exists = false;
    if (!path_is_regular_file(APP_PATH, &current_exists)) {
        return false;
    }
    if (current_exists) {
        /* A completed/current app always wins over a leftover staging file. */
        (void)ow_sd_remove(&s_dev, APP_STAGE);
        return true;
    }

    bool backup_exists = false;
    if (!path_is_regular_file(APP_BACKUP, &backup_exists)) {
        return false;
    }
    if (backup_exists) {
        /* Power may have failed after current -> backup but before candidate
         * -> current. Restore the known launchable predecessor first. */
        if (ow_sd_rename(&s_dev, APP_BACKUP, APP_PATH) != OW_OK) {
            DIAG("waverider-installer: interrupted-upgrade restore failed sdfs=%d\n",
                 (int)ow_sd_last_error());
            return false;
        }
        (void)ow_sd_remove(&s_dev, APP_STAGE);
        DIAG("waverider-installer: restored interrupted upgrade backup\n");
        return true;
    }

    bool stage_exists = false;
    if (!path_is_regular_file(APP_STAGE, &stage_exists)) {
        return false;
    }
    if (stage_exists && verified_payload_at(APP_STAGE)) {
        /* A first installation can lose power after staging when no previous
         * app exists. A byte-identical candidate is safe to finish. */
        if (ow_sd_rename(&s_dev, APP_STAGE, APP_PATH) == OW_OK &&
            verified_payload_at(APP_PATH)) {
            DIAG("waverider-installer: completed interrupted first install\n");
            return true;
        }
        (void)ow_sd_remove(&s_dev, APP_PATH);
        return false;
    }
    (void)ow_sd_remove(&s_dev, APP_STAGE);
    return true;
}

static bool promote_staged_payload(void) {
    bool is_dir = false;
    uint32_t ignored_size = 0;
    bool had_current =
        ow_sd_stat(&s_dev, APP_PATH, &is_dir, &ignored_size) == OW_OK && !is_dir;

    if (had_current) {
        (void)ow_sd_mkdir(&s_dev, APPDATA_DIR);
        (void)ow_sd_mkdir(&s_dev, APPDATA_APP_DIR);
        (void)ow_sd_remove(&s_dev, APP_BACKUP);
        if (ow_sd_rename(&s_dev, APP_PATH, APP_BACKUP) != OW_OK) {
            DIAG("waverider-installer: could not preserve current app sdfs=%d\n",
                 (int)ow_sd_last_error());
            return false;
        }
    }

    if (ow_sd_rename(&s_dev, APP_STAGE, APP_PATH) != OW_OK) {
        DIAG("waverider-installer: promotion failed sdfs=%d\n",
             (int)ow_sd_last_error());
        if (had_current) {
            ow_status restored = ow_sd_rename(&s_dev, APP_BACKUP, APP_PATH);
            DIAG("waverider-installer: automatic restore status=%d\n",
                 (int)restored);
        }
        return false;
    }

    if (verified_payload_at(APP_PATH)) {
        return true;
    }

    DIAG("waverider-installer: promoted app did not verify; restoring backup\n");
    (void)ow_sd_remove(&s_dev, APP_PATH);
    if (had_current) {
        ow_status restored = ow_sd_rename(&s_dev, APP_BACKUP, APP_PATH);
        DIAG("waverider-installer: post-verify restore status=%d\n",
             (int)restored);
    }
    return false;
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
        (void)ow_sd_mkdir(&s_dev, APPDATA_DIR);
        (void)ow_sd_mkdir(&s_dev, APPDATA_APP_DIR);
        fw2_app_recovery_task();
        if (!recover_interrupted_upgrade()) {
            DIAG("waverider-installer: waiting for recoverable SD state attempt=%u\n",
                 attempt + 1u);
            fw2_app_recovery_sleep_ms(SD_RECLAIM_DELAY_MS);
            continue;
        }
        /* Never truncate the installed UF2. A complete candidate is written
         * and verified first, then promoted with rename while the previous
         * version is retained under /appdata/waverider for recovery. */
        (void)ow_sd_remove(&s_dev, APP_STAGE);
        if (ow_sd_open(&s_dev, &file, APP_STAGE, OW_SD_WRITE) == OW_OK) {
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

    if (!verified_payload_at(APP_STAGE)) {
        DIAG("waverider-installer: staged payload stat mismatch want=%u sdfs=%d\n",
             (unsigned)waverider_payload_len, (int)ow_sd_last_error());
        (void)ow_sd_remove(&s_dev, APP_STAGE);
        return false;
    }
    if (!promote_staged_payload()) {
        return false;
    }
    DIAG("waverider-installer: installed %s (%u bytes); backup=%s\n", APP_PATH,
         (unsigned)waverider_payload_len, APP_BACKUP);
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
        sdfs_status_t sd_error = ow_sd_last_error();
        if (installed) {
            show_status("INSTALL COMPLETE", "HOLD HOME TO EXIT", true);
        } else if (sd_error == SDFS_ERR_NO_CARD ||
                   sd_error == SDFS_ERR_NOT_MOUNTED) {
            /* MAIN can acknowledge the SD-host command while its filesystem
             * remains in the transient `none` state. No app files have been
             * changed on this path; give a public installer user a concrete,
             * recoverable instruction instead of an unexplained failure. */
            show_status("APP SD NOT MOUNTED", "RESTART WILI + RETRY", false);
        } else {
            show_status("INSTALL FAILED", "CHECK DIAGNOSTICS", false);
        }
    }

    for (;;) {
        fw2_app_recovery_task();
        fw2_app_recovery_sleep_ms(20);
    }
}
