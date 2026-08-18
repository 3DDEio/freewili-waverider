# Troubleshooting

## SDR missing

Run `sudo foxhuntctl doctor`.

- The SDR belongs in the rightmost bottom USB-A socket, immediately left of the
  Main SD card.
- Receiver mode must show `dtoverlay=dwc2,dr_mode=host`.
- `lsusb` should include `0bda:2838 Realtek RTL2838 DVB-T` or another supported
  RTL2832U identifier.
- If the serial console is still present, the CM0 is probably in maintenance
  mode rather than receiver mode.

If `foxhuntctl host` reports success but the next boot still uses peripheral
mode, inspect every active `dtoverlay=dwc2,dr_mode=` line. Some CM0 images carry
an additional board-filtered host-mode example later in `config.txt`.
`foxhuntctl` must replace the active peripheral line even when that unrelated
example already contains the requested host value. Current releases handle
this ordering correctly.

## Stuck on `Waiting for SDR Data` with flashing yellow LEDs

For a remote-support case, first use the release installer's **Save
Diagnostics** action while this screen is still visible. Send the generated ZIP
and a photo of the exact message to the maintainer. The bundle distinguishes
configuration loading, receiver start, Display connection, and first-SDR-row
waits; it also captures bounded CM0 bridge/service state without copying saved
frequencies or decoded messages. A missing Main port still yields a useful
local installer/discovery timeline. See
[Save diagnostics for remote support](INSTALLATION.md#save-diagnostics-for-remote-support).

First allow the normal CM0/tuner startup window. WaveRider now waits 20 seconds
before attempting any recovery. On FW2 v07, Main can occasionally retain its
routed Linux `TYPE_SHELL` session during a fresh launch. In that state the SDR
may already be sampling while Main blocks the app-signal updates needed by the
Display, so the waiting screen alone does not prove that the dongle is missing.

Current builds self-heal this specific boot race during a bounded 90-second
window. They hang up only the `login -f pi` process directly owned by
`fwcm0 bridge`; the bridge then sends its normal `SHELL_EXIT` notice to Main.
Linux, the bridge, the SDR capture, saved lists, and tuning state are not
restarted. The recovery is disabled after WaveRider has connected once and is
inhibited during an explicit maintenance deployment, so a terminal opened
later for diagnosis is not forcibly closed.

If the screen is still waiting after 90 seconds, exit any Linux Terminal that
is visibly open, return Home, and relaunch WaveRider. Do not restart
`fwcm0-bridge.service` from a shell that is itself routed through that bridge.
Use `sudo foxhuntctl doctor` only after the terminal route has been cleanly
closed.

Do not run host-side `wr_*` app-signal polling loops while WaveRider is live.
On the tested FX0177 v07 unit, Main USB mailbox reads competed with the CM0
service's own response stream and were followed by repeated native Display
publication timeouts. The SDR process can remain healthy while the visible row
sequence stalls. Leave Main USB idle during an RF/CW field test; pause
WaveRider before attaching maintenance diagnostics. The installer's bounded
**Save Diagnostics** action is the exception intended for an already-stuck
startup screen; it explicitly releases its temporary route when done.

## Stale or duplicated foxhunt panels

The FreeWili display retains dynamic panels until explicitly reset. Current
releases reset only the live scripting panels before building Foxhunt and retry
the display bridge every five seconds if it is temporarily busy. They do not
reset firmware, settings, SD-card contents, or saved frequency lists.

If an older panel remains visible after an update, restart
`freewili-foxhunt.service`. If the SDR remains live but the panel does not
return, inspect `sudo foxhuntctl logs`; display failures are nonfatal and the app
continues sampling while it reconnects.

## Waterfall is solid yellow or fills slowly

The waterfall grows one committed FFT row at a time from the top. A previously
solid-yellow display was caused by applying a fixed -90 to -30 dBFS palette to
an RTL-SDR whose uncalibrated `rtl_power` bins sat much closer to full scale.
Current releases calibrate a bounded 30 dB display window from the RF noise
median for the first 12 rows, then freeze it until retune or gain change. A
strong −25 dBFS row and weak −55 dBFS row should therefore never both be
normalized to yellow. RSSI remains relative dBFS; stable colors do not turn it
into calibrated dBm.

Current releases also use native IQ capture and a 12-bin responsive field
waterfall. The capture worker targets ten FFT analyses per second, while each
visible row pipelines its plot values, live text, pointer, and row commit in a
single correlated Display batch. Twelve bins preserve materially more useful
narrowband shape than the rejected eight-bin profile. If RSSI is live
but rows still arrive slowly, the display bridge—not the RTL-SDR sample
stream—is the limiter. Check `sudo foxhuntctl logs` for display timeouts before
changing sample rates or span.

If the numeric RSSI drifts steadily while the radio, antenna, and transmitter
are stationary, allow a short tuner warm-up and compare again. Current native
capture consumes a full 100 ms of IQ on every read; older fast builds used a
fixed shorter read followed by a sleep, which could leave progressively older
samples queued behind the live RF state.

## Colored buttons do not retune

FW2 v07's stock CM0 bridge does not expose Display button events. Current
WaveRider releases therefore require the native Apps-menu app, which reads the
Display processor's supported `uartkbd` queue directly. Confirm the title is
**WaveRider** and the lower footer says `DPAD SELECT CHECK APPLY`; an older stock
dynamic panel cannot retune from physical buttons on v07.

Green sends Next immediately. D-pad changes the local cursor; Check or the
D-pad center sends the explicit selected index to CM0. If the cursor moves but
the large center frequency does not, the hardware input is healthy and the
`wr_cmd` mailbox/CM0 service is not. Check `sudo foxhuntctl logs` and
`/run/freewili-foxhunt/status.json` before restarting.

## `router timeout`

This means the CM0 cannot complete the FPGA mailbox handshake used for the
stock display bridge. It is separate from RTL-SDR USB detection.

1. Confirm the FPGA power zone is on from the FreeWili Power Management panel.
2. Open Wi-Li-nux → Linux Terminal and press Yellow **Enable**. Once Linux has
   had its boot window, return Home without pressing Disable. The on-device
   terminal owns Main's routed shell while open and can leave the host command
   parser silent even after returning Home; use one physical Main-only reset to
   release that route while keeping CM0 powered, then do not reopen the app.
3. Check `systemctl status fwcm0-bridge.service`.
4. Run `fwcm0 status` only after stopping the bridge service, because both
   processes otherwise contend for the software-controlled SPI chip select.
5. If direct status still times out, perform a **Main CPU Software Reset** from
   Hardware → Settings → Software Reset. Do not reset the CM0 and do not reset
   all settings. Wait for Main USB to return, then require a successful RTC
   probe before starting the bridge again. On FX0177 v07, later software-reset
   attempts re-enumerated USB with a silent parser; if that happens, stop
   issuing software resets and perform one physical Main reset on the device.

The application can run headlessly for diagnostics, but the guarded receiver
boot requires the on-device panel. If the bridge does not answer within two
minutes, maintenance mode is restored automatically.

### Direct CM0 console on macOS

Maintenance mode exposes Linux as `Gadget Serial v2.4`. Find the newly created
callout device after enabling Linux:

```text
ls /dev/cu.usbmodem*
```

The supplied probe opens that console at 115200 baud, sends one newline, and
prints the login banner without changing the CM0 configuration:

```text
python3 tools/cm0_serial_probe.py /dev/cu.usbmodemNNNNN
```

Linux is healthy if the result reaches a `pi@raspberrypi:~$` prompt even when
the FreeWili panel remains on `Linux is now booting...`.

### FW2 v07 field diagnosis

The following combination was reproduced on hardware revision 2.0, serial
FX0177, Main firmware v07, bootloader v2.2:

- Debian 13 reaches its automatic `pi` login through `ttyGS0`.
- FPGA zone 6, CM0 zone 17, USB hub zone 8, and the CM0 run line all read back
  enabled from the Main processor.
- The Main processor reports FPGA clock `cpu125`, integer divider `4`,
  fractional divider `0`, and communications mode `SPI`.
- The CM0 exposes `/dev/spidev0.0`, `/dev/ttyAMA0`, and GPIO21 software chip
  select with the expected pin muxes.
- Before recovery, `fwcm0 status` reported `router timeout` even with the bridge
  service stopped. Cycling only FPGA power zone 6 did not restore the link.
- A Main CPU Software Reset immediately restored valid status frames. The
  returned state included `init_done=1` and `boot_ready=1`.
- After the reset, `fwcm0-bridge.service` remained active, its socket appeared,
  the foxhunt panel completed its OneWili build, and the stock Linux shell
  returned `FW2_MAILBOX_OK` from an `echo` command.

The installed vendor bridge writes an `OP_STATUS` request through SPI0 and
waits for a framed response on the 7.8125 Mbaud UART. A system-call trace
confirmed that the failed state completed every SPI transfer but received zero
UART bytes. Safe probes across SPI speeds, UART rates, SPI modes 0–3, and a
temporary no-flow-control build all failed the same way. The successful Main
reset therefore points to stale or incomplete Main/FPGA router initialization,
not a CM0, SD-card, Linux-driver, or foxhunt problem.

## Serial installer returns a blank checksum report

The FW2 v07 Main-routed Linux shell is not a conventional direct serial TTY:

- carriage return submits a Linux command;
- Ctrl-C exits the shell tunnel back to Main firmware;
- sustained unthrottled writes can outrun the Main-to-CM0 mailbox.

Use the included current `deploy/serial_install.py`; do not paste a large base64
blob into the terminal. Before retrying, prove the shell with `printf READY`.
If a legacy installer left an interactive decoder waiting for input, press
Ctrl-C once to cancel that decoder. If the shell does not return, power-cycle,
restore FPGA zone 6 / CM0 zone 17 / the released CM0 run line, and reopen the
shell. The current uploader uses complete, individually acknowledged append
commands, so an interrupted transfer leaves only removable temporary files and
cannot strand the prompt.

Do not reflash firmware for this symptom. Try one Main recovery reset, prove it
with the RTC probe, and use a physical Main reset if USB reappears silent.
Escalate if the condition recurs, reporting both the failed state and the
successful or failed recovery result.

## One-click installer cannot mount the Apps SD

Leave both SD cards installed, return the FreeWili to its home screen, and
click Refresh in the installer. The installer always returns SD ownership to
Main after a failed mount attempt. It then tries the physically established
volatile installer path when Raspberry Pi's RP2350-capable OpenOCD and the
built-in debug probe are available.

If the fallback reports that OpenOCD is missing, install the Raspberry Pi
RP2350-capable OpenOCD bundle and restart the WaveRider installer. Do not put
the Display processor into BOOTSEL and do not flash a stock firmware image.
The installer stops before any stock-firmware write.

The Main SD observed with v07 contained `FW2Main.uf2` and `FW2Display.uf2` in
`/firmware`; its `/fpga` directory was empty. Because the router worked after a
Main reset without adding a file, the empty directory is not evidence of a
missing runtime gateware image.

## List editing

Field edits use the colored buttons shown in the panel footer. Custom list names
and labels are entered in maintenance mode because the current OneWili dynamic
dialog API does not return typed text to the CM0 application:

```text
sudo foxhuntctl lists --help
sudo foxhuntctl lists show
```

## Recover the CM0 console

Run:

```text
sudo foxhuntctl maintenance --reboot
```

If the service cannot run, edit `/boot/firmware/config.txt` on the Linux SD card
and restore these exact lines:

```text
dtoverlay=dwc2,dr_mode=peripheral
gpio=2=op,dl
gpio=3=op,dh
```

Do not use `gpioget` on GPIO2 or GPIO3 while the device is running; requesting
those boot-configured output lines can change their direction and disconnect
the USB mux. `pinctrl get 2,3` is safe for read-only inspection.

## Support bundle

Collect:

```text
sudo foxhuntctl doctor
sudo foxhuntctl status
sudo foxhuntctl logs
```

Remove personal list labels or frequencies before posting the output publicly.

For a stock bridge failure, also include:

```text
systemctl --no-pager --full status fwcm0-bridge.service
journalctl -u fwcm0-bridge.service -n 30 --no-pager
cat /etc/environment
ls -l /dev/spidev0.0 /dev/ttyAMA0
pinctrl get 9,10,11,14,15,16,17,21
```

Do not run `systemctl restart fwcm0-bridge.service` from a Linux shell opened
through that same service. The shell is a child of `fwcm0-bridge`; systemd must
wait for it to exit and the restart deadlocks against its own maintenance
session. Leave the shell before restarting the bridge through an independent
channel. If no independent channel is available and Main no longer opens a
Linux shell, power-cycle the device; do not reflash either SD card.

Before diagnosing a silent Main USB command port, confirm no abandoned host
probe still owns or repeatedly reopens it. On macOS, inspect both the process
list and `lsof` for the exact `/dev/cu.usbmodem...` path. Terminate only the
identified stale probe, never an unknown process. Then use the included helpers:

```text
python3 tools/fw2_main_probe.py --port /dev/cu.usbmodemFX01771
python3 tools/fw2_open_shell.py --port /dev/cu.usbmodemFX01771
```

The probe is read-only. `fw2_main_reset.py` remains available only as a guarded
maintainer diagnostic and now requires `--allow-physical-recovery`; do not use
it unattended. It does not restore defaults or write either SD card, but v07
can re-enumerate with a silent parser. Do not consider recovery complete until
the probe returns a response and the Linux shell produces a round-trip marker.

On FX0177 v07, a successful `l\\a` frame can still report `Linux CPU power:
off`, and even its subsequent `ON` frame did not prove that the on-device Linux
application launched. Treat the visible Yellow Enable action as the boot
authority. Do not open an extra test shell before deployment: opening, closing,
and immediately reopening the Main route reproduced a silent parser. The
current live-fix helper reuses an existing prompt when one is already present
and otherwise opens exactly one routed session.

A completed resolved field report for FW2 v07 hardware is available in
[`SUPPORT_REPORT_FW2_FX0177.md`](SUPPORT_REPORT_FW2_FX0177.md).
