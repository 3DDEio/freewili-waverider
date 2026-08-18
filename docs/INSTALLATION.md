# Installing WaveRider

WaveRider's release bundle includes one installer for both parts of the app:

- the FreeWili screen application at **Apps → Radio → WaveRider**; and
- the CM0 Linux receiver service that talks to the RTL-SDR.

The installer does not replace the stock Main or Display firmware.

## Before you begin

1. Use a FreeWili 2 with its CM0 Linux SD and Main Apps SD installed.
2. Connect the FreeWili USB cable to the computer.
3. Leave the FreeWili at its home screen.
4. Install Python 3.11 or newer on the computer.
5. Download and extract the complete WaveRider device-install archive. Do not
   run the installer from inside a compressed-file preview.

## Run the installer

- **macOS:** double-click `installer/Run WaveRider Installer.command`.
- **Windows:** double-click `installer/Run WaveRider Installer.cmd`.
- **Linux:** run `installer/run-waverider-installer.sh`.

The launcher creates `installer/.installer-venv` inside the extracted release
folder and installs the pinned host USB dependencies there. It does not alter
the computer's global Python installation. The first launch needs Internet
access for those small dependencies; installation onto the FreeWili is
otherwise offline.

Select the detected FreeWili and click **Install WaveRider**. Keep the cable
connected until the progress bar reaches 100 percent. The final serial
disconnect is expected when the installer switches CM0 into guarded SDR host
mode.

Return to the FreeWili home screen and open
**Apps → Radio → WaveRider**. A healthy first launch shows startup progress and
then `SDR LIVE` with a scrolling waterfall.

## Save diagnostics for remote support

If WaveRider remains on a CM0 startup or receiver-waiting screen, leave that
screen visible and reconnect the FreeWili USB cable to the computer. Reopen the
same WaveRider installer, select the detected FreeWili if one appears, and
click **Save Diagnostics**. Choose a location for the generated
`WaveRider-Support-*.zip`, then send that ZIP together with a photo of the exact
on-device message.

The bundle records:

- the persistent installer timeline and release-integrity result;
- the last reported WaveRider startup stage and sanitized receiver health;
- bounded status for the CM0 bridge, WaveRider, and guard services;
- bounded current-boot journal excerpts, CM0 boot-role facts, and USB discovery.

It deliberately omits CW text, decoded-message history, saved frequency lists,
and unrelated files from the computer user's home directory. Collection is
read-only: it does not reboot the FreeWili, restart a service, install files,
or change the receiver profile. It temporarily borrows the routed CM0 shell
while the app is already stuck, restores terminal echo, and attempts to detach
before it finishes. Any detach failure is placed in `warnings.txt` rather than
hidden. Do not run it during an active field hunt.

If the FreeWili Main port is not detected, **Save Diagnostics** still produces
a local-only ZIP containing the installer timeline and the discovery failure.
Advanced users can collect the same bundle without the GUI:

```text
python3 installer/collect_diagnostics.py --port /dev/cu.YOUR_MAIN_PORT \
  --output WaveRider-Support.zip
```

## Safety and fallback behavior

The installer verifies the release checksum manifest and rejects a native app
that targets persistent Display flash. It first asks Main to expose the Apps SD
to the computer, writes a staging file, flushes it, and promotes it under the
friendly `WaveRider.uf2` name. Ownership is returned to Main even when the copy
fails.

Some hosts do not mount the FreeWili Apps SD reliably. In that case the same
Install action can use the built-in debug probe to run the existing installer
from volatile SRAM. This fallback needs Raspberry Pi's RP2350-capable OpenOCD
on the computer. It loads and verifies the temporary installer without a flash
program command. If OpenOCD is absent, the GUI stops and explains the missing
prerequisite without changing stock firmware.

CM0 files are uploaded in bounded commands, verified by SHA-256 on the device,
compiled in a staging directory, and promoted with rollback protection. The
previous receiver runtime is retained for recovery.

## Current release boundary

The combined installer has host regression coverage, but its clean-device
macOS and Windows/Linux physical acceptance runs remain open. It must not be
described as a supported public release until those observations and the
OneWili redistribution-permission gate in
[Deployment and releases](DEPLOYMENT.md) pass.
