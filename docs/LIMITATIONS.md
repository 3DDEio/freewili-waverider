# WaveRider known limitations

This file records current product limits, their user impact, and the intended
direction for improvement. User-visible limitations must be updated here and
summarized in the repository README when they are discovered.

## Live list: 16 frequencies maximum

The native Display app can publish and operate on sixteen entries in the active
list. FreeWili Main v07 provides 32 named app-signal mailbox slots; WaveRider
uses all 32 when sixteen frequency entries and the receiver/control fields are
present.

**User impact:** The saved library can hold 100 unique values, but no more than
sixteen can carry a `LIVE` badge or appear in the fast hunt rotation at once.

**Current workaround:** Keep additional values in Saved and toggle only the
frequencies needed for the current hunt into Live.

**Future direction:** A packed or paged list protocol can remove the mailbox
slot limit without replacing stock Main or Display firmware.

## Saved library: 100 frequencies maximum

The persistent library is deliberately bounded to keep validation, paging,
backup, and recovery predictable on the CM0.

**User impact:** The 101st unique saved value is rejected until another saved
frequency is deleted. This does not change the separate 16-entry Live limit.

## Received audio is not available

FreeWili's NAU88C10 codec, onboard speaker, and headphone output are usable,
but the SDR demodulator runs on CM0 Linux while audio DMA belongs to the Display
processor. The low-rate app-signal mailbox cannot carry 16 kHz PCM safely.

**User impact:** WaveRider currently provides visual waterfall/RSSI hunting
only. It does not play NFM beacon audio through the speaker or headphone jack.
The Settings screen shows Audio Monitor and Volume as locked/unavailable so the
planned control surface is discoverable without implying that sound is active.

**Future direction:** Add a bounded high-rate PCM bridge with drop-oldest
buffering, mute, volume, squelch, and Speaker/Headphones/Both routing. Audio
must never slow the waterfall, controls, or recovery path.

## Morse decoding is tone-specific and remains beta

WaveRider's CM0 path can now demodulate phase changes from the selected NFM
carrier, search approximately 450–1,150 Hz for an audio tone, and decode its
on/off timing as Morse. This is decoded-data processing and does not provide speaker
or headphone audio.

**User impact:** A clean, centered, repeating beacon within that tone range should produce a
`MESSAGE DETECTED` overlay after at least three agreeing receptions. One-time
or disagreeing receptions are retained as candidates but deliberately withheld
from the viewer to reduce false callsigns. Weak signals, multipath,
interference, overlapping transmitters, non-FM modulation, or a substantially
different tone pitch can still produce missing or incorrect characters. Morse
does not encode uppercase vs. lowercase, so WaveRider displays letters in
uppercase. A stored decode is limited to 79 printable ASCII characters. The
popup closes after eight seconds; an identical verified decode inside 30
seconds suppresses only the extra popup, not the evidence update. The CM0
retains 100 candidate/verified records while the native MSGS viewer exposes the
latest 16 verified messages, grouped by frequency. Confirmed Clear removes all
100 retained records, including candidates that were never visible, and cannot
be undone. This is conservative voting, not dictionary
correction, and it cannot guarantee the transmitted text.

**Current validation:** synthetic offset-tuned RTL IQ recovers `KO6FQY` and an
unmodulated carrier is rejected. Connected over-the-air consensus produced
100 percent displayed character accuracy for two distinct 13 WPM / 800 Hz
payloads: `KO6FQY JOIN NORCALCYBER.IO! KO6FQY` at 147.500 MHz and
`KO6FQY -- DECOY DECOY -- KO6FQY` at 144.300 MHz. This proves the core field
decode and frequency labeling on the tested hardware. The larger efficacy
sample, beacon-off false-positive duration, and physical history Clear check
remain before the complete Morse gate closes.

The decoder can be persistently disabled from Settings. Disabling it stops new
Morse processing but deliberately retains existing verified and candidate
history until the user confirms Clear in MSGS.

## RSSI is relative dBFS

The displayed number is not calibrated dBm. RTL-SDR tuner variance, selected
gain, antenna, feed line, filters, and external attenuation all affect it.

**User impact:** Compare readings only while the RF setup and gain remain
consistent. A less-negative value means a stronger received signal.

## Pocket Alert remains threshold-based

Pocket Alert reacts to selected-frequency RSSI crossing a relative dBFS
threshold. It does not wait for or depend on a successful Morse decode, and
nearby interference inside the selected span can also cross the threshold. The design
uses three short motor pulses, a fixed
30-second cooldown, and a 3 dB fall-and-rise re-arm requirement to reduce
battery drain and nuisance vibration. A manual Test action deliberately
bypasses the cooldown.

