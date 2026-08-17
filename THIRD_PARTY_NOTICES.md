# Third-party notices

WaveRider builds on software and packages maintained by other projects. Their
licenses remain in force independently of WaveRider's GPL/CC licensing.

## FreeWili WiliBSP

- Upstream: <https://github.com/freewili/wilibsp>
- License: MIT, plus component-specific notices recorded by upstream.
- Use: RP2350B board support and native application build/runtime.
- Local license copies: [`WILIBSP-MIT.txt`](LICENSES/WILIBSP-MIT.txt),
  [`PICO-PIO-USB-MIT.txt`](LICENSES/PICO-PIO-USB-MIT.txt),
  [`TUSB-XINPUT-MIT.txt`](LICENSES/TUSB-XINPUT-MIT.txt),
  [`FATFS.txt`](LICENSES/FATFS.txt), and
  [`SEGGER-RTT.txt`](LICENSES/SEGGER-RTT.txt).

## FreeWili OneWili

- Upstream: <https://github.com/freewili/onewili>
- Use: Display-to-Main command, event, and SD transport.
- Notice: the pinned public checkout inspected for the initial import did not
  contain a standalone license file. Confirm redistribution terms with
  FreeWili before treating this notice as a license grant. **Do not publish a
  supported binary release until that permission is explicit.**

## Raspberry Pi Pico SDK and OpenOCD

- Pico SDK: <https://github.com/raspberrypi/pico-sdk>
- OpenOCD tools: <https://github.com/raspberrypi/openocd>
- Use: maintainers build and load volatile RP2350 applications.
- These toolchains are not stored in the WaveRider Git repository.
- Runtime license copies: [`PICO-SDK-BSD-3-CLAUSE.txt`](LICENSES/PICO-SDK-BSD-3-CLAUSE.txt)
  and [`TINYUSB-MIT.txt`](LICENSES/TINYUSB-MIT.txt).

## rtl-sdr Debian packages

- Upstream: <https://osmocom.org/projects/rtl-sdr>
- Debian source package: `rtl-sdr` 2.0.2-2
- Licenses: package contents include GPL-2.0-or-later, GPL-3.0-or-later,
  LGPL-2.1-or-later, and MIT components as identified in the packages'
  `/usr/share/doc/*/copyright` files.
- Use: offline arm64 RTL-SDR runtime installation on the CM0.
- Exact corresponding source and checksums are bundled under
  `vendor/debian-source/rtl-sdr-2.0.2-2/`. Public releases preserve the package
  copyright files and identify the source version.

## Generated and compiled files

WaveRider UF2/ELF products are generated from tagged source by the pinned
release workflow and are not committed to Git. Supported releases attach the
validated UF2 files, checksum manifest, deterministic device bundle, complete
source bundle, and provenance attestations.
