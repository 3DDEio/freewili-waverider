#!/bin/sh

# Build a deterministic complete-source archive with pinned submodule contents.
# GitHub's generated source archives contain only gitlinks, so they cannot by
# themselves rebuild WaveRider's native UF2 files.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml")
PREFIX="freewili-waverider-source-$VERSION"
ARCHIVE="$ROOT/dist/$PREFIX.tar.gz"
MANIFEST=$(mktemp /tmp/waverider-source-manifest.XXXXXX)
STAGE=$(mktemp -d /tmp/waverider-source-release.XXXXXX)
COPYFILE_DISABLE=1
export COPYFILE_DISABLE

cleanup() {
    rm -f "$MANIFEST"
    rm -rf "$STAGE"
}
trap cleanup EXIT HUP INT TERM

git -C "$ROOT" submodule status --recursive | while IFS= read -r line; do
    case "$line" in
        " "*) ;;
        *)
            echo "Every source submodule must be initialized at its recorded commit: $line" >&2
            exit 1
            ;;
    esac
done

if [ -n "$(git -C "$ROOT" ls-files --others --exclude-standard)" ]; then
    echo "The complete-source archive requires every release file to be tracked." >&2
    git -C "$ROOT" ls-files --others --exclude-standard >&2
    exit 1
fi

# Verify the pinned source without changing either vendor worktree. The archive
# intentionally carries pristine vendor source plus WaveRider's reviewed patch
# files, exactly like a recursive clone.
python3 "$ROOT/tools/prepare_wilibsp.py" --verify-only
git -C "$ROOT" ls-files -z -- . ':!wilibsp' >"$MANIFEST"
mkdir -p "$STAGE/$PREFIX" "$ROOT/dist"
(
    cd "$ROOT"
    tar --null -T "$MANIFEST" -cf -
) | tar -xf - -C "$STAGE/$PREFIX"
# Read vendor source from the recorded commits rather than from their working
# trees. Native builds apply patches in-place, so this keeps the complete-source
# archive pristine and reproducible even when it is built after a native build.
mkdir -p "$STAGE/$PREFIX/wilibsp" "$STAGE/$PREFIX/wilibsp/libs/onewili"
git -C "$ROOT/wilibsp" archive --format=tar HEAD | \
    tar -xf - -C "$STAGE/$PREFIX/wilibsp"
git -C "$ROOT/wilibsp/libs/onewili" archive --format=tar HEAD | \
    tar -xf - -C "$STAGE/$PREFIX/wilibsp/libs/onewili"
(
    cd "$STAGE/$PREFIX"
    python3 tools/prepare_wilibsp.py \
        --write-source-marker .waverider-native-source.json
)

# The checked-out vendor trees are kept pristine. WaveRider's reviewed deltas
# remain explicit patch files and are applied by tools/prepare_wilibsp.py.
python3 "$ROOT/tools/build_deterministic_tar.py" "$STAGE/$PREFIX" "$ARCHIVE"
digest=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
printf '%s  %s\n' "$digest" "$(basename "$ARCHIVE")" >"$ARCHIVE.sha256"
echo "$ARCHIVE"
