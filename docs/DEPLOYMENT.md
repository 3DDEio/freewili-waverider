# Deployment and releases

## Maintainer release checklist

1. Confirm FreeWili has explicitly licensed or granted redistribution
   permission for the pinned OneWili source. A public checkout without a
   license file is not permission; this is a stop-ship gate.
2. Clone with `--recurse-submodules`; run `python3 tools/prepare_wilibsp.py`
   and `python3 wilibsp/tools/check_app_repo.py .`. Both pinned commits must
   match before reviewed patches are applied.
3. Run the Python tests on 3.11 and 3.13.
4. Run `sh -n` against every shell script.
5. Rebuild the native images with Pico SDK 2.3.0 and Arm GNU Toolchain
   14.2.Rel1, then verify checksums and SRAM-only UF2 targets:

   ```text
   export PICO_SDK_PATH=/path/to/pico-sdk-2.3.0
   export PICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-14.2.Rel1
   # Optional prebuilt Picotool CMake package:
   export PICOTOOL_DIR=/path/to/picotool/cmake/package
   sh deploy/build-native-apps.sh
   sha256sum -c native/dist/SHA256SUMS
   python3 wilibsp/tools/check_app_uf2.py native/dist/waverider_display.uf2
   python3 wilibsp/tools/check_app_uf2.py native/dist/waverider_installer.uf2
   ```

   GitHub's Linux runner uses `deploy/setup-native-ci-linux.sh` to fetch these
   same inputs from their publishers, verify their SHA-256 digests, rebuild
   both UF2 files, and byte-compare them with the release candidates.

6. Build the device archive with `sh deploy/build-release.sh` and the complete
   source archive with `sh deploy/build-source-release.sh`; verify both
   checksums plus the Debian corresponding-source checksums.
7. Extract the archive into a clean directory. Run the native installer's
   `--dry-run`, inspect the strict CM0 serial manifest, and confirm no local
   toolchain, secret, backup, or hardware dump entered the bundle.
8. Upload and preview the splash plus continuous RSSI scale through the Main
   serial port with `deploy/fw2_asset_upload.py --port PORT --show`.
9. Install the rebuilt native app on the release device. Confirm the staged
   installer reads back every byte, retains the previous UF2 under
   `/appdata/waverider/`, and shows **INSTALL COMPLETE**.
10. Launch **Apps → Radio → WaveRider**, hold Page for five seconds, and verify
    the standard About screen shows version `001` plus the public repository.
11. Install the archive onto a clean/current CM0 in maintenance mode.
12. Run `sudo foxhuntctl doctor` before host activation.
13. Activate host mode and verify an RTL2838/R820T device is present.
14. Confirm `/run/freewili-foxhunt/status.json` reaches `state: live` with both
   `sdr_connected` and `display_connected` true before the two-minute guard ends.
   Record `waterfall_row_rate_hz`, `display_push_ms`, and `sdr_queue_depth`; a
   stable field build must sustain at least 3.0 committed rows/second without a
   growing SDR queue.
15. Confirm the splash remains visible for approximately three seconds, then
    switches to the live panel.
16. Run the nine connected observations in `docs/COMPLETION_AUDIT.md`, including
    RSSI/LED motion, span persistence, saved-list management, CW history/Clear,
    and a timed untouched cold launch.
17. Switch to the second saved frequency and verify the center changes.
18. Restore maintenance mode and confirm the USB serial console returns.
19. Merge through protected `main`, verify both CI jobs on the merged commit,
    and only then create the exact matching version tag. Confirm the workflow
    attaches both `.uf2` files directly, not only the archive.

Publish the device-install `.tar.gz`, complete-source `.tar.gz`, both checksum
sidecars, both validated `.uf2` files, `native/dist/SHA256SUMS`, and release
notes on GitHub. GitHub's generated tag archive preserves submodule gitlinks
but not their contents; the separately generated complete-source archive is
the durable offline rebuild input. The device-install bundle is deliberately
not a standalone native-source tree.
Do not
publish a supported binary release while OneWili redistribution permission or
any connected-device acceptance item remains open.

