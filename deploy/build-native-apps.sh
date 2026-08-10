#!/bin/sh

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WILIBSP_DIR=${WILIBSP_DIR:-"$ROOT/research/wilibsp"}
CMAKE_BIN=${CMAKE_BIN:-cmake}

if [ ! -f "$WILIBSP_DIR/build/CMakeCache.txt" ]; then
    echo "Configure the pinned WiliBSP checkout at $WILIBSP_DIR/build first." >&2
    exit 1
fi

# The repository's native/ tree is the release authority.  Keep the pinned
# WiliBSP checkout as a build dependency instead of a second, drifting copy of
# WaveRider's sources.
mkdir -p "$WILIBSP_DIR/apps/waverider_display" \
         "$WILIBSP_DIR/apps/waverider_installer"
cp "$ROOT/native/waverider_display/main.c" \
   "$WILIBSP_DIR/apps/waverider_display/main.c"
cp "$ROOT/native/waverider_display/CMakeLists.txt" \
   "$WILIBSP_DIR/apps/waverider_display/CMakeLists.txt"
cp "$ROOT/native/waverider_installer/main.c" \
   "$WILIBSP_DIR/apps/waverider_installer/main.c"
cp "$ROOT/native/waverider_installer/CMakeLists.txt" \
   "$WILIBSP_DIR/apps/waverider_installer/CMakeLists.txt"
cp "$ROOT/native/embed_binary.py" "$WILIBSP_DIR/apps/embed_binary.py"

"$CMAKE_BIN" --build "$WILIBSP_DIR/build" \
    --target waverider_display waverider_installer

python3 "$WILIBSP_DIR/tools/check_app_uf2.py" \
    "$WILIBSP_DIR/build/apps/waverider_display/waverider_display.uf2"
python3 "$WILIBSP_DIR/tools/check_app_uf2.py" \
    "$WILIBSP_DIR/build/apps/waverider_installer/waverider_installer.uf2"

mkdir -p "$ROOT/native/dist"
cp "$WILIBSP_DIR/build/apps/waverider_display/waverider_display.uf2" \
   "$ROOT/native/dist/waverider_display.uf2"
cp "$WILIBSP_DIR/build/apps/waverider_display/waverider_display.elf" \
   "$ROOT/native/dist/waverider_display.elf"
cp "$WILIBSP_DIR/build/apps/waverider_installer/waverider_installer.elf" \
   "$ROOT/native/dist/waverider_installer.elf"
cp "$WILIBSP_DIR/build/apps/waverider_installer/waverider_installer.uf2" \
   "$ROOT/native/dist/waverider_installer.uf2"

echo "Native WaveRider artifacts are ready in $ROOT/native/dist"
