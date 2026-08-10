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

Cold Linux startup can take longer than a warm relaunch. The screen remains
interactive and the list can be browsed while WaveRider waits.

## Live controls

| Button | Action |
| --- | --- |
| Gray | Open Lists frequency management |
| Yellow | Open Audio status and future controls |
| Green | Tune the next frequency |
| Blue | Tune the previous frequency |
| Red | Refresh receiver health and restart SDR collection |

The D-pad browses and immediately tunes the list. Check also applies the
highlighted entry.

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

## Pocket Alert status

Pocket Alert is not available in this release. The connected FX0177 did not
vibrate during a verified GPIO diagnostic, and no authoritative FreeWili motor
driver has been published.

1. From Live, press **Page** or tap the RSSI scale.
2. WaveRider reports **UNAVAILABLE** and explains that the motor-control path
   is awaiting a FreeWili specification.
3. Red **Info** opens the bounded pin probe. Left/Right selects GPIO31, 36, 44,
   or 46; Green or Red applies a 350 ms weak pull-up, a floating gap, and a
   350 ms weak pull-down before restoring the pin. It never enables output.
4. Press Gray, Cancel, or Page to return.

The threshold, three-pulse pattern, 30-second cooldown, and 3 dB re-arm design
remain in the source but cannot drive hardware in the default build.

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
