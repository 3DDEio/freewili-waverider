# WaveRider native Display app

This directory contains WaveRider's FreeWili 2 Display-side application and
its self-installer. The Display app owns the physical button loop and exchanges
frequency commands plus live SDR rows with the CM0 service through Main's app
signal mailbox.

`dist/` contains the release artifacts:

- `WaveRider.uf2` — the SRAM-only Apps-menu application. The friendly filename
  is intentional because current v07 menus display the UF2 stem.
- `waverider_display.elf` — the same volatile app for probe-assisted testing.
- `waverider_installer.elf` — the volatile maintainer self-installer image.
- `waverider_installer.uf2` — the self-installer UF2 for safety inspection.

The stock Display firmware is never replaced. Both UF2 files must pass
WiliBSP's `check_app_uf2.py` before packaging. The host installer additionally
rejects ELF segments outside FreeWili's volatile SRAM and PSRAM windows and
uses OpenOCD `load_image`/`verify_image`, not `program`.

Build from the pinned WiliBSP submodule with Pico SDK 2.3.0 and Arm GNU
Toolchain 14.2.Rel1:

```text
git submodule update --init --recursive
export PICO_SDK_PATH=/path/to/pico-sdk-2.3.0
export PICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-14.2.Rel1
sh deploy/build-native-apps.sh
```

`tools/prepare_wilibsp.py` verifies the exact WiliBSP and nested OneWili
commits before applying the reviewed patches in `native/patches/`. It refuses
unreviewed dependency drift. The build deliberately omits the optional SDK
compile date so identical pinned sources produce comparable release UF2 files.

Install on hardware with the built-in CMSIS-DAP probe connected:

```text
python3 tools/fw2_install_native_app.py --dry-run
python3 tools/fw2_install_native_app.py
```

Wait for **INSTALL COMPLETE**, then hold Home for five seconds. WaveRider will
be available under `/apps/Radio/WaveRider.uf2` as
**Apps → Radio → WaveRider**. A verified upgrade removes both the former
`/apps/Radio/waverider_display.uf2` and
`/apps/waverider/waverider_display.uf2` copies, then removes the old
`/apps/waverider` category only after enumerating it and proving it is empty.
Upgrade writes a separate candidate, reads every byte back, retains the prior
app under `/appdata/waverider/`, and restores it if promotion or final
verification fails.
