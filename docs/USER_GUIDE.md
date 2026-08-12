# WaveRider user guide

## Starting WaveRider

1. Connect the RTL-SDR to the FreeWili 2 Linux USB Host socket.
2. Attach an antenna appropriate for the frequency being hunted.
3. Open **Apps** and select **WaveRider**.
4. Wait for the startup page to reach live SDR data.

The top LEDs communicate startup state:

- Red: WaveRider has launched and is powering the receiver system.
- Yellow: CM0 Linux or the SDR is still starting.
- Green: the receiver has become ready.
- Blue through yellow ladder: live relative signal strength, increasing from
  left to right.
- Flashing yellow: receiver data is missing or stale. Read the on-screen status
  page for the cause and next action.

Pocket Alert turns off the single front status LED above Home and automatically
reduces the seven-LED top strip to one eighth of normal brightness. The top
strip retains the same readiness, fault, and RSSI colors. Leaving Pocket Alert
restores the front status LED to its prior state.

Cold Linux startup can take longer than a warm relaunch. The screen remains
interactive and the list can be browsed while WaveRider waits.

## Live controls

| Button | Action |
| --- | --- |
| Gray | Open Lists frequency management |
| Yellow | Open decoded-message history |
| Green | Tune the next frequency |
| Blue | Tune the previous frequency |
| Red | Refresh receiver health and restart SDR collection |

The D-pad browses and immediately tunes the list. Check also applies the
highlighted entry.

## Settings

Press **Page** or tap the RSSI scale to open Settings. Up/Down selects a row;
Check, Green **Open**, or a tap opens its detail screen. Page, Gray, or Back
returns to Settings from a detail screen, and Red **Live** returns directly to
the receiver. Opening Settings never pauses SDR collection.

- **Audio Monitor** shows the planned live-monitor and volume controls. They
  remain locked and the receiver remains muted until the safe high-rate PCM
  path to the speaker and headphone jack is implemented.
- **Pocket Alert** controls vibration enablement, threshold, and the manual
  three-pulse Test.
- **CW Decoder** enables or disables new Morse processing. Disabling it does
  not erase verified messages or hidden candidates; those remain in MSGS until
  the user explicitly clears message history.

## Managing saved and Live frequencies

Press Gray **Lists** to replace the waterfall with Frequency Library. The
library holds up to 100 unique saved values. A mint `LIVE` badge identifies
values included in the current hunt rotation; Live remains limited to 16.

- Up/Down selects a saved value.
- Left/Right moves between library pages.
- Green **Live +/-** or Check toggles the selected value in Live without
  deleting it from Saved.
- Blue **Tune** adds the value to Live if necessary, tunes it, and returns to
  the waterfall.
- Red **Delete** opens a confirmation page. Confirming removes the saved value
  and also removes it from Live.
- At least one frequency must remain in Live.

## Adding or correcting a frequency

1. Open Gray **Lists**, then press Yellow **New**.
2. Type the integer-kHz value on the touch keypad. For example, `433200`
   becomes `433.200 MHz`.
3. If a digit is wrong, use Left/Right to select its position. Use Up/Down or
   touch a replacement digit.
4. Press Check to save, or Red to cancel.

The minimum entry resolution is 1 kHz. Values must be between 24 MHz and
1.766 GHz. Duplicate saved values are rejected.

## Reading the waterfall

The white vertical line is the selected center frequency. A clean centered
carrier should appear as a warm or hot vertical core that cools toward adjacent
frequencies. A genuinely offset transmitter or neighboring signal appears away
from the centerline; WaveRider does not mirror or recenter measured peaks.

New waterfall rows enter at the top and history moves downward. Color meaning
is frozen after a short calibration so antenna movement can be compared over
time.

## Reading RSSI

RSSI is relative dBFS:

- A less-negative number is stronger.
- A more-negative number is weaker.
- Keep gain, antenna, cable, and attenuation consistent while comparing.
- Use attenuation or reduced gain when a nearby signal pegs the meter.

