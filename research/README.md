# Local build dependencies

This directory is intentionally empty in Git except for this file. Local Pico
SDK, OpenOCD, CMake, and ARM toolchain installs can exceed a gigabyte and may
contain nested repositories or generated files. WiliBSP and nested OneWili are
now pinned by the repository's `wilibsp/` submodule instead of a sibling copy.

WaveRider's source of truth remains under `native/`. The build helper verifies
the vendor commits, Pico SDK commit/tag, and compiler version, then applies the
reviewed `native/patches/` compatibility delta before compiling from the
repository root. A locally prebuilt Picotool can be supplied through
`PICOTOOL_DIR`; otherwise the Pico SDK build may fetch/build it.

Expected local layout:

```text
research/
  pico-sdk/      # Raspberry Pi Pico SDK required by WiliBSP
  openocd-mac/   # optional maintainer OpenOCD bundle
```

The initial supported release is built against WiliBSP commit
`5fa1e56cea29254badb9c8f71acd027cda0ea45a`, nested OneWili commit
`e9ff9d946ce009f7515e8506cc91df44a299cb34`, Pico SDK 2.3.0 commit
`98a542c1a62fb549ffb5d66a3e5892b06276b670`, and Arm GNU Toolchain
14.2.Rel1. Initialize the submodules and run:

```text
git submodule update --init --recursive
export PICO_SDK_PATH=/path/to/pico-sdk-2.3.0
export PICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-14.2.Rel1
export PICOTOOL_DIR=/optional/path/to/picotool/cmake/package
sh deploy/build-native-apps.sh
```

Do not commit local toolchains, nested dependency repositories, device dumps,
or generated build trees.
