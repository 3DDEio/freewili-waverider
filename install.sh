#!/bin/sh

set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run the installer with sudo." >&2
    exit 1
fi

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_DIR=/opt/freewili-foxhunt
STATE_DIR=/var/lib/freewili-foxhunt

if [ "$(dpkg --print-architecture)" != "arm64" ]; then
    echo "This release targets the FreeWili CM0 arm64 image." >&2
    exit 1
fi
if [ ! -x /usr/local/bin/fwcm0 ] || [ ! -d /opt/onewili ]; then
    echo "The current FreeWili CM0 image with fwcm0 and OneWili is required." >&2
    exit 1
fi

if ! command -v rtl_power >/dev/null 2>&1; then
    set -- "$SOURCE_DIR"/vendor/debian-arm64/librtlsdr0_*_arm64.deb "$SOURCE_DIR"/vendor/debian-arm64/rtl-sdr_*_arm64.deb
    if [ ! -f "$1" ] || [ ! -f "$2" ]; then
        echo "rtl_power is missing and the offline Debian packages are not in this release." >&2
        exit 1
    fi
    dpkg -i "$1" "$2"
fi

install -d -m 0755 "$INSTALL_DIR" "$INSTALL_DIR/src" "$INSTALL_DIR/assets/splash" "$STATE_DIR/lists"
cp -a "$SOURCE_DIR/src/freewili_foxhunt" "$INSTALL_DIR/src/"
if [ -f "$SOURCE_DIR/assets/splash/WAVERIDR.FWI" ]; then
    install -m 0644 "$SOURCE_DIR/assets/splash/WAVERIDR.FWI" "$INSTALL_DIR/assets/splash/WAVERIDR.FWI"
fi
install -m 0644 "$SOURCE_DIR/pyproject.toml" "$INSTALL_DIR/pyproject.toml"
install -m 0755 "$SOURCE_DIR/bin/foxhuntctl" /usr/local/bin/foxhuntctl
install -m 0755 "$SOURCE_DIR/bin/foxhunt-guard" /usr/local/bin/foxhunt-guard
install -m 0644 "$SOURCE_DIR/deploy/freewili-foxhunt.service" /etc/systemd/system/freewili-foxhunt.service
install -m 0644 "$SOURCE_DIR/deploy/freewili-foxhunt-guard.service" /etc/systemd/system/freewili-foxhunt-guard.service

if ! find "$STATE_DIR/lists" -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    install -m 0644 "$SOURCE_DIR/config/default-list.json" "$STATE_DIR/lists/2m-and-70cm-foxhunt.json"
fi

systemctl daemon-reload
systemctl disable freewili-foxhunt.service 2>/dev/null || true
systemctl disable freewili-foxhunt-guard.service 2>/dev/null || true

echo "FreeWili Foxhunt installed."
echo "Run: sudo foxhuntctl doctor"
echo "Then activate the SDR profile: sudo foxhuntctl host --reboot"
