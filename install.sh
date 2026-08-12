#!/bin/sh

set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run the installer with sudo." >&2
    exit 1
fi

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_DIR=/opt/freewili-foxhunt
PREVIOUS_DIR=/opt/freewili-foxhunt.previous
STAGE_DIR=/opt/.freewili-foxhunt.new.$$
STATE_DIR=/var/lib/freewili-foxhunt
RTLSDR_VERSION=2.0.2-2+b1
LIBRTLSDR_SHA256=4edd72c4f9a250a237a1d6d56a3120638d147560fd9e3d7e78a693b010bbb7f9
RTLSDR_SHA256=d139e07182836a94244285f441ba8355ff7e953a58f03090837d203426d48e3e
ROLLBACK_DIR=/var/lib/freewili-foxhunt/install-rollback
ROLLBACK_ARMED=0

restore_previous_runtime() {
    rm -rf "$INSTALL_DIR"
    if [ -d "$PREVIOUS_DIR" ]; then
        mv "$PREVIOUS_DIR" "$INSTALL_DIR"
    fi
}

install_system_file() {
    source=$1
    destination=$2
    mode=$3
    backup=$4
    if [ -e "$destination" ]; then
        cp -a "$destination" "$backup"
    else
        : >"$backup.missing"
    fi
    install -m "$mode" "$source" "$destination"
}

restore_system_file() {
    destination=$1
    backup=$2
    if [ -e "$backup" ]; then
        cp -a "$backup" "$destination"
    elif [ -e "$backup.missing" ]; then
        rm -f "$destination"
    fi
}

rollback_upgrade() {
    if [ "$ROLLBACK_ARMED" -ne 1 ]; then
        return
    fi
    rollback_failed=0
    if [ -d "$ROLLBACK_DIR" ]; then
        restore_system_file /usr/local/bin/foxhuntctl "$ROLLBACK_DIR/foxhuntctl" || rollback_failed=1
        restore_system_file /usr/local/bin/foxhunt-guard "$ROLLBACK_DIR/foxhunt-guard" || rollback_failed=1
        restore_system_file /etc/systemd/system/freewili-foxhunt.service \
            "$ROLLBACK_DIR/freewili-foxhunt.service" || rollback_failed=1
        restore_system_file /etc/systemd/system/freewili-foxhunt-guard.service \
            "$ROLLBACK_DIR/freewili-foxhunt-guard.service" || rollback_failed=1
    fi
    restore_previous_runtime || rollback_failed=1
    systemctl daemon-reload >/dev/null 2>&1 || true
    ROLLBACK_ARMED=0
    return "$rollback_failed"
}

cleanup_stage() {
    status=$1
    trap - EXIT HUP INT TERM
    rm -rf "$STAGE_DIR"
    if [ "$ROLLBACK_ARMED" -eq 1 ]; then
        rollback_upgrade || true
        echo "WaveRider upgrade was interrupted; the previous version was restored." >&2
    fi
    if [ -d "$ROLLBACK_DIR" ]; then
        rm -rf "$ROLLBACK_DIR"
    fi
    exit "$status"
}
trap 'cleanup_stage $?' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [ "$(dpkg --print-architecture)" != "arm64" ]; then
    echo "This release targets the FreeWili CM0 arm64 image." >&2
    exit 1
fi
if [ ! -x /usr/local/bin/fwcm0 ] || [ ! -d /opt/onewili ]; then
    echo "The current FreeWili CM0 image with fwcm0 and OneWili is required." >&2
    exit 1
fi

set -- \
    "$SOURCE_DIR/vendor/debian-arm64/librtlsdr0_2.0.2-2+b1_arm64.deb" \
    "$SOURCE_DIR/vendor/debian-arm64/rtl-sdr_2.0.2-2+b1_arm64.deb"
if [ ! -f "$1" ] || [ ! -f "$2" ]; then
    echo "The exact offline RTL-SDR packages are missing from this release." >&2
    exit 1
fi
printf '%s  %s\n' "$LIBRTLSDR_SHA256" "$1" | sha256sum -c -
printf '%s  %s\n' "$RTLSDR_SHA256" "$2" | sha256sum -c -

