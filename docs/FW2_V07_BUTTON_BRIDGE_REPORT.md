# FW2 v07 CM0 button-bridge report

## Affected configuration

- FreeWili 2 FX0177
- Main firmware: FW2 v07
- CM0 Linux, stock `fwcm0-bridge.service`
- WaveRider using `/run/fwcm0-bridge.sock` and the generated OneWili API

## Reproduction

1. Open the CM0 OneWili console through the stock bridge.
2. Create the dynamic panel with its native panel menu enabled.
3. Enable the documented button event stream with `g\\o 33`.
4. Press and release Gray, Yellow, Green, Blue, and Red.
5. Read the synchronous state with `g\\u` before, during, and after a press.

## Observed

- `g\\o 100` returns `Ok`.
- No unsolicited `button` event frame is emitted.
- Raw `g\\u` response frames contain no five-byte button payload.
- A firmware-injected Green press/release does not change `g\\u`.
- CM0 Linux exposes no FreeWili button device under `/dev/input`.
- The installed `/opt/onewili/cm0/README.md` states that the CM0 bridge reaches
  MAIN's `fwMenuMain` only.
- FreeWili's official host examples default button reads and button events to
  the Display processor, which the installed CM0 bridge does not expose.

## Requested firmware capability

### Completed local retest

WaveRider now creates every panel with its native menu enabled while retaining
its own styled button labels. On connected FX0177 hardware, D-pad navigation
moves the Display-owned list highlight, but Green, Check, and the five context
buttons produce no CM0 event and do not change the tuned frequency. Raw Main
capture with `h\\a\\e 1` showed only mirrored GUI command traffic. The generated
CM0 API exposes a setter for selected list items but no getter, so WaveRider
cannot infer the Display-owned highlight after it moves.

The documented Main-level Event Host Streaming gate (`h\\a\\e`) is not part of
the CM0 Display channel: it receives no acknowledgement when sent through that
transport and has therefore been removed from WaveRider. The consumer processes
every queued state in order, so a press cannot be overwritten by its queued
release before the render loop samples input. The physical event path has now
been retested with a healthy Display bridge and remains absent; the firmware
request below is the supported next step.

### Fallback request

Please expose one of the following through the CM0 bridge:

1. a Display-processor OneWili channel; or
2. a MAIN-side relay that returns the five physical button states and forwards
   their change events.

WaveRider's event consumer already accepts `button` and `*button` frames, maps
the five rising edges in Gray, Yellow, Green, Blue, Red order, and preserves
multiple edges in wire order. No product logic change should be required once
the bridge supplies either state or event data.

## WaveRider native workaround

WaveRider no longer waits on a firmware relay. Its loadable Display app reads
the same supported `uartkbd` event queue used by WiliBSP keyboard examples and
exchanges sequence-numbered commands with CM0 through Main's existing
app-signal service. The app targets SRAM, installs under `/apps/waverider`, and
does not replace stock firmware. Agent-injected Green has been proven on the
connected display path; the release gate remains a physical Green/Check retune
with the CM0 SDR service detached from the maintenance shell.
