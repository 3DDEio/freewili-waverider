# WaveRider native Display app

This directory contains WaveRider's FreeWili 2 Display-side application and
its self-installer. The Display app owns the physical button loop and exchanges
frequency commands plus live SDR rows with the CM0 service through Main's app
signal mailbox.

`dist/` contains the release artifacts:

- `waverider_display.uf2` — the SRAM-only Apps-menu application.
- `waverider_display.elf` — the same volatile app for probe-assisted testing.
- `waverider_installer.elf` — the volatile maintainer self-installer image.
- `waverider_installer.uf2` — the self-installer UF2 for safety inspection.

The stock Display firmware is never replaced. Both UF2 files must pass
WiliBSP's `check_app_uf2.py` before packaging. The host installer additionally
rejects ELF segments outside FreeWili's volatile SRAM and PSRAM windows and
uses OpenOCD `load_image`/`verify_image`, not `program`.

Build from the pinned WiliBSP checkout:

```text
CMAKE_BIN=/path/to/cmake sh deploy/build-native-apps.sh
```

Install on hardware with the built-in CMSIS-DAP probe connected:

```text
python3 tools/fw2_install_native_app.py --dry-run
python3 tools/fw2_install_native_app.py
```

Wait for **INSTALL COMPLETE**, then hold Home for five seconds. WaveRider will
be available under `/apps/Radio/waverider_display.uf2` as
**Apps → Radio → WaveRider**. A verified upgrade removes the former
`/apps/waverider/waverider_display.uf2` copy so the menu does not retain a
duplicate legacy entry.