installed_librtlsdr=$(dpkg-query -W -f='${Version}' librtlsdr0 2>/dev/null || true)
installed_rtlsdr=$(dpkg-query -W -f='${Version}' rtl-sdr 2>/dev/null || true)
if [ "$installed_librtlsdr" != "$RTLSDR_VERSION" ] || \
   [ "$installed_rtlsdr" != "$RTLSDR_VERSION" ]; then
    dpkg -i "$1" "$2"
fi

install -d -m 0755 "$STAGE_DIR" "$STAGE_DIR/src" "$STAGE_DIR/assets/splash" "$STATE_DIR/lists"
cp -a "$SOURCE_DIR/src/freewili_foxhunt" "$STAGE_DIR/src/"
if [ -f "$SOURCE_DIR/assets/splash/WAVERIDR.FWI" ]; then
    install -m 0644 "$SOURCE_DIR/assets/splash/WAVERIDR.FWI" "$STAGE_DIR/assets/splash/WAVERIDR.FWI"
fi
install -m 0644 "$SOURCE_DIR/pyproject.toml" "$STAGE_DIR/pyproject.toml"
PYTHONPYCACHEPREFIX="$STAGE_DIR/.pycache" \
    PYTHONPATH="$STAGE_DIR/src:/opt/onewili/python:/opt/onewili/cm0/python" \
    /usr/bin/python3 -m compileall -q "$STAGE_DIR/src/freewili_foxhunt"
rm -rf "$STAGE_DIR/.pycache"

# Replace the runtime tree as one same-filesystem rename so files removed by a
# release cannot survive an upgrade. Retain one complete predecessor until the
# new tree and system files are in place.
rm -rf "$PREVIOUS_DIR"
if [ -d "$INSTALL_DIR" ]; then
    mv "$INSTALL_DIR" "$PREVIOUS_DIR"
fi
if ! mv "$STAGE_DIR" "$INSTALL_DIR"; then
    if [ -d "$PREVIOUS_DIR" ] && [ ! -e "$INSTALL_DIR" ]; then
        mv "$PREVIOUS_DIR" "$INSTALL_DIR"
    fi
    echo "WaveRider runtime promotion failed; the previous tree was restored." >&2
    exit 1
fi
ROLLBACK_ARMED=1

# The runtime rename above and these four integration files form one upgrade.
# Preserve every predecessor first, then restore the whole set if any install
# or daemon-reload step fails so a public upgrade cannot leave a mixed version.
rm -rf "$ROLLBACK_DIR"
install -d -m 0700 "$ROLLBACK_DIR"
if ! (
    set -e
    install_system_file "$SOURCE_DIR/bin/foxhuntctl" \
        /usr/local/bin/foxhuntctl 0755 "$ROLLBACK_DIR/foxhuntctl"
    install_system_file "$SOURCE_DIR/bin/foxhunt-guard" \
        /usr/local/bin/foxhunt-guard 0755 "$ROLLBACK_DIR/foxhunt-guard"
    install_system_file "$SOURCE_DIR/deploy/freewili-foxhunt.service" \
        /etc/systemd/system/freewili-foxhunt.service 0644 \
        "$ROLLBACK_DIR/freewili-foxhunt.service"
    install_system_file "$SOURCE_DIR/deploy/freewili-foxhunt-guard.service" \
        /etc/systemd/system/freewili-foxhunt-guard.service 0644 \
        "$ROLLBACK_DIR/freewili-foxhunt-guard.service"
    systemctl daemon-reload
); then
    rollback_upgrade || true
    rm -rf "$ROLLBACK_DIR"
    echo "WaveRider integration install failed; the complete previous version was restored." >&2
    exit 1
fi

if ! find "$STATE_DIR/lists" -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    install -m 0644 "$SOURCE_DIR/config/default-list.json" "$STATE_DIR/lists/2m-and-70cm-foxhunt.json"
fi

systemctl disable freewili-foxhunt.service 2>/dev/null || true
systemctl disable freewili-foxhunt-guard.service 2>/dev/null || true

# All required installation steps completed. From this point the retained
# predecessor is the supported manual rollback rather than an active journal.
ROLLBACK_ARMED=0
rm -rf "$ROLLBACK_DIR"

echo "FreeWili Foxhunt installed."
if [ -d "$PREVIOUS_DIR" ]; then
    echo "Previous runtime retained at $PREVIOUS_DIR until this upgrade is accepted."
fi
echo "Run: sudo foxhuntctl doctor"
echo "Then activate the SDR profile: sudo foxhuntctl host --reboot"
