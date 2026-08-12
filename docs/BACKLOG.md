# WaveRider backlog

The requirement-by-requirement connected-device exit gate is maintained in
`docs/COMPLETION_AUDIT.md`. Host tests and injected input do not close physical
hardware observations in that audit.

## Approved product decision

The user-facing application name is **WaveRider**. Until the live RF cadence
gate passes, source packages, services, installer paths, and release archives
retain the current `freewili-foxhunt` names to avoid a partial migration during
hardware bring-up.

## Gate: responsive field sampling

External test beacon recovery (2026-08-11): the XIAO ESP32-C3's persistent
`code.py` had been replaced by a 22-byte `print("Hello World!")` program. The
separate recovery package now configures its healthy SA868 for low-power
147.500 MHz operation and completed one error-free transmit/idle software
cycle. Confirm over-the-air reception before using it to close WaveRider's
known-RF validation gates; transmitter firmware remains separate from
WaveRider.

Brand migration begins after the connected device demonstrates:

- RSSI response within one second of antenna movement;
- stable, comparable waterfall colors across time;
- no steadily growing IQ/sample backlog;
- an acceptable end-to-end waterfall row rate on the stock display bridge;
- working yellow/green quick retuning after sustained streaming.

## WaveRider naming migration

- [x] Change the on-device panel title and status identity to `WaveRider`.
- Use `WaveRider — RTL-SDR Foxhunt` as the descriptive subtitle.
- Rename release archives, screenshots, and public documentation.
- [x] Publish the project as
  [`3DDEio/freewili-waverider`](https://github.com/3DDEio/freewili-waverider).
  The first public Git history is an honest initial import; earlier milestones
  are reconstructed in `HISTORY.md` rather than represented by fabricated
  commits.
- Preserve `foxhuntctl`, `freewili-foxhunt.service`, installed list paths, and
  upgrade compatibility unless a migration provides explicit aliases and
  rollback coverage.
- [x] Add a three-second native 480 x 320 WaveRider splash. The current build
  procedurally animates a gently bobbing, tail-kicking orca above three
  phase-shifted sound-wave surf bands. The detailed silhouette includes a
  cyan rim, white eye patch/belly/chin, gray saddle, tall dorsal, pectoral fin,
  and articulated flukes, so launch no longer depends on a
  compatible Main-SD image. The calm 10 FPS loop remains recovery-responsive
  and measures its three seconds against wall time rather than adding render
  time. Tapping the `WaveRider` title replays the splash for field verification;
  legacy converter/uploader assets remain available for older builds.

## Current milestone: original-mockup parity

- [x] Publish GitHub-facing user documentation with visible limitations. The
  repository README now highlights the 16-entry list cap, receive-only scope,
  unavailable audio, relative dBFS, twelve-bin interpolated field waterfall,
  startup delay, USB-mode conflict, and tested hardware boundary. Detailed
  operating instructions live in `docs/USER_GUIDE.md`; the maintained product
  constraint register lives in `docs/LIMITATIONS.md`.

- [x] Add a one-tap stock Apps-menu launcher named **WaveRider**. It must power
  FPGA/CM0 as needed, release CM0 reset, invoke the stock Linux-enable path,
  wait for bounded readiness, and reveal the service without opening Linux
  Terminal. First inspect and reuse the installed v07 Wi-Li-nux menu-registration
  mechanism; do not ship a replacement Main UF2. See `docs/LAUNCHER.md`.
  The installed native app now accepts Main v07's ten-byte whole-power-mask
  envelope, applies the CM0/FPGA awake mask, reports the settled mask back to
  Main, and starts receiving live CM0 rows without a Terminal launch.

- [x] Show `WaveRider` in the live panel header.
- [x] Restore the original mockup palette on the native RGB565 framebuffer:
  charcoal background, dark blue-green panels, white/muted frequency text,
  mint active state, and physical-key accent colors. Connected framebuffer
  captures verified both the live panel and native splash; abbreviated web
  colors are no longer interpreted as raw RGB565 values.
- [x] Keep the active list name out of the live view; show it only in Lists with an
  `ACTIVE` marker.
- [x] Use large, frequency-only channel rows in the narrow live-view rail;
  preserve descriptive labels in Lists/editor rather than shrinking the hunt text.
- [ ] Replace the progress fill with a continuous RGB565 blue-to-yellow relative-dBFS range,
  repainting pointer, live numeric value, and -70 / -50 / -30 / -10 field legend.
  The original space-padded pointer collapsed to the cold edge because v07
  strips leading command whitespace. A bridge-safe hyphen track with a moving
  `V` is implemented; validate its motion on connected hardware before closing.
  The native scale now clears the complete previous marker footprint, redraws
  the gradient, and overlays only a two-pixel instantaneous marker so RSSI
  updates cannot accumulate a white history trail. All host checks and the
  SRAM-only installer gate pass; persistent device installation is waiting for
  the FreeWili CMSIS-DAP/debug USB connection to be visible to the Mac.
- [x] The first bordered-button workflow was physically validated: Add inserted,
  Remove deleted, Next/Previous tuned both directions, and Refresh showed
  status and repainted the waterfall. It is now superseded by the library
  workflow below; the proven Next, Previous, and Refresh actions are retained.
- [ ] Add the full-screen Frequency Library and revised field controls: Gray
  **Lists**, Yellow **Messages**, Green **Next**, Blue **Previous**, and Red
  **Refresh** on Live; Back, New, Live +/-, Tune, and confirmed Delete inside
  Lists. Saved storage is atomically persisted up to 100 unique values while
  the mailbox-bounded Live rotation remains 16. Paging, Live membership, Tune,
  and delete propagation are implemented and host-tested. The native and CM0
  builds are now installed; injected connected controls saved 433.200 MHz,
  toggled it into Live, displayed `LIVE 11/16`, and retained that state across
  a CM0 service restart. The pass also fixed stale global-count publication and
  ordered `00-` source-list persistence. Validate all paths on physical buttons
  and touch, then repeat after cold power restoration.
- [ ] Replace Add's temporary +25 kHz behavior with exact frequency entry. The
  native editor now uses seven direct integer-kHz digit positions instead of a
  configurable step: touch types and advances, Left/Right moves to an incorrect
  position, Up/Down replaces that digit, Check saves, and Red cancels. Explicit
  24 MHz..1.766 GHz bounds and duplicate rejection remain. The one-shot kHz value
  reuses `wr_state` because Main v07's 32-signal mailbox is full when all
  sixteen list entries are published; adding a 33rd named signal fails.
  Connected AgentIO validation entered and saved 433.200 MHz using six direct
  keypad digits. Validate cursor correction and the same save path with the
  physical D-pad/Check controls.
- [ ] Replace the coarse twelve-block waterfall row with a continuous measured
  spectrum. CM0 now applies a small three-tap linear-power smoother after
  peak-preserving reduction, and Display interpolates between the twelve
  measured mailbox bins across all 324 plot pixels. This produces a hot core
  with cooling shoulders without mirroring data or hiding a genuinely
  off-frequency beacon/interferer. Validate against a known carrier.
- [x] Restore the core physical tune inputs. The stock FW2 v07 relay remains unusable:
  its documented stream emits no `button` frames and synchronous `g\\u` is
  empty. WaveRider now has a loadable, SRAM-only native Display app that reads
  the supported `uartkbd` driver directly and exchanges compact commands/data
  with CM0 through Main's app-signal mailbox. The complete host/deployment
  suite passes as part of the current 143-test regression set. A
  connected synthetic-input test proved Green changes the selected row and
  retunes the SDR from 147.495 to 147.545 MHz through the complete
  Display-to-Main-to-CM0 mailbox. Direct keyboard diagnostics show healthy,
  error-free PIC frames but have not yet observed a physical Green/Check edge,
  even in the independent upstream `hello_keyboard` app. The current official
  WiliBSP parser matches the pinned local mapping. D-pad movement now applies
  an absolute tune immediately (instead of requiring Green/Check), and direct
  frequency-row taps provide a second controller path; both passed full
  Display-to-Main-to-CM0 synthetic tests and changed `wr_sel` plus `wr_freq`.
  The user has now physically confirmed D-pad and Check tuning on this unit.
- [ ] Provide explicit startup and health feedback instead of appearing frozen.
  The native app now presents staged CM0/Linux/SDR startup progress, elapsed
  time, a Receiver Status page with link/stream/last-row/command state, and a
  bounded Refresh page that returns to live only after a new row arrives.
  When live data becomes stale for three seconds, the same yellow LED fault
  state now replaces the waterfall with **Receiver Needs Attention**, the CM0
  and SDR state, last-row age, command state, and a plain Refresh/USB action.
  A recovered SDR row restores the waterfall automatically. A fresh-boot test
  then exposed a distinct v07 race: RTL-SDR sampling was live at 5.32 rows/s,
  but Main retained a routed `TYPE_SHELL` login and blocked Display app-signal
  traffic. WaveRider now waits through a 20-second boot grace and, only if the
  Display has never connected, hangs up the exact bridge-owned `login -f pi`
  process during a bounded 90-second startup window. The bridge's existing
  `SHELL_EXIT` notice releases Main without restarting Linux, the bridge, or
  the SDR. An explicit maintenance inhibit prevents deployment tools from
  being mistaken for an orphaned boot shell. The installed `app.py` and
  `bridge_recovery.py` hashes match the working tree, the service is active,
  and one non-shell mailbox sample reported `wr_ready=1`, `wr_seq=64`, and
  live RSSI. A subsequent physical launch exposed an approximately two-minute
  healthy startup that looked like a fault because all seven LEDs blinked
  amber. The CM0 service no longer orders itself after the complete
  `multi-user.target`; it can start as soon as `fwcm0-bridge.service` is ready.
  RTL-SDR capture now starts before the Display mailbox handshake, and warm
  relaunches skip 32 redundant app-signal creation round trips when the v1
  protocol marker is already present. The native startup display now advances
  through six measured subsystem milestones with dim, steady green LEDs from
  left to right; the seventh LED is earned by the first live SDR row. Yellow
  flashing is reserved for a real post-startup data fault. Repeat one untouched
  cold launch with a stopwatch to close this gate and record time-to-first-row.
  The first timed physical observation was substantially faster and reached
  four green milestones immediately before entering the waterfall. Because
  the remaining milestones completed between LED refreshes, the final build
  now holds all seven green for three seconds as an explicit ready confirmation
  while the waterfall renders normally; it does not artificially delay startup.
  A later post-connect failure proved that startup-only shell cleanup was not a
  complete runtime recovery strategy: the native app could remain on **Waiting
  for CM0 Bridge** indefinitely after losing its OneWili transport. The display
  app now classifies only timeout/I/O/protocol failures as a broken transport,
  reopens that transport after three seconds, and requests at most one Main-only
  software reset after fifteen seconds. A missing app signal during healthy CM0
  startup does not enter this reset path. CM0 Linux and the SDR are preserved.
  Host regression and SRAM packaging gates pass. Connected validation against
  the stalled physical unit proved the deepest v07 lock cannot receive its own
  software-reset request over the jammed OneWili route. The app now replaces
  indefinite waiting with **Main Bridge Locked** and exact physical reset
  guidance. Automatic out-of-band Main reset remains open; do not manipulate
  the power-coprocessor's reserved reset bits without a board-revision-safe
  vendor contract. That validation also caught partial mailbox replies: cached
  list/settings signals could still answer while the committed live-row
  `wr_seq` path was dead, repeatedly clearing the recovery timer. Recovery
  health is now owned only by `wr_seq`; secondary signal reads can no longer
  hide a dead receiver mailbox. Startup also queues one idempotent Refresh at
  30 seconds without a complete row and changes to **CM0 Data Stalled** at 60
  seconds, so a responsive-but-stale mailbox cannot masquerade as endless
  boot progress. Connected clean-power-cycle validation then reached live mode
  at approximately 37 seconds: the display reported **CM0 LINK**, successive
  captures changed from -23.2 to -64.7 dBFS, and new waterfall history was
  visible. This confirms clean startup recovery; the vendor-bound out-of-band
  reset limitation for an already deeply wedged Main route remains documented.
  Physical Pocket Alert testing then exposed two unrelated operations that
  could make the recovered system look dead: entering the page reconstructed
  and resent Main's complete awake mask merely to suppress the front LED, and
  saving one alert setting republished the entire 16-frequency mailbox. A live
  power snapshot can omit device-managed USB-hub/CM0 bits, so the former could
  interrupt the receiver route; the latter blocked command acknowledgements
  behind unnecessary traffic. Both operations are removed. Pocket Alert now
  changes no power rails and persists its setting without a full-list rebuild.
  The user clarified that the visible failure began specifically on **Test**:
  its blocking three-pulse loop stopped servicing OneWili for roughly 690 ms,
  enough to discard live traffic on the narrow v07 route. Manual Test now uses
  the existing nonblocking sequencer, preserving three 150 ms pulses and 80 ms
  gaps while buttons, app signals, and SDR rows continue to be serviced.
  Repeat Page, Enable/threshold, Test, Back, and Refresh on the fixed build.
- [x] Install the native app at `/apps/waverider/waverider_display.uf2` and
  expose it in the stock Apps menu. Host USB SD enumeration is unreliable on
  the test Mac, so a verified SRAM-only self-installer now writes the embedded
  app through Main's supported SDFS service and checks the final byte count.
  Both freshly rebuilt UF2 artifacts pass the BSP's SRAM-only safety gate. The
  connected self-installer wrote and byte-count-verified the file, and Main
  launched that exact stored copy from the Apps menu. The installer now halts
  both display cores and quiesces peripheral DMA before `load_image` plus
  `verify_image`, preventing an old keyboard DMA ring from mutating the loaded
  installer during its fail-closed comparison.
- [x] Produce and audit a GitHub-ready release archive. The rebuilt
  `dist/freewili-foxhunt-0.1.0.tar.gz` includes the final CM0 cadence code,
  native Display UF2, volatile self-installer, offline RTL-SDR packages,
  deployment helpers, and public documentation. The archived `display.py` and
  `waverider_display.uf2` hashes match the working tree, the archive checksum
  file verifies, and a clean extraction passes the native installer's SRAM-only
  dry-run gate. Public prerelease
  [`v0.1.0-beta.1`](https://github.com/3DDEio/freewili-waverider/releases/tag/v0.1.0-beta.1)
  was downloaded again from GitHub and its published checksum verified. The
  protected `main` branch requires both Python 3.11 and 3.13 CI checks,
  CODEOWNER review, linear history, and resolved review conversations; force
  pushes and branch deletion are blocked. Secret scanning, push protection,
  private vulnerability reporting, and web commit signoff are enabled.
- [x] Constrain waterfall plot values to FW2's documented 0..100 plot scale.
  The previous 0..255 encoder caused v07 to reject `g\\e\\f` values above 100 as
  `Invalid`, leaving a partially staged hot/yellow row and a static panel. The
  corrected noise-anchored hardware snapshot reported values 4..62, ten
  distinct colors, 2.42 committed rows/second, and `display_connected=true`.
- [x] Remove the RTL2832 tuner-center DC artifact from peak/RSSI/waterfall data.
  The native receiver intentionally tunes 25 kHz above the selected frequency;
  connected-hardware imagery exposed the dongle's stationary DC ridge at
  exactly `PK +25.0 kHz`. A seven-bin local-noise notch now removes that false
  signal before reduction and peak detection. The post-deploy snapshot no
  longer reported +25 kHz and showed an ordinary -65 dBFS noise floor.
- [x] Add and validate a thin waterfall centerline at the exact selected
  frequency. The implementation uses a two-pixel native overlay because the
  v07 dynamic-control API has no line primitive. Connected framebuffer and
  device-photo checks show live row repaints preserve the centered marker.
- Preserve the existing native-IQ cadence and frozen waterfall scaling while
  changing the UI.
- [x] Select and validate a bounded microbatch size for the 12-bin field
  profile. The previous 32-command single-window build overloaded the stock
  bridge, timed out on `g\\e\\f`, and eventually left `fwcm0-bridge.service`
  restart-looping with `router timeout`. Benchmark windows 1, 2, and 4 after a
  full cold power cycle; deploy only the smallest window that sustains at least
  3 committed rows/second without bridge errors or a growing SDR queue. A
  detached-shell batch-1 benchmark initially passed panel creation and a
  12-bin row at 1.97 rows/second. The final implementation keeps that bounded
  transaction behavior but removes steady-state `wr_freq`, `wr_span`, and
  `wr_sel` writes from each row, publishing tuning state only when it changes.
  Connected CM0 status now reports 3.6 rows/second, zero queued SDR rows, and
  six distinct encoded waterfall levels; the prior build measured 2.6 rows/s.
- [x] Clear the FX0177 bridge-router recovery gate. After Main-only recovery,
  the current bridge instance stayed active. The remaining Display timeout was
  isolated to an attached Main `TYPE_SHELL` session: `g\\c\\a` and `g\\e\\a`
  timed out while attached, then the identical clean-panel benchmark passed as
  soon as the login shell exited. WaveRider is now enabled and launched only
  after shell detach.
- Complete the final physical design-QA comparison against the original mockup
  after a fresh device photo; the 480 x 320 connected framebuffer comparison
  now passes palette and splash review.

## Separate device-maintenance record — not WaveRider

- [x] The independent, opt-in FW2 v07 quiet/dark startup modification is
  physically proven after a complete power cycle: no stock LED animation, no
  spoken **Free Wili** clip, and normal application operation. It is never
  bundled with or invoked by WaveRider installation or launch. The hash-locked
  V3 procedure and complete rollback boundary are maintained separately in
  `docs/FW2_V07_STARTUP_PATCH.md`.

## Subsequent WaveRider features

- [ ] Add opt-in Pocket Alert vibration for eyes-free hunting. The design uses
  three nonblocking 150 ms pulses separated by 80 ms gaps, a fixed 30-second
  cooldown, and a 3 dB fall-and-rise re-arm
  requirement. Page or the RSSI scale opens a dedicated screen with persistent
  enable/disable, -70..-10 dBFS threshold adjustment, live RSSI/state, and a
  manual Test action. CM0 stores settings atomically and packs them into the
  existing `wr_count` commit so Main's 32-signal mailbox limit is preserved.
  All 143 host tests and the native build pass. Connected validation opened the
  screen, retained live RSSI updates, invoked Test, round-tripped +1/-1 dB and
  enable/disable through Main and CM0, and confirmed root-owned JSON returned
  to disabled/-50 dBFS/30 seconds. The first physical Test produced no felt
  vibration and exposed a separate full-screen repaint flash. The deployed
  diagnostic build stopped full-page redraws during SDR samples and verified
  that GPIO46's output latch and settled pad followed all six transitions, but
  no vibration was felt. A user-approved input-only diagnostic also found no
  response on GPIO31/36/44/46. Current logic-analyzer material assigns Main
  GPIO46 as an analog input, contradicting the older haptic claim. The installed
  Doom and Meshtastic apps were copied read-only and inventoried; their evidence
  and checksums remain in `docs/HAPTIC_EVIDENCE.md`.

  On 2026-08-11 an independent production FW2 v07 bench trace identified the
  vibration motor on **Display GPIO35**. A bounded WaveRider field build changed
  only the motor pin, retained the 12 mA drive and three 150 ms / 80 ms pulse
  envelope, and was installed on FX0177. The user physically confirmed all
  three manual-Test pulses. WaveRider now uses the verified GPIO35 route.
  **Remaining validation:** confirm an RF threshold crossing, 30-second
  cooldown, 3 dB re-arm, persistence, and any additional board revisions.

- [ ] Complete the seven-visible-LED field feedback pass. The native Display
  app now drives only indices 0..6: all red at launch, all yellow while Linux or
  SDR data is pending, all green for the ready transition, then a left-to-right
  RSSI ladder using the same blue-to-yellow scale as the screen. Missing/stale
  rows flash all seven yellow and Refresh uses a yellow chase. Updates are
  coalesced to 4 Hz and never consume the CM0 waterfall mailbox. Physically
  confirm LED index order, colors, thresholds, and the deliberate fault state.
  Pocket Alert deliberately lowers the strip from 48/255 to 6/255 brightness
  while preserving those colors and status patterns. It also clears the safe
  zone-9 status-LED flag while active, turning off the separate front indicator
  above Home, and restores that indicator's prior state on exit.
- [ ] Add real narrow-FM beacon audio with mute, volume, squelch, and output
  routing for onboard speaker, headphone jack, or both. Hardware playback is
  proven in WiliBSP through the NAU88C10 codec at approximately 16 kHz, but the
  demodulator runs on CM0 Linux while the codec/DMA lives on the Display CPU.
  The current low-rate app-signal mailbox cannot carry PCM. Implement and prove
  a dedicated bounded CM0-to-Display audio transport before exposing an Audio
  menu. Audio must default muted, respect the 0.5 W speaker limit, use the BSP
  speaker safety cap and low-power mute state, and shed audio frames instead of
  slowing RSSI, waterfall, controls, or recovery.
- [ ] Field-validate live Morse message detection. CM0 now removes the known
  tuner offset, searches a bounded NFM CW audio range in 20 ms Goertzel
  windows, adapts
  dot/dash timing by fitting the complete message, confidence-gates timing,
  pattern, and tone evidence, and suppresses only duplicate verified popups for
  30 seconds. At least three recent agreeing receptions are required before a
  callsign/message becomes user-visible; actual variant occurrence counts now
  weight consensus, inconsistent bookend callsigns are rejected, and tone
  acquisition/release hysteresis plus bounded speed adaptation prevent noise
  from becoming a confident timing model.
  Native transport uses bounded sequenced six-byte frames; the Display shows
  an eight-second popup while the waterfall remains live. The CM0 now keeps
  100 atomic history records, coalesces similar repeats, and restores the
  newest 16 to a local MSGS viewer with frequency, time, repeats, and quality.
  The viewer now groups observations by frequency and has a confirmation-gated
  Clear action that atomically deletes both verified and candidate history.
  Synthetic 13 and 20 WPM `KO6FQY` decoding passes, timing jitter/outliers are
  tolerated, inconsistent callsigns and unmodulated carriers are rejected, and
  non-800 Hz tone acquisition and sub-dot dropout repair pass, and the full
  host suite covers grouped navigation plus cache/persistence clearing.
  Partial KO6FQY/domain text has now been observed over air; confirm repeatable
  recovery of `KO6FQY JOIN NORCALCYBER.IO! KO6FQY` at 147.500 MHz before
  calling this field-proven.
- Close-in attenuation/gain workflow for near-field hunting.
- Calibrated color legend tied to the frozen relative dBFS waterfall scale.
- Compass-assisted heading sweep and saved hunt observations.
