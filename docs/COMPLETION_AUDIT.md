# WaveRider connected-device completion audit

This document records the evidence required before WaveRider is called complete.
Passing host tests or injected controls is not a substitute for observing the
corresponding physical behavior on the connected FreeWili 2.

## Requirement status

| Requirement | Authoritative completion evidence | Current evidence | Status |
| --- | --- | --- | --- |
| Real-time centered waterfall | Connected CM0 status reports at least 3 committed rows/second with no growing SDR queue; final device screen visibly continues scrolling around the center marker. | CM0 reported 3.6 rows/second and queue depth 0 after removing redundant steady-state mailbox writes. A final AgentIO framebuffer contains a filled, multi-level waterfall with the selected-frequency centerline. Physical continued scrolling still needs one final observation after cold boot. | Pending final physical observation |
| Frequency controls | A physical control changes both `wr_sel` and `wr_freq`; the large displayed frequency and RTL-SDR tune target agree. | The user physically confirmed D-pad and Check tuning, plus all five context actions: Add inserted an entry, Remove deleted it, Next and Previous tuned in both directions, and Refresh displayed health before repainting the waterfall. | Proven |
| Frequency Library | Physical Lists opens the saved library; digit-position correction, paging, Live +/-, Tune, confirmed Delete, and atomic persistence behave as labeled after power restoration. | The revised native and CM0 builds are installed. Connected injected controls opened Lists, entered and saved exactly 433.200 MHz, toggled it into Live, reported the corrected `LIVE 11/16` count, and retained both the saved row and Live badge across a CM0 service restart. This pass exposed and fixed stale global-count transport plus ordered `00-` list-file persistence. Physical-key/touch repetition and a cold-power persistence check remain. | **Pending final physical and cold-power validation** |
| Accurate RSSI | With a stable known signal, attenuation or antenna movement produces a prompt, directionally correct dBFS change; the numeric value, scale marker, waterfall intensity, and LED count agree. | Native marker mapping is linear and clamped from -70 to -10 dBFS. Connected runtime snapshots reported live values around -65 to -64 dBFS and placed the marker near the cold end. No controlled attenuation/movement check has been recorded for the final build. | **Not yet proven under controlled signal change** |
| Morse message detection | A clean, centered, repeating NFM Morse transmission is decoded without stopping the waterfall; only a message supported by at least three agreeing receptions produces a bounded popup; verified detections remain browsable by frequency with time/repeats/quality; confirmed Clear removes all history; and an unmodulated carrier or inconsistent callsign is withheld. | Synthetic 240 kHz IQ recovers `KO6FQY`; 13-to-20 WPM startup mismatch, non-800 Hz tone acquisition, sub-dot dropout repair, complete payload timing, jitter/outlier resistance, callsign consistency, carrier rejection, weighted repeat consensus, bounded native framing, atomic 100-record storage, 16-record verified replay, frequency grouping, confirmed candidate/verified clearing, popup rendering, and suppression pass in the host suite. Earlier connected 147.500 MHz transcription contained substitutions; the hardened build still needs live proof. | **Pending repeatable clean over-the-air recovery and physical MSGS grouping/Clear validation** |
| Pocket Alert haptics | With Pocket Alert enabled, a below-to-above threshold crossing produces exactly three pulses; a steady carrier does not repeat, another crossing inside 30 seconds is suppressed, and a crossing after both cooldown and 3 dB re-arm alerts again. Settings survive restart. | An independent production FW2 v07 bench trace identified Display GPIO35 after GPIO46 toggled correctly but failed to move the connected motor. A bounded WaveRider GPIO35 build retained the 12 mA drive and three 150 ms pulses / 80 ms gaps; the user physically confirmed all three manual-Test pulses on FX0177 on 2026-08-11. See `docs/HAPTIC_EVIDENCE.md`. | **Manual Test proven; pending RF crossing, cooldown, re-arm, persistence, and additional board-revision validation** |
| Automatic CM0 Linux startup | Launch WaveRider from the stock Apps menu after a cold boot without opening Linux Terminal; CM0 service reaches live SDR/display state promptly and startup progress is truthful. | A later untouched fresh boot remained on **Waiting for SDR Data** even though CM0 sampling was live. Diagnosis isolated a retained Main `TYPE_SHELL` route. A startup-only, exact-process recovery is installed: after a 20-second grace it can hang up only the bridge-owned `login -f pi`, causing the existing bridge to send `SHELL_EXIT`; it is bounded to 90 seconds, disabled after the first successful Display connection, and inhibited during maintenance. A subsequent launch took about two minutes. The service now starts after the bridge rather than after full `multi-user.target`, SDR initialization overlaps the Display handshake, and warm launches skip redundant mailbox creation. Six dim-green subsystem milestones advance the top LEDs; the seventh means the first live row. 153 host tests pass. | **Pending timed untouched cold-boot validation** |
| Persistent operation | After complete power removal and restoration, the Apps entry remains and the same build becomes live. | The Apps entry, stored contest list, and executable survived full power removal; the user launched WaveRider and it eventually returned to live SDR data. | Proven |
| Reproducible public deployment | Clean release contains the final CM0/native artifacts, documentation, offline dependencies, checksums, and a safe install path. | 143 host tests pass. A clean staged checkout independently passed the earlier release suite, native artifact checks, archive construction, and archive checksum validation. GitHub CI passes on Python 3.11 and 3.13. Public prerelease `v0.1.0-beta.1` was downloaded from GitHub and its published checksum verified. The native installer remains subject to the SRAM-only gate. | Proven for beta; current working changes need the next release pass |

