# Resolved FW2 v07 field report: CM0 router timeout

Observed and recovered 2026-08-08 on a FreeWili 2 Founders/DEFCON unit.

## Device

- Main firmware: FW2 v07
- Hardware revision: 2.0
- Bootloader: v2.2
- Device serial: FX0177
- PCB serial: FWFB0200726XX03D
- CM0 OS: Debian GNU/Linux 13.4 (Trixie), arm64
- CM0 kernel: `6.12.75+rpt-rpi-v8`

## Initial symptom

Wi-Li-nux → Linux Terminal remained on `Linux is now booting...`, and commands
typed into that panel produced no response. The CM0's direct USB gadget console
appeared on macOS and automatically logged in as `pi`, proving that Linux had
completed boot.

`fwcm0-bridge.service` repeatedly exited with `error: router timeout`. Stopping
the service and running `fwcm0 status` directly produced the same timeout.

## Failed-state evidence

- Main reported FPGA, USB hub, FTDI, and CM0 power zones on.
- Main reported the CM0 run line released/high.
- FPGA settings were `cpu125`, divider `4 + 0/256`, communications mode `SPI`.
- The live kernel clock framework reported a 125 MHz UART clock.
- CM0 exposed the expected SPI0, UART0, GPIO21 software-CS, and flow-control
  pin muxes.
- A system-call trace showed successful two-byte SPI transfers followed by
  continuous UART polls with no received bytes.
- SPI rates from 250 kHz through 7.5 MHz all timed out.
- Plausible UART rates from 115.2 kbaud through 7.8125 Mbaud timed out.
- Temporary diagnostics using SPI modes 0–3 and with RTS/CTS disabled timed out.
- Cycling only FPGA power zone 6 did not restore the link.

## Recovery

A documented **Main CPU Software Reset** restored the router immediately. It
was invoked from Hardware → Settings → Software Reset. No firmware was flashed,
no settings were reset, and neither SD card was modified.

After the reset:

```text
init_done=1 boot_ready=1 quiesced=0 ready=0
```

- `fwcm0-bridge.service` stayed active.
- `/run/fwcm0-bridge.sock` existed.
- A transient foxhunt launch reported `display_connected: true`.
- The stock Main Linux shell opened through the FPGA mailbox.
- `echo FW2_MAILBOX_OK` returned `FW2_MAILBOX_OK` through the full round trip.

The same Main reset was also triggered through
`dev.hardware.settings_home.software_reset()`. The API call itself timed out as
the Main USB endpoint reset, which is expected, and the bridge recovered
automatically afterward.

## Conclusion

This incident does not justify a firmware reflash or hardware-return request.
The evidence is most consistent with stale or incomplete Main/FPGA router
initialization after the earlier CM0/FPGA power and reset sequence. The first
recovery action for this exact symptom is a Main CPU Software Reset.

Escalate to FreeWili only if the Main reset fails or the timeout recurs. If it
does recur, include this report and ask whether v07 has a known router
initialization ordering issue.

The Main SD's `/fpga` directory was empty, but the router worked after reset
without adding any file. It is therefore not evidence of a missing gateware
payload.
