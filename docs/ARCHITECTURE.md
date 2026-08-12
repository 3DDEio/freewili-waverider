# Architecture

## Runtime boundary

`freewili-foxhunt.service` runs on the onboard CM0. It owns the RTL-SDR process,
parses FFT rows, reduces them to display width, maintains receiver health, and
publishes compact values through Main's app-signal mailbox.

Colored-button state comes from FreeWili's Display-side `uartkbd` driver. The
native app consumes press edges directly, so a held key performs one action,
then writes a sequence-numbered command to `wr_cmd`. The field editor avoids
depending on typed dialog return values: touch or D-pad input edits seven
integer-kHz digit positions locally, then sends one exact value. The Lists
workspace pages a 100-entry saved library through the same sixteen frequency
slots and carries Live membership in otherwise-idle row signals. Custom names
still use `foxhuntctl lists` in maintenance mode.

The application does not replace the main or display firmware.

A separate Main-side **WaveRider** launcher owns only the one-tap startup
sequence: power FPGA/CM0, release CM0 reset, invoke stock Linux enable, wait for
bounded readiness, and reveal the persistent panel. The launcher never performs
FFT or SDR work and must reuse the stock v07 Apps-menu mechanism. See
`LAUNCHER.md`.

## Data path

```text
RTL-SDR
  -> librtlsdr synchronous IQ blocks
  -> eight-window, 256-point FFT average
  -> normalized SpectrumRow
  -> validation and bin reduction
  -> relative RSSI and peak detector
  -> two-second display calibration, then stable color range
  -> 12-bin peak-preserving waterfall row
  -> sequence-committed Main app-signal mailbox
  -> native Display framebuffer and LEDs
```

The primary capture path calls the already-installed `librtlsdr.so.0` through
Python's standard-library `ctypes`. It reads IQ continuously, averages eight
Hann-windowed 256-point FFTs, consumes a complete 100 ms IQ block per read, and
keeps only the two newest rows. This remains offline-installable and requires no compiled Python
extension or NumPy on the 416 MiB CM0. The older distro-provided `rtl_power`
worker remains the automatic fallback if the shared library is unavailable.

The live IQ worker also feeds an experimental narrow-FM Morse branch. It uses
phase-difference demodulation at approximately 16 kHz, removes WaveRider's
known RTL tuner offset, and searches a bounded CW audio range in 20 ms Goertzel
windows while reporting the detected tone lock.
The timing decoder retains tone and silence durations for a complete message,
then fits the dot unit against all 1/3 mark and 1/3/7 gap ratios before
classifying any character. This prevents a fast beacon's first dash from being
classified using the slower startup guess. Confidence combines timing
residuals, known-pattern coverage, and tone evidence; disagreeing callsign-
shaped bookends invalidate the candidate.
Before classification, sub-dot tone interruptions and noise spikes are merged
back into their surrounding run. A one-second end guard prevents long word
spacing from prematurely emitting a fragment as a complete message.
Tone detection uses separate acquisition/release thresholds: a new mark needs
strong spectral evidence, while a locked mark tolerates modest fading. Dot-unit
adaptation is bounded between messages so noisy candidates cannot drag the
decoder from a measured 20 WPM signal toward an implausible slow timing model.
Only a bounded decoded text event leaves the CM0; raw PCM is not sent through
the app-signal mailbox. Text is transported in sequenced six-byte chunks. A
zero-span marker identifies a live detection and a one-hertz span identifies a
silent history replay; neither can collide with a valid WaveRider tuning frame.
The first 11 payload bytes carry exact frequency kHz, repeat count, confidence,
and `HH:MM`; up to 79 printable text bytes follow without adding signal slots.

`MessageStore` atomically persists up to 100 observations in `messages.json`.
Similar receptions on the same frequency are conservatively coalesced. Per-
variant occurrence counts feed an aligned consensus, and a record remains an
internal candidate until at least three receptions have sufficient decoder
quality and agreement. On display connect, the CM0 replays the latest 16
verified records without triggering old popups. The native app caches that
bounded page, groups it by exact frequency, and owns MSGS navigation locally,
so reviewing history does not interrupt SDR capture. A confirmation-gated
native command clears both the cache and the complete atomic CM0 store,
including candidate records that are deliberately absent from the viewer.

On FX0177 with the RTL2838/R820T test receiver and a 200 kHz span, the native
worker produced 20 rows in 2.908 seconds (6.88 rows/second including device
open, tuning, and close). Capture is therefore no longer the dominant latency.

## Display path

The production service uses `NativeSignalDisplay`. In Live mode it publishes `wr_freq`,
`wr_span`, `wr_rssi`, `wr_peak`, three packed waterfall words, selected index,
and up to sixteen list frequencies. `wr_seq` is written last, so the Display app
never renders a partially updated frame. Display commands use
`sequence << 8 | opcode << 4 | argument`; Green sends Next, D-pad changes the
local cursor, and Check/Nav-center sends an explicit selected index.

In Lists mode, those same sixteen `wr_f*` slots carry a page of exact integer
kHz values. The low 16 bits of `wr_row0` carry the page's Live-membership mask
and its next five bits carry the global Live count; `wr_row1` carries
saved-library count, and `wr_row2` carries page offset. No
waterfall rows are published while this mode is active, so the bounded
32-signal mailbox does not grow.

The native app is a normal SRAM-targeted FreeWili BSP application installed at
`/apps/waverider/waverider_display.uf2`. It owns the 480 x 320 framebuffer,
continuous RSSI scale, waterfall centerline, button footer, and top LED meter.
Holding Home for five seconds returns to the stock recovery loader. Main and
Display firmware remain unchanged.

