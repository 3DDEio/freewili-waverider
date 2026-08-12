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

# Normalize the source state before archiving: reviewed WaveRider vendor
# deltas are present regardless of whether the caller previously built native
# artifacts. The helper is idempotent.
python3 "$ROOT/tools/prepare_wilibsp.py"
git -C "$ROOT" ls-files --recurse-submodules -z >"$MANIFEST"
mkdir -p "$STAGE/$PREFIX" "$ROOT/dist"
(
    cd "$ROOT"
    tar --null -T "$MANIFEST" -cf -
) | tar -xf - -C "$STAGE/$PREFIX"
(
    cd "$STAGE/$PREFIX"
    python3 tools/prepare_wilibsp.py \
        --write-source-marker .waverider-native-source.json
)

# The checked-out vendor trees are kept pristine. WaveRider's reviewed deltas
# remain explicit patch files and are applied by tools/prepare_wilibsp.py.
find "$STAGE/$PREFIX" -type f -exec touch -h -t 197001010000 {} +
find "$STAGE/$PREFIX" -type d -exec touch -h -t 197001010000 {} +
LC_ALL=C tar --uid 0 --gid 0 --uname root --gname root \
    -C "$STAGE" -cf - "$PREFIX" | gzip -n >"$ARCHIVE"
digest=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
printf '%s  %s\n' "$digest" "$(basename "$ARCHIVE")" >"$ARCHIVE.sha256"
echo "$ARCHIVE"
