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

**Future direction:** Add a bounded high-rate PCM bridge with drop-oldest
buffering, mute, volume, squelch, and Speaker/Headphones/Both routing. Audio
must never slow the waterfall, controls, or recovery path.

## RSSI is relative dBFS

The displayed number is not calibrated dBm. RTL-SDR tuner variance, selected
gain, antenna, feed line, filters, and external attenuation all affect it.

**User impact:** Compare readings only while the RF setup and gain remain
consistent. A less-negative value means a stronger received signal.

## Planned Pocket Alert is threshold-based, not signal identification

The planned Pocket Alert reacts to selected-frequency RSSI crossing a relative dBFS
threshold. It does not demodulate or identify a transmitter, and nearby
interference inside the selected span can also cross the threshold. Hardware
output is disabled. The design uses three short motor pulses, a fixed
30-second cooldown, and a 3 dB fall-and-rise re-arm requirement to reduce
battery drain and nuisance vibration. A manual Test action deliberately
bypasses the cooldown.

## Pocket Alert motor output is disabled

The current FreeWili 2 board-support library has no authoritative haptic
driver. Its secondary pin inventory lists a motor on Display GPIO46 and marks
the driver `TODO`, while current FreeWili 2 logic-analyzer documentation also
assigns GPIO46 to its analog-input bank. Connected diagnostics verified every
requested GPIO46 high/low transition at the MCU pad, but the motor never moved.
That result rules out WaveRider's pulse sequencer without proving that GPIO46
is a motor control on this board revision.

**User impact:** WaveRider never enables output drive on an unverified haptic
pin. Its explicit Info diagnostic can briefly apply only weak internal pulls
to GPIO31, 36, 44, or 46, restoring the exact prior mux/pad state after each
350 ms touch. The complete connected scan produced no response (GPIO31 was
repeated; GPIO36/44/46 were tested once). Pocket Alert reports that the hardware path is unavailable until FreeWili confirms the
processor/pin, active level, required waveform, and any power gate. Visual RSSI,
waterfall, and LED feedback continue to operate normally.

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
