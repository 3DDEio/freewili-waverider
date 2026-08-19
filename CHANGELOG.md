# Changelog

All notable public changes to WaveRider are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A cross-platform WaveRider installer with one Install action, automatic
  FreeWili discovery, release checksum validation, direct Apps-SD installation,
  safe volatile debug-probe fallback, CM0 Linux preparation, receiver-service
  rollback, and live progress/error feedback.
- Persistent rotating installer logs plus a privacy-safe **Save Diagnostics**
  bundle for remote CM0 startup support. It records bounded startup/service,
  USB, and sanitized runtime evidence without exporting decoded messages or
  saved frequency lists, and always attempts to release an opened support
  route while recording any detach failure.
- Hardened real-world support capture now creates a fresh CLI timeline, copies
  it after collection, records host serial/FreeWili Main classification, and
  preserves a read-only Main parser preflight even when the CM0 shell cannot
  open.
- Frequency-grouped, persistent CW message history with confirmation-gated
  Clear and larger word-wrapped decoded text.
- Git-clone installation quick start, repository map, and browsable
  documentation index.
- A six-position Waterfall Span slider in Settings covering the documented
  25 kHz through 2 MHz profiles with per-frequency persistence.
- A hidden, animated cyber-RF creator-credits screen for KO6FQY and KO6FQJ,
  with bounded display time and immediate key/touch dismissal.
- Pinned WiliBSP/OneWili external-app source with reviewed WaveRider patches,
  exact Debian rtl-sdr corresponding source, and local third-party notices.

### Changed

- The Apps-menu file is now `/apps/Radio/WaveRider.uf2`, matching the filename
  stem shown by current v07 menus. A verified upgrade removes the obsolete
  Radio filename and removes `/apps/waverider` only after proving it is empty.
- Continuous IQ collection now runs independently of FFT/Morse processing with
  a bounded queue and visible overrun failure instead of dropped CW timing.
- Morse carrier hysteresis, separator preservation, whole-message timing fit,
  and three-reception consensus now support exact known-payload field decodes.
- The native application now identifies itself as **WaveRider** and installs at
  **Apps → Radio → WaveRider**. Upgrades verify the new copy before removing the
  former `/apps/waverider` entry.
- Pytest collection is explicitly confined to WaveRider's tests instead of
  vendor SDK trees.
- Boot-recovery verification now always detaches its routed shell, including
  when the initial terminal command fails, and compares installed hashes
  exactly rather than by substring.
- Native app upgrades now use a byte-verified staging file, retain the previous
  UF2, restore it on failure, and recover safely after interruption between
  rename operations.
- Public and CM0 install packages use explicit application-only contents.
- Release automation pins Actions, accepts only version-matching tags already
  contained in protected `main`, validates SRAM-only UF2 files, and attaches
  both installable UF2 artifacts directly.
- CI and tag publication now provision checksum-pinned native build tools and
  require two clean native builds to produce byte-for-byte identical results.
- Public archives, UF2 files, and checksums receive GitHub/Sigstore build-
  provenance attestations tied to the protected tagged commit.
- Device-install archives now use normalized timestamps and ownership, omit
  locally generated Python metadata, and reproduce byte-for-byte from the same
  release inputs.
- The deterministic project-source archive no longer copies WiliBSP or
  OneWili. It records the reviewed dependency commits and includes a helper
  that fetches those exact trees directly from FreeWili for local builds.
- CM0 upgrades now verify the exact bundled RTL-SDR packages, compile a staged
  runtime, promote the complete tree atomically, and retain one predecessor.
- CM0 integration upgrades now restore the preceding runtime, command wrappers,
  and systemd units after either an install failure or an interrupted upgrade,
  preventing mixed-version recovery states.

### Release blockers

- The pinned public OneWili checkout has no explicit license. A supported
  binary release remains blocked until FreeWili provides redistribution terms
  for the linked library and WaveRider's corresponding patch.

### Field validation

- Exact 100 percent displayed character accuracy at 147.500 MHz for
  `KO6FQY JOIN NORCALCYBER.IO! KO6FQY`.
- Exact 100 percent displayed character accuracy at 144.300 MHz for
  `KO6FQY -- DECOY DECOY -- KO6FQY`.

### Planned

- Larger CW efficacy sample and beacon-off false-positive control.
- Optional narrow-FM speaker/headphone audio bridge.

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