## Public project record

- Repository: <https://github.com/3DDEio/freewili-waverider>
- First public prerelease:
  <https://github.com/3DDEio/freewili-waverider/releases/tag/v0.1.0-beta.1>
- Software license: GPL-3.0-or-later.
- Documentation and original artwork: CC BY-SA 4.0.
- Protected `main`: both CI jobs and CODEOWNER review required; stale approvals
  dismissed; force pushes and deletion blocked.
- Security: secret scanning, push protection, web commit signoff, and private
  vulnerability reporting enabled.
- Known distribution uncertainty: the checked-out public OneWili source did
  not contain a standalone license file. WaveRider does not bundle that source;
  redistribution rights should be confirmed with FreeWili before that boundary
  changes.

## Final hands-on audit

Perform these steps without a routed Linux shell attached:

1. On the current WaveRider screen, note the large active frequency.
2. Add a specific frequency through the numeric editor, tune it, then remove
   it. Confirm the saved list and active receiver agree.
3. Open Receiver Status from `SDR LIVE`. Confirm it distinguishes CM0 link,
   SDR streaming, last-row age, and command synchronization.
4. On a stable beacon, move or attenuate the antenna. Confirm RSSI becomes more
   negative when the signal weakens and less negative when it strengthens; the
   scale marker and illuminated LED count must move in the same direction.
5. On launch, time from selecting WaveRider to the first live row. Confirm one
   through six dim-green LEDs advance left-to-right with actual startup
   milestones, the seventh appears only when live data begins, and no yellow
   flashing occurs during a healthy boot. The live view must then become the
   left-to-right blue-to-yellow RSSI ladder. Disconnect or stop the SDR and
   confirm all seven flash yellow only for that real fault.
6. Confirm `SDR LIVE`, a changing RSSI value, and a continuously scrolling
   centered waterfall remain stable after the startup and Refresh paths.
7. Open Pocket Alert and run Red **Test**. Confirm three distinct pulses, then
   repeat the RF threshold crossing, cooldown, 3 dB re-arm, and restart
   persistence checks described in the requirement table.
8. Tune the KO6FQY beacon at 147.500 MHz. Confirm the complete uppercase
   `KO6FQY JOIN NORCALCYBER.IO! KO6FQY` popup appears while the waterfall keeps
   moving, closes after eight seconds, and is not repeated immediately for the
   same transmission.

Only after all eight observations pass should the active implementation goal be
marked complete.
