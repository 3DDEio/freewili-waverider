# WaveRider

[![CI](https://github.com/3DDEio/freewili-waverider/actions/workflows/ci.yml/badge.svg)](https://github.com/3DDEio/freewili-waverider/actions/workflows/ci.yml)
[![License: GPL v3+](https://img.shields.io/badge/software-GPLv3%2B-blue.svg)](LICENSE)
[![Docs: CC BY-SA 4.0](https://img.shields.io/badge/docs-CC%20BY--SA%204.0-lightgrey.svg)](LICENSES/CC-BY-SA-4.0.txt)

**WaveRider — RTL-SDR Foxhunt** turns a FreeWili 2 with its onboard CM0 and an
RTL2832U/R820T USB receiver into a receive-only 2 m / 70 cm field instrument.

https://hackerwarehouse.com/product/rtlsdr/

WaveRider is currently beta software for FreeWili 2. Read the limitations below
before relying on it in a field event.

## Important current limitations

- **16 frequencies in the Live hunt list.** The Display/Main mailbox is full
  when all sixteen entries are published. Up to 100 additional values can be
  retained in the paged Saved library and toggled into Live as needed.
- **Receive only.** WaveRider never transmits and cannot key a radio.
- **No received audio yet.** The speaker and headphone codec work, but the
  required high-rate CM0-to-Display audio bridge has not been implemented.
- **Morse decoding remains beta.** WaveRider can acquire an NFM Morse audio
  tone across approximately 450–1,150 Hz on the selected frequency. Candidate text is retained
  internally, but a message is not shown as detected until at least three
  recent receptions agree. Noisy, weak, overlapping, or differently pitched
  signals may still be withheld or decode incorrectly. Morse has no letter
  case, so detected text is shown uppercase. WaveRider does not invent or
  dictionary-correct uncertain characters. Exact user-visible field decodes
  are proven at 147.500 and 144.300 MHz with two distinct known payloads; the
  larger efficacy sample and beacon-off false-positive control remain open.
- **Relative RSSI, not calibrated dBm.** Readings are dBFS and are meaningful
  for comparing signal strength while antenna, gain, and attenuation remain
  consistent.
- **Waterfall is a field view, not a laboratory spectrum analyzer.** Each row
  carries twelve measured RF bins which are smoothed and interpolated across
  the screen. Real off-frequency peaks are intentionally not mirrored.
- **Linux/SDR startup is not instant.** The app displays startup progress and
  receiver health while CM0 Linux and the RTL-SDR become ready.
- **Bridge recovery is automatic but bounded.** If the Main-to-Display link is
  lost after WaveRider has been live, the app reopens its local transport and
  makes one best-effort Main-controller-only reset request. CM0 Linux and SDR
  capture are intentionally left running. A deeply wedged Main route cannot
  receive its own reset request; WaveRider then shows **Main Bridge Locked** and
  requires Hardware → Settings → Software Reset (or a power cycle).
- **Live receiver mode and the CM0 maintenance serial console are mutually
  exclusive** on the tested FW2 v07 hardware because the CM0 has one USB
  controller.
- Hardware validation currently covers one FX0177/v07 FreeWili 2 and an
  RTL2838/R820T receiver. Other compatible RTL-SDRs may work but are not yet
  part of the connected-device test matrix.

See [Known limitations](docs/LIMITATIONS.md) for consequences and workarounds,
the [User guide](docs/USER_GUIDE.md) for normal operation, and the
[documentation index](docs/README.md) for the complete project record.

## What it does

- A persistent saved-frequency library with up to 100 values, independently
  managed from the 16-entry live hunt list.
- Large, frequency-only channel rows on the live hunt screen for field readability.
- Exact on-device frequency entry from 24 MHz to 1.766 GHz using cursor-editable
  kHz digits or the touch keypad; no step-size setup is required.
- Fast next/previous frequency selection.
- RTL-SDR connection and live-sample health state.
- Relative RSSI in dBFS with an explicitly labeled waterfall scale.
- A continuous blue-to-yellow RSSI range with a moving live-value pointer.
- A three-second animated WaveRider splash with a detailed swimming orca and
  moving sound-wave surf.
- A short waterfall calibration followed by a stable 30 dB color window, so
  antenna movement remains comparable across time.
- Low-latency native IQ capture targeting 10 analyses per second, with
  complete 100 ms reads and latest-only buffering so the field display cannot
  accumulate stale motion.
- A Settings slider with 25 kHz, 100 kHz, 200 kHz, 500 kHz, 1 MHz, and 2 MHz
  visible spans. Each frequency remembers its selected span.
- A loadable native Display app that reads FreeWili's supported `uartkbd`
  hardware queue directly, bypassing the broken v07 CM0 button relay.
- A compact Main app-signal mailbox carrying button commands, active frequency,
  RSSI, peak, frequency lists, and 12-bin live waterfall rows between the
  Display processor and CM0 service.
- Stock Apps-menu installation without replacing Main or Display firmware.
- A maintenance profile that restores the CM0 USB serial console.
- Seven-LED startup, ready, RSSI, and fault feedback.
- A **Pocket Alert** status page with an adjustable threshold, three-pulse
  alert, 30-second cooldown, 3 dB re-arm hysteresis, and manual Test action.
  Its Display GPIO35 active-high, 12 mA driver and 150/80 ms timing are
  physically verified on production FW2 v07 unit FX0177. Other board revisions
  should run the manual Test before relying on Pocket Alert.
- A Page-key **Settings** hub for Audio Monitor, Waterfall Span, Pocket Alert,
  and CW Decoder.
  Pocket Alert and the persistent CW toggle are functional; Audio exposes its
  future monitor/volume controls as locked until the safe PCM transport exists.
- Plain-language startup, refresh, and receiver-fault status pages.
- Live adaptive-pitch NFM Morse detection with an eight-second `MESSAGE DETECTED`
  overlay plus a frequency-grouped **MSGS** history. The CM0 stores 100
  observations with frequency, last-seen time, repeat count, and confidence;
  the native viewer restores the latest 16 verified records after reconnect.
  A confirmed Clear removes both verified messages and hidden candidates. Dot timing
  is fitted across the complete message, and repeated receptions vote by their
  actual occurrence count. Only bounded decoded ASCII—not PCM—crosses the
  mailbox, so waterfall and controls retain priority.

This software receives only. It does not turn the RTL-SDR into a transmitter.

## Optional development test beacon

[`test-beacon/`](test-beacon/README.md) contains the separately licensed,
optional XIAO ESP32-C3 + NiceRF SA868 fixture used for controlled WaveRider
field tests. It is not installed by WaveRider, is not required by end users,
and does not change WaveRider's receive-only behavior. Its fail-safe updater
stages and reads back the complete CircuitPython program before activation.

## Hardware

- FreeWili 2 with the onboard CM0 and current CM0 Linux image.
- RTL2832U-compatible SDR. The initial test device uses an R820T tuner.
- SDR connected to **Linux USB Host**, the rightmost bottom USB-A socket,
  immediately left of the Main SD card.
- An antenna appropriate for the frequency being monitored. A directional
  antenna is required for meaningful bearing work.

## Install current WaveRider from GitHub

This installs the current release candidate without replacing the stock Main
or Display firmware. The native app is stored on the Main SD card and appears
as **Apps → Radio → WaveRider**.

1. Install Python 3.11 or newer, clone the repository, and install the small
   host-side installer dependency. Confirm `python3 --version` reports 3.11+
   before creating the environment:

   ```text
   git clone https://github.com/3DDEio/freewili-waverider.git
   cd freewili-waverider
   python3 --version
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install '.[installer]'
   ```

   On Windows, use `python` in place of `python3` and activate the environment
   with `.venv\Scripts\activate` instead.

2. Connect the FreeWili 2 built-in CMSIS-DAP probe. Install
   [Raspberry Pi's RP2350-capable OpenOCD](https://github.com/raspberrypi/pico-sdk-tools/releases)
   on `PATH`, then validate and launch the safe SRAM-only app installer:

   ```text
   python tools/fw2_install_native_app.py --dry-run
   python tools/fw2_install_native_app.py
   ```

3. Wait for **INSTALL COMPLETE**, hold Home for five seconds, and put CM0 Linux
   into its maintenance/serial-console profile. Identify its serial port, then
   install and activate the receiver service. Replace the example port as
   needed (`/dev/ttyACM0` on Linux or a COM port such as `COM7` on Windows):

   ```text
   python deploy/serial_install.py --port /dev/cu.usbmodem1701 --activate
   ```

4. The serial port disappears when receiver mode takes ownership of the CM0
   USB controller; that is expected. Return to the home screen and open
   **Apps → Radio → WaveRider**.

For OpenOCD overrides, maintenance recovery, and release verification, see the
[deployment guide](docs/DEPLOYMENT.md).

## Install from a release

The installer is offline-capable and does not replace FreeWili firmware.

1. Boot the CM0 in its normal maintenance/serial-console profile.
2. Download and extract the [latest WaveRider release](https://github.com/3DDEio/freewili-waverider/releases/latest)
   on Windows, macOS, or Linux.
3. Install the host-side installer and image-transfer dependencies:

   ```text
   python3 -m pip install 'pyserial>=3.5,<4' 'freewili>=0.0.51,<1'
   ```

4. Install the native WaveRider Apps-menu application with the built-in
   CMSIS-DAP probe connected. [Raspberry Pi's RP2350-capable OpenOCD](https://github.com/raspberrypi/pico-sdk-tools/releases)
   must be on
   `PATH`, or supplied with `--openocd` and `--scripts`:

   ```text
   python3 tools/fw2_install_native_app.py --dry-run
   python3 tools/fw2_install_native_app.py
   ```

   Wait for **INSTALL COMPLETE**, then hold Home for five seconds. The loader
   runs only from volatile SRAM/PSRAM, fail-closes on any QSPI target, and
   installs the friendly entry at **Apps → Radio → WaveRider**.

5. Identify the CM0 console port:

   - macOS: usually `/dev/cu.usbmodem1701`
   - Linux: usually `/dev/ttyACM0`
   - Windows: a COM port such as `COM7`

6. Install and reboot into receiver mode:

   ```text
   python3 deploy/serial_install.py --port /dev/cu.usbmodem1701 --activate
   ```

The serial port disappearing is expected: the CM0 has one USB controller and
receiver mode routes it to the Linux USB Host socket. The first receiver boot is
guarded for two minutes. If the SDR and on-device display do not both become
live, the installer restores maintenance mode and the serial console returns.

## Repository layout

- `src/` — CM0 Linux receiver, waterfall, Morse, settings, and bridge service.
- `native/` — FreeWili Display app, self-installer, and pinned native artifacts.
- `deploy/` — release builder plus serial and on-device installation scripts.
- `config/` — default field frequencies and service configuration.
- `docs/` — user, deployment, architecture, validation, and limitation records.
- `tools/` — safe device diagnostics, maintenance, and verification helpers.
- `test-beacon/` — optional, separately licensed controlled RF test fixture.
- `tests/` — host-side behavior, safety, native design, and documentation tests.

## On-device controls

- Gray — **Lists:** open the saved-frequency library and live-list manager.
- Yellow — **MSGS:** reopen and browse recent decoded CW observations.
- Green — **Next:** tune the next saved frequency.
- Blue — **Previous:** tune the preceding saved frequency.
- Red — **Refresh:** verify the CM0/SDR connection, restart capture, display
  status, and repaint the waterfall after a new row arrives.
- D-pad Up/Down/Left/Right: browse and immediately tune list entries on the live
  screen. Check applies the highlighted entry.
- Page (or a tap on the RSSI scale) — **Settings:** open Audio Monitor,
  Waterfall Span, Pocket Alert, or CW Decoder. Up/Down selects; Check opens;
  Page returns.

Pocket Alert is source-verified but still beta hardware functionality. Confirm
the manual Test on your FreeWili revision before relying on eyes-free alerts.

In Lists:

- D-pad Up/Down selects a saved frequency; Left/Right changes pages.
- Green or Check adds/removes the selected value from the 16-entry live list.
- Yellow **New** opens exact frequency entry.
- Blue **Tune** adds the selected value to Live when necessary and tunes it.
- Red **Delete** asks for confirmation, then removes the saved value and its
  Live membership.

In MSGS:

- Up/Down or **PREV**/**NEXT** selects a frequency and shows its message count.
- Green, Check, or **OPEN** opens only the messages observed on that frequency.
- **FREQS** returns from a message to the grouped frequency summary.
- Red **CLEAR** opens a confirmation page. Check clears every verified message
  and hidden candidate; Red, Gray, Back, or **CANCEL** preserves them.

In New Frequency:

- Touch the digits to type a kHz value such as `433200`, displayed as
  `433.200 MHz`.
- D-pad Left/Right selects a digit; Up/Down replaces that digit.
- The touch keypad replaces the selected digit and advances the cursor.
- Check saves the value to the library; Red cancels without changing it.

Custom list names and descriptive labels currently require the maintenance
console; exact frequencies can be added and removed entirely on-device.

## Optional device maintenance: quiet and dark startup

This is **not a WaveRider feature or installation step**. WaveRider, its
installer, and its launcher never modify the stock Display firmware or change
the device's startup lights or sounds. Most users should install WaveRider
without applying this separate, device-specific maintenance patch.

The stock LED animation and spoken **Free Wili** boot clip run before
WaveRider, so the app itself cannot suppress them. FW2 v07 omits the relevant
controls from its visible Settings list. The failed settings-file route is now
blocked. A version-locked Display effect-point patch has been deployed to the
connected FX0177 unit and independently read back; verified stock recovery is
retained. The voice suppression is physically proven; V3 LED cold-boot
acceptance is still pending. See
[`docs/NIGHT_DEFAULTS.md`](docs/NIGHT_DEFAULTS.md) for the limitation, exact
evidence, and rollback boundary.

## Return to maintenance mode

From the on-device Linux terminal or another CM0 shell path:

```text
sudo foxhuntctl maintenance --reboot
sudo foxhuntctl lists show
```

After reboot, the CM0 USB serial console returns and the SDR host port is no
longer active.

## Common commands

```text
sudo foxhuntctl doctor
sudo foxhuntctl status
sudo foxhuntctl next
sudo foxhuntctl previous
sudo foxhuntctl logs
sudo foxhuntctl host --reboot
sudo foxhuntctl maintenance --reboot
```

## Frequency lists

Lists live at `/var/lib/freewili-foxhunt/lists/*.json`. They use integer Hz
internally, so saved frequencies do not accumulate decimal rounding error.

The saved library supports up to **100 unique frequencies**. WaveRider pages
that library through its bounded mailbox, while the live hunt screen publishes
and operates on a maximum of **16 entries**. The Lists page shows a `LIVE`
badge beside every saved value currently participating in the hunt rotation.

Each entry supports:

- `frequency_hz`
- a short `label`
- `span_hz`
- `gain_profile`: `auto`, `foxhunt`, `close-in`, or `manual`

The app writes list updates atomically and keeps the previous file as a backup.

Create a custom named list while the maintenance console is connected:

```text
sudo foxhuntctl lists create "Club Foxhunt" 145.565 "Primary fox"
sudo foxhuntctl lists add "Club Foxhunt" 146.565 "Backup fox" --span 500000
sudo foxhuntctl lists move "Club Foxhunt" 2 up
sudo foxhuntctl lists rename "Club Foxhunt" "Saturday ARES Hunt"
```

## Signal units

The default readout is relative dBFS. RTL-SDR gain, tuner variation, antenna
loss, cable loss, and attenuation all affect the number. Absolute dBm is not
shown unless a future calibration profile explicitly supports the complete RF
path. Relative dBFS is still highly useful during a foxhunt: with the gain and
antenna held constant, a less-negative number means a stronger received signal.

## Development

User-visible constraints are part of the product contract. Any newly discovered
limit must be added to `docs/LIMITATIONS.md`; if it can affect installation or
field use, it must also be summarized in **Important current limitations** near
the top of this README. Documentation contract tests keep the current frequency
cap, safety boundary, audio status, and physical button map visible.

Run the test suite:

```text
python3 -m pip install '.[installer,dev]'
python3 -m pytest -q tests
```

Build a GitHub release archive:

```text
sh deploy/build-release.sh
```

GitHub Actions verifies Python 3.11 and 3.13 on every push. Pushing a tag such
as `v0.1.0` runs the test suite, rebuilds and verifies the offline archive, and
publishes both the archive and checksum as a GitHub release.

See the [User guide](docs/USER_GUIDE.md),
[Known limitations](docs/LIMITATIONS.md),
[Architecture](docs/ARCHITECTURE.md), [Deployment](docs/DEPLOYMENT.md),
[Splash assets](assets/splash/README.md), and
[Troubleshooting](docs/TROUBLESHOOTING.md). The public product name is
**WaveRider**; remaining work is tracked in [the backlog](docs/BACKLOG.md).

## Project governance

WaveRider is developed in public at
[`3DDEio/freewili-waverider`](https://github.com/3DDEio/freewili-waverider).
The `main` branch is protected: changes are expected to arrive through pull
requests, pass CI, and receive owner review. See [Contributing](CONTRIBUTING.md)
and the [Security policy](SECURITY.md). The repository's pre-public work is
recorded honestly in [Project history](HISTORY.md); it is a reconstructed
milestone record, not fabricated Git history.

## Credits

WaveRider was created by **KO6FQY** and **KO6FQJ**, with contributions from
the WaveRider community. The device also contains a small animated creator
credit for curious operators to discover.

## Current beta boundary

The RTL-SDR capture, persistence, health reporting, recovery profiles, native
screen, exact-frequency editor, all five context buttons, D-pad/Check tuning,
RSSI, and live waterfall have been exercised on FW2 v07 hardware (FX0177) with
an RTL2838/R820T receiver. The connected pipeline has sustained approximately
5 committed waterfall rows per second with no unbounded queue growth. Known
13 WPM / 800 Hz beacons have decoded with 100 percent displayed character
accuracy at both 147.500 MHz (`KO6FQY JOIN NORCALCYBER.IO! KO6FQY`) and
144.300 MHz (`KO6FQY -- DECOY DECOY -- KO6FQY`) after the three-reception
consensus gate. Final field acceptance still requires the larger efficacy
sample, a beacon-off false-positive control, and the remaining RSSI/LED,
startup, waterfall, and message-management observations in the completion
audit.

Planned next: a dedicated bounded PCM bridge for optional narrow-FM speaker and
headphone audio, with on-device volume, output, squelch, and mute controls.

## License

WaveRider software is licensed under
[GNU GPL v3 or later](LICENSE). Redistributed software and derivative works
must remain available under the GPL with corresponding source; the GPL does
not permit someone to convert the copyrighted WaveRider codebase into an
incompatible proprietary release.

Documentation and original artwork are licensed under
[Creative Commons Attribution-ShareAlike 4.0](LICENSES/CC-BY-SA-4.0.txt).
Third-party components retain their own licenses. See [Licensing](LICENSES.md)
and [Third-party notices](THIRD_PARTY_NOTICES.md). FreeWili and related marks
belong to their respective owners; WaveRider is an independent project.
