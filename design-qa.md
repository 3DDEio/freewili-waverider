# WaveRider design QA

- Source visual truth: `/var/folders/sy/h7xzp1456ys72bj73kg182h40000gn/T/codex-clipboard-07636527-059e-4883-b643-0b64b2ba9705.png`
- Source pixels: 1338 x 966, including a rendered device frame.
- Implementation target: FreeWili 2 stock 480 x 320 dynamic panel.
- CSS size / density normalization: not applicable; this is a native embedded panel.
- State: live RTL-SDR foxhunt screen.
- Implementation screenshot: pending a post-deployment device photo.
- Primary interactions: Lists, Bandwidth, Next, Mark, and Stop/Start are covered by automated action tests; physical-button validation is pending on-device confirmation.

**Findings**

- [P1] A rendered implementation capture is not yet available.
  Evidence: the source mockup is available, but the rebuilt 480 x 320 panel has not yet been photographed.
  Impact: typography, spacing, list density, RSSI-bar placement, and button-label alignment cannot be judged from code alone.
  Fix: deploy to FX0177, capture the live screen straight-on, and compare it with the source in one combined visual.

**Implementation Checklist**

- Deploy the rebuilt panel to FX0177.
- Exercise all five physical buttons and confirm the visible result.
- Capture the live panel at the same state as the source mockup.
- Run a full-view comparison plus focused header, RSSI, list, and button-strip comparisons.
- Iterate until no P0/P1/P2 differences remain.

**Follow-up Polish**

- Tune exact font sizes and x/y offsets after the first real panel capture.

## Comparison history

- Initial pass: blocked before visual comparison because no implementation capture exists yet.

## Final result

blocked
