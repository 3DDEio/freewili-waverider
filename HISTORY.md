# WaveRider project history

This is a reconstructed development record, not fabricated Git commit history
and not a substitute for the missing early commits. WaveRider was developed
interactively on connected FreeWili 2 hardware
before the repository's initial public import. The original intermediate file
states were not committed, so manufacturing backdated commits would give a
false impression of provenance.

The public Git history therefore starts with one honest initial-import commit.
All subsequent work uses normal commits, pull requests, protected-branch
checks, and release tags.

## Reconstructed milestones

### Hardware recovery and inventory

- Identified the FreeWili 2 Display, Main, and CM0/Linux surfaces.
- Recovered and inspected the CM0 ext4 filesystem without modifying it.
- Validated the current CM0 Linux image and the RTL2838/R820T USB receiver.
- Preserved a maintenance-console recovery path while enabling Linux USB Host
  operation for the SDR.

### Receiver proof of concept

- Established continuous RTL-SDR IQ capture on the CM0.
- Implemented relative dBFS RSSI and a centered waterfall for foxhunting.
- Replaced accumulated sample queues with latest-only buffering so movement
  remains visible instead of lagging behind the operator.
- Confirmed a stable connected pipeline above the 3 rows/second acceptance
  threshold.

### Native WaveRider interface

- Built a volatile SRAM FreeWili Display application; stock Main and Display
  firmware are not replaced.
- Added the WaveRider splash, live waterfall, moving RSSI marker, frequency
  list, startup/receiver status, and seven-LED signal meter.
- Moved physical controls to the Display-side UART keyboard path after the
  tested v07 CM0 button relay proved unreliable.
- Physically validated D-pad/Check tuning and all five context actions.

### Frequency management

- Added an exact digit-position frequency editor.
- Added a persistent saved library of 100 unique frequencies and a 16-entry
  Live hunt list.
- Added page navigation, Live membership, tune, add, and confirmed delete.
- Added the Ham Radio Village contest frequencies used during field testing.

### Deployment and recovery

- Added guarded maintenance/receiver profiles for the CM0's single USB
  controller.
- Added an offline-capable serial installer and a volatile native Apps-menu
  self-installer.
- Added fail-closed checks that reject native images targeting persistent
  Display QSPI flash.
- Confirmed the Apps entry, configuration, and CM0 service survive complete
  power removal.

### Haptic investigation

- Implemented a threshold/cooldown/re-arm design. The initial public GPIO46
  assignment produced no physical vibration.
- Verified every requested GPIO46 transition at the RP2350 pad.
- Ran a user-observed input-only weak-pull scan of GPIO31, GPIO36, GPIO44, and
  GPIO46; every candidate produced no response and was immediately restored.
- An independent production FW2 v07 bench trace later identified Display
  GPIO35. WaveRider changed only the motor pin and physically produced all three
  manual-Test pulses on FX0177 on 2026-08-11. GPIO35 is now the verified route;
  RF threshold/cooldown/re-arm validation remains open.

### Initial public import

- Added public documentation, CI, release automation, contribution/security
  policy, checksummed native artifacts, and copyleft/share-alike licensing.
- Recorded remaining beta boundaries rather than presenting unverified
  features as complete.

## Evidence boundaries

Connected validation currently covers one FreeWili 2 running Main v07 with an
onboard CM0 and an RTL2838/R820T receiver. Relative RSSI is useful for direction
finding but is not calibrated dBm. See
[`docs/COMPLETION_AUDIT.md`](docs/COMPLETION_AUDIT.md) and
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for the exact evidence and open
work.
