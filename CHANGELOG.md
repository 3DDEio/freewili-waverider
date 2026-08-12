# Changelog

All notable public changes to WaveRider are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Frequency-grouped, persistent CW message history with confirmation-gated
  Clear and larger word-wrapped decoded text.
- Optional, separate CircuitPython SA868 development beacon fixture with a
  byte-for-byte verified deployment path.
- Git-clone installation quick start, repository map, and browsable
  documentation index.

### Changed

- Continuous IQ collection now runs independently of FFT/Morse processing with
  a bounded queue and visible overrun failure instead of dropped CW timing.
- Morse carrier hysteresis, separator preservation, whole-message timing fit,
  and three-reception consensus now support exact known-payload field decodes.
- The native application now identifies itself as **WaveRider** and installs at
  **Apps → Radio → WaveRider**. Upgrades verify the new copy before removing the
  former `/apps/waverider` entry.
- Pytest collection is explicitly confined to WaveRider's tests instead of the
  pinned vendor SDK research trees.
- Boot-recovery verification now always detaches its routed shell, including
  when the initial terminal command fails, and compares installed hashes
  exactly rather than by substring.
- Pocket Alert and the opt-in FX0177 v07 quiet/dark startup documentation now
  match the physically verified hardware behavior.

### Field validation

- Exact 100 percent displayed character accuracy at 147.500 MHz for
  `KO6FQY JOIN NORCALCYBER.IO! KO6FQY`.
- Exact 100 percent displayed character accuracy at 144.300 MHz for
  `KO6FQY -- DECOY DECOY -- KO6FQY`.

### Planned

- Larger CW efficacy sample and beacon-off false-positive control.
- Optional narrow-FM speaker/headphone audio bridge.
- Authoritative haptic-driver integration if FreeWili publishes the hardware
  interface and the connected board is confirmed to contain a motor.

## [0.1.0-beta.1] - 2026-08-09

### Added

- Native FreeWili 2 Apps-menu display application.
- CM0 RTL-SDR IQ capture, centered waterfall, and relative dBFS RSSI.
- Persistent 100-frequency library and 16-frequency Live hunt list.
- Exact on-device frequency editor and physically validated controls.
- Startup, receiver-health, refresh, fault, and seven-LED feedback.
- Guarded receiver/maintenance profiles and offline-capable installation.
- Public documentation, connected-device completion audit, CI, and release
  packaging.

### Known limitations

- Received audio is not implemented.
- This original beta disabled haptic output because the public pin assignment
  was incorrect. Unreleased WaveRider builds now use physically verified
  Display GPIO35 on FX0177 v07; other board revisions still require manual
  Test validation.
- The waterfall is optimized for field direction finding, not laboratory
  measurement.
- RSSI is relative dBFS, not calibrated dBm.

[Unreleased]: https://github.com/3DDEio/freewili-waverider/compare/v0.1.0-beta.1...HEAD
[0.1.0-beta.1]: https://github.com/3DDEio/freewili-waverider/releases/tag/v0.1.0-beta.1