The included release workflow performs the archive/checksum build and uploads
those files when a `v*` tag is pushed. Use a prerelease tag and mark the GitHub
release as prerelease until the connected-hardware checklist above passes.

### Maintainer live-fix deployment

When an older WaveRider service is already producing enough bridge traffic to
interfere with maintenance commands, use the single-session live-fix helper
after Main responds to `tools/fw2_main_probe.py`:

```text
python3 tools/fw2_deploy_live_fix.py --port /dev/cu.usbmodemFX01771
```

The helper opens one correlated CM0 shell, stops WaveRider, backs up the
runtime modules, uploads checksum-verified candidates, and compiles them. On
FX0177 v07, do not start or validate the display while that routed shell is
attached: Main suppresses GUI-console acknowledgements until the login shell
exits. Use `tools/fw2_start_waverider_detached.py` after deployment; it enables
the service, schedules its start, and cleanly detaches before the display opens.
Runtime validation may reconnect only after the panel has initialized, and must
detach again before judging continued row cadence or buttons. It fails
validation if the SDR or Display is not live, if the measured waterfall
rate is below 3.0 Hz, or if the journal contains a correlated-batch failure. Use
`--min-row-rate HZ` only when testing a deliberately different acceptance gate. It
restores the backups and restarts the old service if installation fails. This is
a maintainer recovery tool; public installs should continue to use the release
archive workflow.

After that cadence gate passes, prove the physically reliable D-pad event path
and retune as one observable transaction:

```text
python3 tools/fw2_verify_native_buttons.py \
  --port /dev/cu.usbmodemFX01771 --button dpad --timeout 35
```

Wait for its `READY` line, then press D-pad Down once. D-pad movement applies
the selected row immediately, so no Green/Check confirmation is required. The
verifier passes only when both the selected row and tuned frequency change.
WaveRider also treats each frequency row as a direct touch target; tapping a
row applies it immediately. Green and Check remain apply aliases on keyboard
firmware that reports those context-key edges.

### Native Apps-menu installer

WaveRider's physical controls run in a loadable Display app. The app and its
self-installer are ordinary volatile FreeWili BSP applications; neither UF2
contains a stock DISPLAY-QSPI payload. The self-installer uses Main's supported
SDFS service to create:

```text
/apps/Radio/waverider_display.uf2
```

Rebuild both artifacts from the pinned external-project tree and run the
fail-closed checks before touching hardware:

```text
export PICO_SDK_PATH=/path/to/pico-sdk-2.3.0
export PICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-14.2.Rel1
# Optional prebuilt Picotool CMake package:
export PICOTOOL_DIR=/path/to/picotool/cmake/package
sh deploy/build-native-apps.sh
sha256sum -c native/dist/SHA256SUMS
python3 wilibsp/tools/check_app_uf2.py native/dist/waverider_display.uf2
python3 wilibsp/tools/check_app_uf2.py native/dist/waverider_installer.uf2
python3 tools/fw2_install_native_app.py --dry-run
```

With the built-in CMSIS-DAP debug probe connected, launch the installer from
volatile SRAM/PSRAM:

```text
python3 tools/fw2_install_native_app.py
```

The loader validates the embedded WaveRider UF2 as SRAM-only, rejects any
installer ELF segment outside the documented volatile SRAM/PSRAM windows,
halts both display cores, quiesces peripheral DMA, uses OpenOCD `load_image`
plus `verify_image`, and never invokes `program` or a flash-write operation.
The on-device installer writes a separate staging candidate and reads every
byte back before promotion. It retains the prior app at
`/appdata/waverider/waverider_display.previous.uf2`, restores it if promotion
or final verification fails, and recovers a verified backup or staging file if
power was lost between the rename operations.

Wait for **INSTALL COMPLETE** on the device, then hold Home for five seconds.
WaveRider can thereafter be launched from **Apps → Radio → WaveRider** or with:

```text
python3 wilibsp/tools/fw.py run-app Radio/waverider_display.uf2
```

