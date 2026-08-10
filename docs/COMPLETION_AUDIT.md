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
| Pocket Alert haptics | With Pocket Alert enabled, a below-to-above threshold crossing produces exactly three pulses; a steady carrier does not repeat, another crossing inside 30 seconds is suppressed, and a crossing after both cooldown and 3 dB re-arm alerts again. Settings survive restart. | The physical Test produced no vibration even though connected diagnostics recorded matching requested/output-latch/settled-pad transitions for every GPIO46 edge. Official public sources provide only a secondary `GPIO46` note marked `TODO`; current logic-analyzer docs also use GPIO46 as an analog input. Output drive is disabled. The input-only weak-pull scan was also negative: GPIO31 twice, then GPIO36, GPIO44, and GPIO46 once each, all restored after testing. | **Blocked on authoritative motor-control specification or confirmation that a motor is populated** |
| Automatic CM0 Linux startup | Launch WaveRider from the stock Apps menu after a cold boot without opening Linux Terminal; CM0 service reaches live SDR/display state. | After a full reboot, the user launched WaveRider from Apps and it eventually entered live SDR operation without manually opening Linux Terminal. The native app now shows staged startup progress and a browsable Receiver Status page while this wait is in progress. | Proven; final progress-page UX pending |
| Persistent operation | After complete power removal and restoration, the Apps entry remains and the same build becomes live. | The Apps entry, stored contest list, and executable survived full power removal; the user launched WaveRider and it eventually returned to live SDR data. | Proven |
| Reproducible public deployment | Clean release contains the final CM0/native artifacts, documentation, offline dependencies, checksums, and a safe install path. | 123 host tests pass. A clean staged checkout independently passed those tests, native artifact checks, archive construction, and archive checksum validation. GitHub CI passes on Python 3.11 and 3.13. Public prerelease `v0.1.0-beta.1` was downloaded from GitHub and its published checksum verified. The native installer remains subject to the SRAM-only gate. | Proven |

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
5. On launch, confirm the seven visible LEDs are red, then yellow while waiting,
   green when ready, and finally become a left-to-right blue-to-yellow RSSI
   ladder. Disconnect or stop the SDR and confirm all seven flash yellow.
6. Confirm `SDR LIVE`, a changing RSSI value, and a continuously scrolling
   centered waterfall remain stable after the startup and Refresh paths.
7. After FreeWili supplies an authoritative motor-control specification, restore
   the driver behind the experimental compile-time gate and repeat the physical
   Test, RF threshold crossing, cooldown, and re-arm validation.

Only after all seven observations pass should the active implementation goal be
marked complete.
