# FreeWili 2 haptic evidence

This record explains why WaveRider drives Display GPIO35 active-high. The pin
was physically verified on a production FreeWili 2 v07 unit after older public
material incorrectly directed development to GPIO46. This project does not
redistribute the installed application binaries.

## Installed application inventory

The following files were copied read-only from the connected FreeWili 2 Main SD
on 2026-08-09 and analyzed locally:

| Installed app | Size | SHA-256 |
| --- | ---: | --- |
| `/apps/Games/DOOM.UF2` | 610,304 bytes | `a59939dd9ed693551807a88423389c31ed6560c9ea7399a662d8b719d7d527e3` |
| `/apps/Radio/meshtastic.uf2` | 2,167,296 bytes | `2c3ea28e461f03d513020973c934123cd87e725ac142fa6a6c9a75a3001564ba` |

Both files passed UF2 block-magic validation. Doom is an RP2350 RISC-V app;
Meshtastic is an RP2350 Arm Secure app.

## Meshtastic source evidence

The installed Meshtastic image contains the source identifier
`https://github.com/Ytuf/firmware`, the board name `FreeWili 2 (RP2350B)`, and
FreeWili-specific runtime strings. That repository exposes a `freewili-port`
branch at commit `58af2f8557255ce42952fa51e435a272d3ab1a4f`.

In that branch:

- `variants/rp2350/freewili/variant.h` maps `EXT_NOTIFY_OUT` and `BUZZER_PIN`
  to GPIO46 and identifies it as `HAP_MOTOR`.
- `src/platform/extra_variants/freewili/variant.cpp` initializes GPIO46 as an
  output, selects 12 mA drive, and treats HIGH as motor-on.
- The boot check is three 150 ms HIGH pulses with 80 ms LOW gaps.
- Normal button haptics use an 80 ms active-high DC pulse; the source notes that
  the generic tone/PWM path is too weak on this hardware.

The source branch is corroborating evidence from the origin embedded in the
installed image; the repository does not publish a reproducible manifest that
proves the installed UF2 is bit-for-bit derived from that exact commit.

## Doom corroboration

The installed Doom image contains a dedicated PWM haptic driver with runtime
diagnostics for its GPIO, PWM slice/channel, frequency, divisor, maximum duty,
and overlong-drive safety cutoff. Its stripped UF2 does not expose the selected
GPIO as a plain-text constant, so Doom independently proves shipped haptic use
but is not the source of WaveRider's pin assignment.

## Corrected hardware decision

The Meshtastic source pointer was useful for the pulse envelope, but its GPIO46
assignment did not operate the motor on the connected production board. That
result is also consistent with current FreeWili logic-analyzer material, which
uses Main GPIO46 as an analog input rather than a vibration output.

On 2026-08-11 an independent production FW2 v07 bench trace reported the motor
on the **Display CPU's GPIO35**. WaveRider changed only the haptic pin from 46
to 35, keeping the bounded 12 mA drive and nonblocking three-pulse envelope.
The connected FX0177 unit then produced all three physical pulses from the
manual Test action. This establishes the WaveRider driver as:

- Display GPIO35;
- active-high;
- 12 mA pad drive;
- three nonblocking 150 ms pulses separated by 80 ms gaps;
- 30-second alert cooldown and 3 dB fall-and-rise re-arm for battery and
  nuisance protection.

## Connected-unit results and power-rail diagnostic

On 2026-08-09 the connected unit physically produced Meshtastic's three boot
pulses. This proves that the motor is populated and functional on this unit.
WaveRider's earlier Pocket Alert TEST handler was observed over RTT. It received
the red-button event and produced three 150 ms active-high GPIO46 pulses with
80 ms gaps; both the SIO output latch and pad readback followed every high and
low transition, but no physical vibration was felt. This proved the software
waveform was correct while disproving GPIO46 as the motor route on this board.

The same capture showed that WaveRider's audio power zone was off. Because the
Meshtastic startup path initializes the audio-related board path before its
haptic self-test, a bounded diagnostic build declared AUDIO in WaveRider's
application power-zone metadata and kept it awake. The connected-unit TEST
still produced no physical vibration, disproving the audio-zone hypothesis.
WaveRider therefore no longer requests that otherwise-unused rail. The later
GPIO35 physical success confirms that the problem was pin assignment, not an
audio rail or pulse-timing dependency.

Manual TEST uses three 150 ms HIGH intervals and 80 ms LOW gaps, scheduled
through WaveRider's nonblocking pulse state machine. An
earlier blocking sleep loop stopped servicing OneWili for the duration of the
test and physically reproduced a lost SDR/command route on Main v07, so no
haptic action may block the Display event loop.

## End-to-end RF acceptance on FX0177 v07

On 2026-08-11 the recovered KO6FQY beacon was controlled over USB while the
user held the Wili and confirmed each physical result. WaveRider measured about
-64.6 dBFS with the beacon off and -8.4 dBFS keyed at bench distance. With
Pocket Alert enabled at a persisted -40 dBFS threshold:

- manual Test produced exactly three pulses and SDR/CM0 remained live;
- the first off-to-on RF crossing produced exactly three pulses;
- a continuously strong signal produced no additional alert;
- after returning to about -65.0 dBFS, crossing the -43 dBFS re-arm boundary,
  and waiting beyond the 30-second cooldown, the next RF crossing produced
  exactly one additional three-pulse alert;
- disabling Pocket Alert persisted across a CM0 service restart together with
  the -40 dBFS threshold; and
- a complete strong RF crossing while disabled produced no vibration.

This closes the end-to-end Pocket Alert behavior gate for the tested FX0177 v07
unit. Other hardware revisions still need compatibility confirmation.
