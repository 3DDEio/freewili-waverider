# FW2 v07 quiet/dark Display patch

This is a version-locked maintenance path for the connected FX0177 Display
firmware. It is not a generic FreeWili firmware patch, a WaveRider dependency,
or part of the WaveRider installer. Installing or launching WaveRider must never
apply it automatically. It is an independent, opt-in device modification for
owners who explicitly want different stock boot behavior.

## Evidence

The verified stock Display UF2 has SHA256:

```text
0d49cdd3ebf4e0068c283da2bd6d141a2cd76f4f1c78ddc3ac6422cfb6a0bdc9
```

Read-only runtime tracing established:

- the boot voice call is guarded by effective `sndsys`, which remained `1`
  after the failed settings-file experiment;
- the settings constructor writes factory `sndsys=1` and `lshowdef=10`, but a
  first patch at those constructor stores failed cold-boot acceptance because
  later startup code overwrote both values;
- startup applies that value to the light-show object, whose 16-pixel buffer is
  streamed through PIO0 to Display GPIO21;
- a temporary RAM-only change from light-show `10` to `0` kept all 48 RGB bytes
  at zero while the stock firmware continued running.

V2 patched the settings-application call and the final sound effect point. Its
cold-boot test proved the sound suppression but showed the LED animation starts
earlier, from the live light-show object's own constructor. V3 adds that exact
constructor site:

| Address | Stock | Patched | Effect |
|---|---:|---:|---|
| `0x10000694` | `d4f84c14` | `002100bf` | pass selector `0` immediately before stock light-show activation |
| `0x100028cc` | `0a23` | `0023` | initialize the live light-show object selector to `0` instead of `10` |
| `0x100075b2` | `d0d0` | `d0e7` | always branch over startup voice sound ID 27 |

## Build the candidate

The source UF2 is a locally recovered stock backup and is not distributed by
this repository:

```shell
python3 tools/fw2_patch_display_startup.py \
  /path/to/verified/FW2Display.uf2 \
  build/maintenance/FW2Display-v07-quiet-dark-v3.uf2 \
  --raw-dir build/maintenance/quiet-dark-v3-sectors
```

The patcher refuses every other input hash, verifies both original
instructions, validates all UF2 blocks before and after modification, refuses
to overwrite an existing output unless explicitly requested, and writes an
audit JSON sidecar.

On the connected FX0177 unit, both v2 target sectors first matched their exact
regions in the full-flash backup. Independent post-write read-back matched:

- sector `0x000000`: `fbe3524c9d97a29142609d48f91b90ecd8b87109bcc9a21efe4e3915e4ba27ba`
- sector `0x002000`: `59a414d75758689150c09e221bc9356062d85393dffeaf0b7afe9a9a7d67f290`
- sector `0x007000`: `56fedc4b6234759dda2f5780d8d524da48572a31345190deac96c0ce0b54ab79`

The ineffective v1 constructor sector at `0x005000` was simultaneously
restored to stock SHA256
`ad0267e724f10ed871bc89b2cafec824a6bf6b0790037ffa5dce5afb898f2347`.

## Recovery and acceptance gate

Retain both the verified stock UF2 and the full 16 MiB flash image before any
deployment. If the Display fails to boot or any unrelated function regresses,
restore the stock UF2 through the existing firmware-recovery path.

The connected V3 candidate passed a complete physical cold boot:

1. no stock RGB sweep/light show;
2. no spoken **Free Wili** clip;
3. normal application operation remains available, including app-controlled
   LEDs.
