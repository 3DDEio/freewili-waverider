# Local build dependencies

This directory is intentionally empty in Git except for this file. Local Pico
SDK, WiliBSP, OneWili, OpenOCD, CMake, and ARM toolchain checkouts can exceed a
gigabyte and may contain nested repositories or generated files.

WaveRider's source of truth remains under `native/`. The native build helper
copies that source into a local WiliBSP checkout before compiling.

Expected local layout:

```text
research/
  wilibsp/       # https://github.com/freewili/wilibsp
  pico-sdk/      # Raspberry Pi Pico SDK required by WiliBSP
  openocd-mac/   # optional maintainer OpenOCD bundle
```

The initial public release was built against WiliBSP commit
`5fa1e56cea29254badb9c8f71acd027cda0ea45a`. Follow WiliBSP's own setup
instructions, configure its `build/` directory, then run:

```text
CMAKE_BIN=/path/to/cmake sh deploy/build-native-apps.sh
```

Do not commit local toolchains, nested dependency repositories, device dumps,
or generated build trees.