Pocket Alert's sequencer runs on the Display CPU. Its GPIO46 active-high output,
12 mA drive, and 150 ms pulse / 80 ms gap timing match the FreeWili Meshtastic
port recovered from the installed app; the evidence and checksums are recorded
in `docs/HAPTIC_EVIDENCE.md`. CM0 atomically persists the enabled flag and
integer dBFS threshold in `pocket-alert.json`. To stay
within Main v07's 32 named-signal
limit, Live mode packs list count in the low byte of `wr_count`, enabled in bit
8, and the threshold offset from -90 dBFS in bits 9..15. Opcodes 14 and 15
persist changes. The sequence is nonblocking (three 150 ms pulses separated by
80 ms), so it never sleeps or delays RSSI/waterfall polling.
Normal triggers use both a 30-second cooldown and 3 dB hysteretic re-arm.

The older stock-panel transport remains useful for maintenance diagnostics. It
connects directly to `/run/fwcm0-bridge.sock` using the documented
length-prefixed `OP_CONSOLE` request, but v07 cannot relay physical buttons to
CM0 and is no longer the production input path.

On tested FX0177 v07 firmware, Main stops acknowledging `OP_CONSOLE` GUI
commands while its routed `TYPE_SHELL` Linux session is attached. The same
clean bridge that timed out on `g\\c\\a` and `g\\e\\a` with the host shell open
created a panel and committed a 12-bin row immediately after that login shell
exited. Deployment and launch therefore use the routed shell only for bounded
maintenance, schedule WaveRider to start after detach, and never keep a host
shell attached during live display or button operation.

Some CM0 images ship an older generated Python surface without the current
`add_waterfall` method. The compatibility shim emits the same documented
`g\b\m` wire command using the generated encoder; it does not patch the vendor
installation.

The dynamic-panel state is retained by the display controller. At each attach,
the app recreates dynamic panel index 0 directly before rebuilding its controls;
the legacy `s\\f\\r` path is not acknowledged on the tested clean FX0177 v07
firmware. A failed
display call drops only the UI adapter; the SDR worker keeps running and the app
retries the panel connection every five seconds.

Each FFT row is staged bin-by-bin and then committed by changing the waterfall
control value. FW2 v07 can complete Main-host and Display acknowledgements out
of order on the shared bridge, so the transport correlates response paths and
pipelines a 12-bin row, its live text, and its commit in bounded microbatches.
The production window is selected by a clean-bridge hardware benchmark rather
than the rejected 32-command single window. The palette honors the saved floor and ceiling when they fit the live
data. Otherwise it calibrates a 30 dB window against the median RF noise for 12
rows, then freezes that range until retune or gain change. An instantaneous
peak never changes the scale, so the same color retains the same relative dBFS
meaning across antenna movement. Runtime status records measured waterfall row
rate, Display push latency, and SDR queue depth for field validation.

## Receiver-mode guard

`freewili-foxhunt-guard.service` treats the first receiver boot as a
transaction: both the SDR and display bridge must report live within two
minutes. On failure it restores the exact peripheral-mode and USB-mux boot
lines, disables the app, and reboots back to the console.

## USB profiles

The CM0's only USB controller cannot expose its external serial gadget and the
RTL-SDR host port simultaneously on the tested firmware.

- Maintenance: `dr_mode=peripheral`, GPIO2 low, GPIO3 high.
- Foxhunt: `dr_mode=host`, GPIO2 high, GPIO3 high.

`foxhuntctl` changes only those exact boot lines and refuses to continue when
the expected configuration is absent. Host activation is explicit; installation
alone never changes the boot profile. Replacement is performed before checking
whether the requested value appears elsewhere, because a board-filtered example
must not mask the still-active USB-role line.

## Planned audible audio path

The FreeWili 2 playback hardware is suitable: WiliBSP proves the NAU88C10 codec,
fixed approximately 16 kHz I2S playback, onboard speaker, 3.5 mm headphone
output, and independent speaker/headphone routing. The speaker is rated at
0.5 W maximum; WaveRider must retain the BSP's speaker-volume safety cap and
enter the codec's speaker low-power state whenever muted.

The current application boundary does not yet carry audible PCM. NFM tone
analysis for Morse already branches locally from CM0's tuned IQ stream, but
general audio playback still needs de-emphasis and squelch while the playback
codec and I2S DMA are owned by the RP2350 Display CPU. The current Main
app-signal mailbox is intentionally sized for controls, twelve waterfall bins,
and bounded text events; it cannot safely transport 16 kHz PCM.
The existing USB audio-stream helper carries the device microphone toward a
host and is not a CM0-to-speaker playback route.

Real received audio therefore requires a dedicated bounded PCM transport from
CM0 to Display. That transport must use short sequence-numbered frames, a small
jitter buffer, and drop-oldest behavior so it can never back-pressure FFT,
RSSI, waterfall, controls, or recovery. Only after that bridge passes cadence
and recovery tests should the UI expose an Audio page with Mute, Volume,
Squelch, and Output choices for Speaker, Headphones, or Both. Audio defaults to
muted after install and after any receiver fault.

## Persistent data

- Application: `/opt/freewili-foxhunt`
- Lists: `/var/lib/freewili-foxhunt/lists`
- Saved-frequency library: `/var/lib/freewili-foxhunt/frequency-library.json`
- Runtime status: `/run/freewili-foxhunt/status.json`
- Logs: system journal for `freewili-foxhunt.service`

## Recovery guarantee

`foxhuntctl maintenance --reboot` disables the service and restores the serial
gadget lines. The first receiver boot rolls back automatically if its readiness
check fails. Uninstall keeps user lists unless `--purge` is explicitly passed.
