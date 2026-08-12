#!/bin/sh

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WILIBSP_DIR=${WILIBSP_DIR:-"$ROOT/wilibsp"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/native"}
CMAKE_BIN=${CMAKE_BIN:-cmake}

if [ -z "${PICO_SDK_PATH:-}" ]; then
    echo "PICO_SDK_PATH must point to the pinned Pico SDK 2.3.0 checkout." >&2
    exit 1
fi
if [ -z "${PICO_TOOLCHAIN_PATH:-}" ]; then
    echo "PICO_TOOLCHAIN_PATH must point to Arm GNU Toolchain 14.2.Rel1." >&2
    exit 1
fi
sdk_version=$(git -C "$PICO_SDK_PATH" describe --tags --exact-match 2>/dev/null || true)
sdk_commit=$(git -C "$PICO_SDK_PATH" rev-parse HEAD 2>/dev/null || true)
if [ "$sdk_version" != "2.3.0" ] || \
   [ "$sdk_commit" != "98a542c1a62fb549ffb5d66a3e5892b06276b670" ]; then
    echo "Pico SDK drift: expected 2.3.0 at 98a542c1a62fb549ffb5d66a3e5892b06276b670." >&2
    echo "Found tag=${sdk_version:-unknown} commit=${sdk_commit:-unknown}" >&2
    exit 1
fi
toolchain_version=$(
    "$PICO_TOOLCHAIN_PATH/bin/arm-none-eabi-gcc" --version 2>/dev/null | sed -n '1p'
)
case "$toolchain_version" in
    *"Arm GNU Toolchain 14.2.Rel1"*"14.2.1"*) ;;
    *)
        echo "Toolchain drift: expected Arm GNU Toolchain 14.2.Rel1 / GCC 14.2.1." >&2
        echo "Found: ${toolchain_version:-unavailable}" >&2
        exit 1
        ;;
esac

python3 "$ROOT/tools/prepare_wilibsp.py"
python3 "$WILIBSP_DIR/tools/check_app_repo.py" "$ROOT"

if [ ! -f "$BUILD_DIR/CMakeCache.txt" ]; then
    if [ -n "${PICOTOOL_DIR:-}" ]; then
        "$CMAKE_BIN" -S "$ROOT" -B "$BUILD_DIR" -G Ninja \
            -DCMAKE_BUILD_TYPE=RelWithDebInfo \
            -DPICO_SDK_PATH="$PICO_SDK_PATH" \
            -DPICO_TOOLCHAIN_PATH="$PICO_TOOLCHAIN_PATH" \
            -Dpicotool_DIR="$PICOTOOL_DIR"
    else
        "$CMAKE_BIN" -S "$ROOT" -B "$BUILD_DIR" -G Ninja \
            -DCMAKE_BUILD_TYPE=RelWithDebInfo \
            -DPICO_SDK_PATH="$PICO_SDK_PATH" \
            -DPICO_TOOLCHAIN_PATH="$PICO_TOOLCHAIN_PATH"
    fi
fi

"$CMAKE_BIN" --build "$BUILD_DIR" \
    --target waverider_display waverider_installer

python3 "$WILIBSP_DIR/tools/check_app_uf2.py" \
    "$BUILD_DIR/apps/waverider_display/waverider_display.uf2"
python3 "$WILIBSP_DIR/tools/check_app_uf2.py" \
    "$BUILD_DIR/apps/waverider_installer/waverider_installer.uf2"

mkdir -p "$ROOT/native/dist"
cp "$BUILD_DIR/apps/waverider_display/waverider_display.uf2" \
   "$ROOT/native/dist/waverider_display.uf2"
cp "$BUILD_DIR/apps/waverider_display/waverider_display.elf" \
   "$ROOT/native/dist/waverider_display.elf"
cp "$BUILD_DIR/apps/waverider_installer/waverider_installer.elf" \
   "$ROOT/native/dist/waverider_installer.elf"
cp "$BUILD_DIR/apps/waverider_installer/waverider_installer.uf2" \
   "$ROOT/native/dist/waverider_installer.uf2"

(
    cd "$ROOT"
    sha256sum native/dist/waverider_display.elf \
              native/dist/waverider_display.uf2 \
              native/dist/waverider_installer.elf \
              native/dist/waverider_installer.uf2 >native/dist/SHA256SUMS
)

echo "Native WaveRider artifacts are ready in $ROOT/native/dist"