This is currently the maintainer recovery path for Macs on which the USB-muxed
Main SD card does not enumerate. Public packages may instead use `fw install-app`
when the removable volume mounts normally.

## Offline dependencies

Release archives include the official Debian Trixie arm64 `librtlsdr0` and
`rtl-sdr` packages. The installer verifies both release SHA-256 values and
requires the exact `2.0.2-2+b1` package versions, reinstalling the pinned pair
when the CM0 differs. Their checksums must be verified against Debian package
metadata before every version update.

## Serial installer behavior

`deploy/serial_install.py` creates a temporary archive from an explicit CM0
runtime allowlist, transfers it as base64 over the CM0 serial shell, verifies
SHA-256 on the device, extracts it under `/tmp`, and runs `install.sh`.
Untracked files, local toolchains, hardware dumps, the native app, and
maintainer-only firmware tools cannot enter that transfer. `--activate`
selects host mode only after a successful install.

The CM0 installer compiles a complete staging runtime before changing the live
tree, then promotes it with a same-filesystem rename. Removed source files
cannot linger across upgrades, and the immediately prior tree remains at
`/opt/freewili-foxhunt.previous` for rollback inspection. It also backs up the
two command wrappers and two systemd units and restores those files plus the
previous runtime if integration installation or `daemon-reload` fails, avoiding
a mixed-version upgrade. HUP, INT, and TERM during the integration transaction
take the same complete rollback path. Persistent lists, settings, and message
history remain under `/var/lib/freewili-foxhunt`.

On FW2 v07, prepare Linux before invoking the Main-routed installer:

1. From the home screen, open Wi-Li-nux → Linux Terminal and press the Yellow
   **Enable** action. The serial `l\\a` acknowledgement alone is not proof that
   the Linux application actually began its boot sequence.
2. In Hardware → Power Management, confirm FPGA zone 6 and CM0 zone 17 are on.
3. Confirm `CM0_RUNPG` is released; use Set CM0 Run Line → `1` if it is held in
   reset.
4. After Linux has had its boot window, press physical **Home**. Do not press
   Disable.
5. Physically reset **Main only** to release the route retained by the on-device
   terminal, then leave the Linux app closed.
6. Require a successful `fw2_main_probe.py` response and let the installer or
   live-fix helper perform the first and only Open Shell request.

The on-device terminal and a host-side Main-routed shell are mutually exclusive
on the tested v07 unit. Merely returning Home did not restore Main serial; a
Main-only physical reset was required while leaving the already-enabled CM0
running. The tunnel submits Linux commands with carriage return. `serial_install.py`
handles that constraint and uploads the archive as short, individually
acknowledged, restartable shell commands. It never enters a multiline decoder,
and refuses to extract any archive whose SHA-256 does not match. Main-SD splash
assets are deliberately excluded from this CM0 transfer and remain present in
the public release archive.

The host shell and WaveRider's live Display traffic are also mutually exclusive
on this v07 unit. A routed shell may be used to install or inspect, but its login
shell must exit before WaveRider builds or updates its panel. Closing the Mac
serial file alone does not detach the Main shell session.

The serial installer does not update FreeWili firmware or rewrite either SD
card image. `foxhuntctl host` enables a one-shot safety service. A failed SDR or
display check restores the exact maintenance USB settings and reboots, making
the serial console available again.

## Legacy Main-SD UI assets

The current native Apps-menu build animates the three-second surfing-orca and
sound-wave splash and draws the continuous RSSI scale itself. It does not depend on an image
file, Main-SD mount state, or FW2's picture-control lookup rules. Tap the
`WaveRider` title to replay the splash for verification.

The older `WAVERIDR.FWI` and `RSSISCL.FWI` assets remain in the repository for
compatibility with the earlier CM0-rendered panel. The optional host-side
helper uploads them to `1:/images/WAVERIDR.FWI` and
`1:/images/RSSISCL.FWI` using Main firmware's checksummed transfer protocol.

Recreate and install those legacy assets with:

```text
python3 deploy/fw2_asset_upload.py --port /dev/cu.usbmodemFX01771 --show
```
