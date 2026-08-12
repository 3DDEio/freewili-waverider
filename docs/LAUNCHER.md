# WaveRider one-tap launcher

## Current installation

WaveRider now has a persistent stock Apps-menu entry backed by a native Display
application. Selecting it draws the splash, powers and enables the CM0 path,
and reveals live CM0 data without opening an interactive Linux terminal.

- Application: `/opt/freewili-foxhunt`
- Service: `/etc/systemd/system/freewili-foxhunt.service`
- Saved lists and marks: `/var/lib/freewili-foxhunt`
- Runtime status: `/run/freewili-foxhunt/status.json`
- Apps-menu image: `/apps/Radio/waverider_display.uf2`
- Splash and RSSI scale: drawn by the native app; no Main-SD image dependency

The service remains separately maintainable from the CM0 console, but normal
launch no longer requires the user to open Wi-Li-nux or attach a shell.

## Required user experience

The finished installation adds **WaveRider** under **Apps → Radio** in the
stock FreeWili 2 menu.
Selecting it must be the only startup action:

1. Show the WaveRider splash immediately.
2. Enable FPGA power zone 6 and CM0 power zone 17 if either is off.
3. Release `CM0_RUNPG`.
4. invoke the stock Linux-enable action represented on v07 by `l\\a`.
5. Wait for the CM0 bridge and `/run/freewili-foxhunt/status.json` to report
   ready, without opening or attaching any interactive Linux shell route.
6. Start or reveal `freewili-foxhunt.service` and transition to the live panel.
7. If startup fails, show a bounded **Retry / Diagnostics / Back** screen rather
   than leaving `Linux is now booting...` indefinitely.

The launcher must be idempotent: selecting it while Linux or WaveRider is
already running reveals the existing panel and must not restart the bridge or
create a duplicate panel.

## Process boundary

The launcher is intentionally small. It owns power, boot, readiness, and
navigation only. RTL-SDR access, FFT/RSSI processing, frequency-list storage,
waterfall rendering, and marks remain in the CM0 Python service.

This is a functional requirement, not merely a simpler UI: tested v07 Main
firmware stops acknowledging CM0 GUI-console commands while `TYPE_SHELL` is
attached. The launcher must use power/readiness signaling and systemd startup,
never a hidden Linux-terminal session.

```text
FreeWili Apps menu
  -> Radio
     -> WaveRider launcher on Main
        -> power FPGA + CM0
        -> release CM0 reset
        -> stock Linux enable
        -> CM0 systemd starts WaveRider
        -> readiness/status handshake
        -> persistent WaveRider Display panel
```

## Safe integration boundary

FreeWili 2's public material confirms that stock firmware can launch UF2 and
WiliWASM applications, and that CM0 applications use the supported screen API.
It does not currently document the v07 file or manifest format for registering
a third-party entry inside the stock Apps menu. A standalone UF2 that replaces
the Main application is not an acceptable shortcut because WaveRider must
preserve the stock firmware, recovery menus, and power controls.

Before implementing the Main-side artifact, inspect the installed v07 Main SD
and stock menu registry, then copy the mechanism used by Wi-Li-nux. The launcher
is complete only when it appears beside the stock apps and survives a normal
power cycle without a manual Linux Terminal step.

## Acceptance tests

- Cold device: select WaveRider once; live SDR panel appears without visiting
  Wi-Li-nux.
- Warm Linux: select WaveRider; existing service/panel is reused.
- Missing SDR: bounded error screen offers Retry and Back.
- Bridge failure: launcher reports diagnostics and never restart-loops.
- Back/Home: returns to stock firmware without corrupting either SD card.
- Reboot: Apps-menu entry and CM0 service activation remain installed.
