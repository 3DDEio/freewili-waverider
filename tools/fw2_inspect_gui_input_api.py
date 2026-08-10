#!/usr/bin/env python3
"""Read the installed CM0 OneWili GUI input surface without changing it."""

from __future__ import annotations

import argparse

import serial

try:
    from .fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly
except ImportError:  # direct script execution
    from fw2_deploy_live_fix import detach_shell, open_shell, shell_ok, shell_readonly


QUERIES = (
    "python3 -c 'import onewili,inspect,os; print(os.path.dirname(inspect.getfile(onewili)))'",
    "grep -R -n -E 'list.*selected|selected.*list|get.*control|read.*button|button.*event' "
    "/opt/onewili/python /usr/local/lib/python3*/dist-packages/onewili "
    "/usr/lib/python3*/site-packages/onewili 2>/dev/null | head -n 240",
    "find /opt/onewili/python /usr/local/lib/python3*/dist-packages/onewili "
    "/usr/lib/python3*/site-packages/onewili -type f 2>/dev/null | head -n 160",
    "for f in /opt/onewili/python/onewili/menus/gui*.py; do echo ===$f; "
    "grep -n '^    def ' $f; done",
    "sed -n '1,230p' /opt/onewili/python/onewili/menus/gui.py; "
    "sed -n '1,230p' /opt/onewili/python/onewili/menus/gui_control_properties.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect installed OneWili GUI input API")
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    with serial.Serial(args.port, 1_000_000, timeout=0.05) as port:
        open_shell(port)
        shell_ok(port, "stty -echo")
        try:
            for index, query in enumerate(QUERIES, start=1):
                print(f"QUERY {index}")
                print(shell_readonly(port, query, timeout=30.0))
        finally:
            try:
                shell_ok(port, "stty echo")
            except Exception:
                pass
            # Schedule WaveRider after the routed shell exits; v07 suppresses
            # Display replies while a TYPE_SHELL client remains attached.
            try:
                shell_ok(
                    port,
                    "sudo systemd-run --unit=waverider-inspect-resume --on-active=2s "
                    "/bin/systemctl restart freewili-foxhunt.service",
                )
            finally:
                detach_shell(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
