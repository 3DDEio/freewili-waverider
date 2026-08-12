#!/bin/sh

set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run the uninstaller with sudo." >&2
    exit 1
fi

purge=${1:-}
foxhuntctl maintenance 2>/dev/null || true
systemctl disable --now freewili-foxhunt.service 2>/dev/null || true
systemctl disable --now freewili-foxhunt-guard.service 2>/dev/null || true
rm -f /etc/systemd/system/freewili-foxhunt.service
rm -f /etc/systemd/system/freewili-foxhunt-guard.service
rm -f /usr/local/bin/foxhuntctl
rm -f /usr/local/bin/foxhunt-guard
rm -rf /opt/freewili-foxhunt
rm -rf /opt/freewili-foxhunt.previous
if [ "$purge" = "--purge" ]; then
    rm -rf /var/lib/freewili-foxhunt
else
    echo "Saved frequency lists remain in /var/lib/freewili-foxhunt."
fi
systemctl daemon-reload
echo "FreeWili Foxhunt removed. Reboot to restore the serial-console profile."
