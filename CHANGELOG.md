# Changelog

All notable public changes to WaveRider are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned

- Controlled known-beacon field acceptance.
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
- Haptic output is disabled because the public hardware control path is not
  authoritative and the connected device did not respond.
- The waterfall is optimized for field direction finding, not laboratory
  measurement.
- RSSI is relative dBFS, not calibrated dBm.

[Unreleased]: https://github.com/3DDEio/freewili-waverider/compare/v0.1.0-beta.1...HEAD
[0.1.0-beta.1]: https://github.com/3DDEio/freewili-waverider/releases/tag/v0.1.0-beta.1
