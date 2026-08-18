#!/bin/sh

# Build a deterministic WaveRider project-source archive. Vendor source is not
# copied into this artifact; tools/fetch_native_dependencies.py retrieves the
# exact reviewed commits directly from FreeWili when a native build is needed.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml")
PREFIX="freewili-waverider-source-$VERSION"
ARCHIVE="$ROOT/dist/$PREFIX.tar.gz"
MANIFEST=$(mktemp /tmp/waverider-source-manifest.XXXXXX)
COPYFILE_DISABLE=1
export COPYFILE_DISABLE

cleanup() {
    rm -f "$MANIFEST"
}
trap cleanup EXIT HUP INT TERM

if [ -n "$(git -C "$ROOT" ls-files --others --exclude-standard)" ]; then
    echo "The project-source archive requires every release file to be tracked." >&2
    git -C "$ROOT" ls-files --others --exclude-standard >&2
    exit 1
fi

git -C "$ROOT" ls-files -z -- . ':!wilibsp' >"$MANIFEST"
mkdir -p "$ROOT/dist"
STAGE=$(mktemp -d /tmp/waverider-source-release.XXXXXX)
trap 'rm -f "$MANIFEST"; rm -rf "$STAGE"' EXIT HUP INT TERM
mkdir -p "$STAGE/$PREFIX"
(
    cd "$ROOT"
    tar --null -T "$MANIFEST" -cf -
) | tar -xf - -C "$STAGE/$PREFIX"
python3 "$ROOT/tools/build_deterministic_tar.py" "$STAGE/$PREFIX" "$ARCHIVE"
digest=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
printf '%s  %s\n' "$digest" "$(basename "$ARCHIVE")" >"$ARCHIVE.sha256"
echo "$ARCHIVE"
