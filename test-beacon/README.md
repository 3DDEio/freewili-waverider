# Optional KO6FQY field-test beacon

This directory is intentionally separate from WaveRider's receiver runtime.
It is an optional development fixture for a Seeed Studio XIAO ESP32-C3 wired
to a NiceRF SA868. WaveRider never installs, starts, or controls this beacon.

## Current controlled-test configuration

- Station ID: `KO6FQY`
- Frequency: `144.3000 MHz`
- Power: low (`HL` held low)
- Morse payload: `KO6FQY -- decoy decoy -- KO6FQY`
- Morse speed: 13 WPM
- Audio tone: 800 Hz
- Delay after each completed message: 30 seconds
- Bandwidth: 25 kHz

Edit only the configuration constants near the top of `code.py`. Confirm the
frequency is authorized for the operator, location, and test conditions before
transmitting. Use a dummy load or suitable antenna and maintain appropriate
station identification. WaveRider itself remains receive-only.

## Fail-safe deployment

Install `pyserial`, connect only the test beacon, and run:

```text
python3 test-beacon/deploy.py --port /dev/cu.usbmodemNNNN
```

The updater stages `/code.py.new`, reads it back byte-for-byte, and only then
rotates the active file to `/code.py.last`. A failed or interrupted transfer
does not replace the active beacon program. On 2026-08-12 this process installed
the 144.300 MHz configuration, and the SA868 returned `+DMOSETGROUP:0` before
WaveRider displayed the entire decoy payload exactly after consensus.

## Timing requirement

The microphone PWM is allocated once and keyed by changing its duty cycle.
Do not recreate or deinitialize `PWMOut` for every Morse element: on this
ESP32-C3, that lifecycle delay is a significant fraction of a 13 WPM dot and
corrupts the transmitted 1:3:7 timing ratios.

## Provenance and license

The hardware mapping and SA868 control flow are adapted from Bradán Lane's
CircuitPython port of the rot13labs Fox Hunt Badge firmware:

<https://gitlab.com/bradanlane_cp/foxhunt>

This optional fixture is GPL-3.0-or-later and retains its SPDX headers and
attribution. It is not included in WaveRider's end-user installation bundle.
