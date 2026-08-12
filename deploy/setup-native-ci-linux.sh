#!/bin/sh

# Provision the exact public native-build inputs used by GitHub Actions.
# Every downloaded binary archive is checked against its publisher's digest;
# build-native-apps.sh performs the second, semantic version/commit check.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TOOL_ROOT=${NATIVE_TOOL_ROOT:-"$ROOT/build/native-toolchain"}
SDK_DIR="$TOOL_ROOT/pico-sdk"
TOOLCHAIN_DIR="$TOOL_ROOT/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi"
PICOTOOL_DIR="$TOOL_ROOT/picotool"

SDK_COMMIT=98a542c1a62fb549ffb5d66a3e5892b06276b670
TOOLCHAIN_ARCHIVE=arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi.tar.xz
TOOLCHAIN_SHA256=62a63b981fe391a9cbad7ef51b17e49aeaa3e7b0d029b36ca1e9c3b2a9b78823
PICOTOOL_ARCHIVE=picotool-2.3.0-x86_64-lin.tar.gz
PICOTOOL_SHA256=d8222dbb04e83427bcaef8466fe6e76b0e0193c3a140029934bd365dae49f61f

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) ;;
    *)
        echo "This provisioning helper supports GitHub's Linux x86_64 runner only." >&2
        exit 1
        ;;
esac

rm -rf "$TOOL_ROOT"
mkdir -p "$TOOL_ROOT"

git clone --branch 2.3.0 --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/raspberrypi/pico-sdk.git "$SDK_DIR"
found_sdk=$(git -C "$SDK_DIR" rev-parse HEAD)
if [ "$found_sdk" != "$SDK_COMMIT" ]; then
    echo "Pico SDK checkout drift: expected $SDK_COMMIT, found $found_sdk" >&2
    exit 1
fi

curl --fail --location --silent --show-error \
    "https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/binrel/$TOOLCHAIN_ARCHIVE" \
    --output "$TOOL_ROOT/$TOOLCHAIN_ARCHIVE"
printf '%s  %s\n' "$TOOLCHAIN_SHA256" "$TOOL_ROOT/$TOOLCHAIN_ARCHIVE" | \
    sha256sum -c -
tar -xJf "$TOOL_ROOT/$TOOLCHAIN_ARCHIVE" -C "$TOOL_ROOT"

curl --fail --location --silent --show-error \
    "https://github.com/raspberrypi/pico-sdk-tools/releases/download/v2.3.0-0/$PICOTOOL_ARCHIVE" \
    --output "$TOOL_ROOT/$PICOTOOL_ARCHIVE"
printf '%s  %s\n' "$PICOTOOL_SHA256" "$TOOL_ROOT/$PICOTOOL_ARCHIVE" | \
    sha256sum -c -
tar -xzf "$TOOL_ROOT/$PICOTOOL_ARCHIVE" -C "$TOOL_ROOT"

test -x "$TOOLCHAIN_DIR/bin/arm-none-eabi-gcc"
test -f "$PICOTOOL_DIR/picotoolConfig.cmake"

if [ -n "${GITHUB_ENV:-}" ]; then
    printf 'PICO_SDK_PATH=%s\n' "$SDK_DIR" >>"$GITHUB_ENV"
    printf 'PICO_TOOLCHAIN_PATH=%s\n' "$TOOLCHAIN_DIR" >>"$GITHUB_ENV"
    printf 'PICOTOOL_DIR=%s\n' "$PICOTOOL_DIR" >>"$GITHUB_ENV"
fi

echo "Pinned native toolchain ready under $TOOL_ROOT"