The narrow white pointer shows only the current reading and moves along the
colored scale as RSSI changes. It does not retain a peak or paint a history
trail. The pointer and seven-LED ladder should move in the same direction as
the numeric value.

## Reading a detected Morse message

When WaveRider recognizes an NFM Morse tone at approximately 450–1,150 Hz on
the selected carrier, it first retains the decode as a candidate. A candidate is not
presented as a callsign or message until at least three recent receptions on
that frequency agree and pass timing/signal quality checks. Once verified, the
left frequency rail temporarily changes to **MESSAGE DETECTED** and shows the
decoded text. The waterfall continues updating beside the message. The overlay
closes after eight seconds, or immediately when the receiver is tuned to
another frequency.

Press Yellow **MSGS** from Live to open a frequency summary. Each row shows a
frequency and its verified-message count. Use Up/Left/**PREV** and
Down/Right/**NEXT** to select a frequency, then Green, Check, or **OPEN** to
view only that frequency's messages. Within a frequency, **PREV** and **NEXT**
browse its observations; **FREQS** returns to the grouped summary and **LIVE**
returns to the receiver.

Red or **CLEAR** on the frequency summary opens a confirmation page. Check or
the center **CLEAR** button permanently removes every verified message and
hidden candidate from both the Wili cache and CM0 storage. Red, Gray, Back, or
**CANCEL** leaves history unchanged. Clearing cannot be undone.

The on-device viewer holds the latest 16 verified observations; the CM0 keeps
up to 100 candidate and verified records in
`/var/lib/freewili-foxhunt/messages.json` and silently restores the latest 16
verified records after a reconnect or reboot.

Morse carries letters but not capitalization, so text is displayed uppercase.
Treat the result as an aid rather than guaranteed transcription: weak or noisy
signals may omit or substitute characters. Recenter the carrier, improve the
antenna signal, or reduce nearby interference if decoding is unreliable. An
identical verified message decoded again inside 30 seconds does not open
another popup, but its repeat count and last-seen time are still updated.
Similar repeated receptions on the same frequency are conservatively grouped;
actual reception counts weight the character consensus, rather than giving a
one-off garble the same vote as repeated text. WaveRider does not use a
dictionary or guess unknown characters. A one-time transmission may therefore
remain an unshown candidate; this is intentional to avoid false callsigns.

## Pocket Alert status

1. From Live, press **Page** or tap the RSSI scale, select **Pocket Alert**, and
   press Check or **Open**.
2. Yellow toggles Pocket Alert on or off.
3. Green lowers the threshold by 1 dB; Blue raises it by 1 dB.
4. Red **Test** runs three 150 ms pulses with 80 ms gaps. The manual Test does
   not wait for an RF threshold crossing.
5. Press Gray, Cancel, or Page to return to Settings; Red returns to Live.

When enabled, WaveRider alerts once when RSSI crosses upward through the chosen
threshold. It will not alert again until RSSI falls at least 3 dB below the
threshold, crosses upward again, and the 30-second cooldown has expired. The
driver uses the physically verified production FW2 v07 Display GPIO35 route.
Users should still confirm the manual Test on their own board revision before
relying on it.

## Receiver status and Refresh

Tap the `SDR LIVE` label to view Receiver Status. If touch input is inconvenient,
press Red **Refresh** to run the same receiver-health checks while restarting
collection. The status page reports:

- CM0 link state;
- SDR streaming state;
- time since the last waterfall row;
- row count and link requests;
- command synchronization.

Press Red **Refresh** when data appears stale. WaveRider reopens the RTL-SDR,
clears the old scale, waits for a newly committed row, and then repaints the
waterfall. If a fault persists, check the SDR's USB connection and power.

## Returning to maintenance mode

Receiver mode uses the CM0 USB controller for the RTL-SDR, so the maintenance
serial port is unavailable at the same time. Use the documented recovery path:

```text
sudo foxhuntctl maintenance --reboot
```

See [Deployment](DEPLOYMENT.md) for installation and maintainer workflows,
[Troubleshooting](TROUBLESHOOTING.md) for recovery, and
[Known limitations](LIMITATIONS.md) before field use.
