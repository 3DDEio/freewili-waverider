#!/bin/sh

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml")
BUILD_DIR="$ROOT/build/freewili-foxhunt-$VERSION"
ARCHIVE="$ROOT/dist/freewili-foxhunt-$VERSION.tar.gz"
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-0}
COPYFILE_DISABLE=1
export COPYFILE_DISABLE
MANIFEST=$(mktemp /tmp/waverider-device-manifest.XXXXXX)

cleanup() {
    rm -f "$MANIFEST"
}
trap cleanup EXIT HUP INT TERM

rm -rf "$ROOT/build/freewili-foxhunt-$VERSION"
mkdir -p "$BUILD_DIR" "$ROOT/dist"
for artifact in \
    "$ROOT/native/dist/waverider_display.elf" \
    "$ROOT/native/dist/WaveRider.uf2" \
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
# Copy only tracked, explicitly allowlisted paths. This prevents an ignored
# .env, device capture, compiler output, or editor file from leaking into a
# public archive merely because it sits below a copied directory.
git -C "$ROOT" ls-files -z -- \
    AGENTS.md CHANGELOG.md CONTRIBUTING.md COPYRIGHT HISTORY.md LICENSE \
    LICENSES LICENSES.md README.md SECURITY.md THIRD_PARTY_NOTICES.md \
    CMakeLists.txt .gitmodules pyproject.toml install.sh uninstall.sh \
    assets bin config deploy docs native src tools vendor >"$MANIFEST"
(
    cd "$ROOT"
    tar --null -T "$MANIFEST" -cf -
) | tar -xf - -C "$BUILD_DIR"
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
SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
    python3 "$ROOT/tools/build_deterministic_tar.py" "$BUILD_DIR" "$ARCHIVE"
digest=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
printf '%s  %s\n' "$digest" "$(basename "$ARCHIVE")" >"$ARCHIVE.sha256"
echo "$ARCHIVE"