## Pocket Alert board-revision coverage is limited

WaveRider drives the physically verified production FW2 v07 motor route:
Display GPIO35, active-high at 12 mA, using three 150 ms pulses separated by
80 ms. The connected FX0177 unit produced all three pulses from the manual Test
on 2026-08-11. Older public material and a Meshtastic source branch name
GPIO46; that route toggled electrically but did not move this board's motor.
See `docs/HAPTIC_EVIDENCE.md`.

**User impact:** GPIO35 is proven on the connected production v07 unit, but
other board revisions have not been physically surveyed. Run the manual Test
before relying on Pocket Alert. RSSI, waterfall, and LED feedback remain the
authoritative fallbacks if a different revision does not respond.

## Waterfall resolution is optimized for field hunting

Each displayed row contains twelve measured RF bins transported through Main's
bounded mailbox. CM0 applies a small local power smoother and Display
interpolates those measurements over 324 pixels to avoid block-shaped carrier
artifacts.

**User impact:** The waterfall is useful for locating a carrier and observing
relative signal shape, but it is not a high-resolution laboratory spectrum
analyzer. Real off-frequency signals and interference remain offset; WaveRider
does not fabricate a symmetric trace around center.

## Linux and SDR startup take time

Selecting WaveRider powers and releases CM0, starts Linux, starts the service,
and opens the RTL-SDR. The duration varies between warm and cold launches.

**User impact:** The live waterfall may not appear immediately. Use the staged
startup page, tap `SDR LIVE` for the detailed receiver page, or press Red
**Refresh** to run a new health check. Status includes the CM0 link, SDR stream,
last-row age, and command synchronization. A stale receiver replaces the
waterfall with a plain-language attention page and flashes all seven top LEDs
yellow.

## Receiver USB and maintenance serial are mutually exclusive

The tested CM0 exposes one USB controller. Receiver mode routes it to the
Linux USB Host socket for the RTL-SDR; maintenance mode routes it to the serial
gadget.

**User impact:** The CM0 serial port disappears in receiver mode. A routed host
shell also suppresses live Display acknowledgements on tested v07 firmware, so
maintenance sessions must detach before judging the waterfall or buttons.

## Main bridge recovery is bounded

WaveRider distinguishes a missing app signal during ordinary Linux startup
from a broken Main-to-Display transport. After eight consecutive transport
failures, it reopens the local OneWili connection after three seconds. If the
transport is still unavailable after fifteen seconds, it makes one Main CPU
software-reset request for that recovery episode. The CM0, Linux, SDR stream,
saved frequencies, and device settings are not reset.

**User impact:** Local parser and ordinary post-disconnect failures can recover
without a full power cycle. A deeply wedged Main route cannot carry the reset
request that would repair it. WaveRider replaces the indefinite waiting screen
with **Main Bridge Locked** and directs the user to hold Home, then choose
Hardware → Settings → Software Reset. A full power cycle is the fallback.
Recovery is only active while the WaveRider native app is on screen; it will
not reset Main while the user is intentionally working in Linux Terminal.

## Tested hardware scope is narrow

Connected validation currently covers FreeWili 2 FX0177 with v07 firmware and
an RTL2838/R820T receiver.

**User impact:** Other RTL2832U-compatible receivers are expected to work but
remain beta until added to the connected-device test matrix.

## Exact New editor uses 1 kHz minimum resolution

The on-device editor covers 24 MHz through 1.766 GHz using seven integer-kHz
digit positions. Touch input replaces the selected digit and D-pad Left/Right
moves back to correct any position.

**User impact:** Frequencies requiring sub-kilohertz entry cannot currently be
created from the device UI. Duplicate frequencies and values outside the tuner
range are rejected.

## Custom text requires maintenance mode

The live device editor creates an automatic label such as `New 147.495`.

**User impact:** Custom list names and descriptive frequency labels are edited
through `foxhuntctl lists` while the maintenance console is available.

## Receive-only safety boundary

WaveRider controls only an RTL-SDR receive path. It contains no transmit or
radio-keying capability.
## Front status LED in Pocket Alert

WaveRider dims its seven top RGB LEDs in Pocket Alert mode, but it does not
switch off the separate front status LED. Current FreeWili 2 firmware exposes
that indicator only inside a complete Main power-mask operation. Rebuilding
that mask from a live status snapshot is unsafe because transient or
device-managed USB-hub and CM0 bits may be absent; sending the incomplete mask
can interrupt the RTL-SDR or CM0 route. A dedicated front-LED control from the
device firmware is required before WaveRider can safely suppress it.
