#!/bin/sh

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml")
BUILD_DIR="$ROOT/build/freewili-foxhunt-$VERSION"
ARCHIVE="$ROOT/dist/freewili-foxhunt-$VERSION.tar.gz"

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
    "$ROOT/pyproject.toml" \
    "$ROOT/install.sh" \
    "$ROOT/uninstall.sh" \
    "$BUILD_DIR/"
cp -a "$ROOT/LICENSES" "$BUILD_DIR/"
cp -a "$ROOT/assets" "$ROOT/bin" "$ROOT/config" "$ROOT/deploy" "$ROOT/docs" "$ROOT/native" "$ROOT/src" "$ROOT/tools" "$ROOT/vendor" "$BUILD_DIR/"
find "$BUILD_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$BUILD_DIR" -type f -name '*.pyc' -delete
tar -C "$ROOT/build" -czf "$ARCHIVE" "freewili-foxhunt-$VERSION"
digest=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
printf '%s  %s\n' "$digest" "$(basename "$ARCHIVE")" >"$ARCHIVE.sha256"
echo "$ARCHIVE"
