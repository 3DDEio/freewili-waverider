#!/bin/sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_DIR="$HERE/.installer-venv"

if [ ! -x "$ENV_DIR/bin/python" ]; then
    python3 -m venv "$ENV_DIR"
fi
if ! "$ENV_DIR/bin/python" -c 'import serial, pyfwfinder' >/dev/null 2>&1; then
    "$ENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$HERE/requirements.txt"
fi
exec "$ENV_DIR/bin/python" "$HERE/waverider_installer.py"
