#!/bin/sh

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml")
BUILD_DIR="$ROOT/build/freewili-foxhunt-$VERSION"
ARCHIVE="$ROOT/dist/freewili-foxhunt-$VERSION.tar.gz"
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-0}

rm -rf "$ROOT/build/freewili-foxhunt-$VERSION"
mkdir -p "$BUILD_DIR" "$ROOT/dist"
for artifact in \
    "$ROOT/native/dist/waverider_display.elf" \
    "$ROOT/native/dist/waverider_display.uf2" \
    "$ROOT/native/dist/waverider_installer.elf" \
    "$ROOT/native/dist/waverider_installer.uf2"
do
    if [ ! -f "$artifact" ]; then
        echo "Missing native artifact: $artifact" >&2
        echo "Run deploy/build-native-apps.sh first." >&2
        exit 1
    fi
done
(
    cd "$ROOT"
    sha256sum -c native/dist/SHA256SUMS
)
cp -a \
    "$ROOT/AGENTS.md" \
    "$ROOT/CHANGELOG.md" \
    "$ROOT/CONTRIBUTING.md" \
    "$ROOT/COPYRIGHT" \
    "$ROOT/HISTORY.md" \
    "$ROOT/LICENSE" \
    "$ROOT/LICENSES.md" \
    "$ROOT/README.md" \
    "$ROOT/SECURITY.md" \
    "$ROOT/THIRD_PARTY_NOTICES.md" \
    "$ROOT/CMakeLists.txt" \
    "$ROOT/.gitmodules" \
    "$ROOT/pyproject.toml" \
    "$ROOT/install.sh" \
    "$ROOT/uninstall.sh" \
    "$BUILD_DIR/"
cp -a "$ROOT/LICENSES" "$BUILD_DIR/"
cp -a "$ROOT/assets" "$ROOT/bin" "$ROOT/config" "$ROOT/deploy" "$ROOT/docs" "$ROOT/native" "$ROOT/src" "$ROOT/tools" "$ROOT/vendor" "$BUILD_DIR/"
# CI provisioning is maintainer/release infrastructure. It is intentionally
# absent from the user-facing device-install bundle, which has no native-source
# checkout or reason to download a compiler toolchain.
rm -f "$BUILD_DIR/deploy/setup-native-ci-linux.sh"
# The independently maintained FX0177 stock-firmware quiet/dark patch is kept
# in the Git repository for its own users, but is intentionally not distributed
# as part of the WaveRider application release. Installing WaveRider must never
# imply or encourage replacing a user's stock Display firmware.
rm -f \
    "$BUILD_DIR/docs/FW2_V07_STARTUP_PATCH.md" \
    "$BUILD_DIR/docs/NIGHT_DEFAULTS.md" \
    "$BUILD_DIR/tools/fw2_patch_display_startup.py" \
    "$BUILD_DIR/tools/fw2_set_night_defaults.py"
find "$BUILD_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$BUILD_DIR" -type f -name '*.pyc' -delete
rm -rf "$BUILD_DIR/src/freewili_foxhunt.egg-info"
find "$BUILD_DIR" -type f -exec touch -h -t 197001010000 {} +
find "$BUILD_DIR" -type d -exec touch -h -t 197001010000 {} +
LC_ALL=C tar --uid 0 --gid 0 --uname root --gname root \
    -C "$ROOT/build" -cf - "freewili-foxhunt-$VERSION" | \
    gzip -n >"$ARCHIVE"
digest=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
printf '%s  %s\n' "$digest" "$(basename "$ARCHIVE")" >"$ARCHIVE.sha256"
echo "$ARCHIVE"
