# Quiet and dark stock startup

This is an independent, opt-in device-maintenance effort. It is not required by
WaveRider and is never applied by the WaveRider installer or launcher.

WaveRider does not own the LED animation or spoken **Free Wili** clip that can
run before the app opens. Those effects execute in the stock Display firmware.

## FW2 v07: version-locked startup patch deployed

The installed v07 firmware contains text and save logic for `sndvol`, `sndsys`,
and `lshowdef`, but does not expose Display Setup in the on-device menu. Its
FTDI endpoint is the FPGA high-speed interface rather than a Display console.

An earlier maintenance experiment treated `0x1037f000..0x103fefff` as a 512 KiB
LittleFS settings volume. It made a complete rollback backup, wrote only one
changed 4 KiB sector, read the sector back byte-for-byte, remounted the image,
and verified this content:

```text
sndvol=0
sndsys=0
lshowdef=0
```

That storage verification was real, but it did not prove startup behavior. The
subsequent full power-cycle test failed: the LEDs and voice remained. A
read-only runtime inspection then found effective `sndsys=1` and the compiled
factory settings in RAM. Therefore the installed v07 build does not consume
that presumed settings file during cold boot.

`tools/fw2_set_night_defaults.py` now refuses `--method v07-debug`; it must not
be used to write another guessed flash location. Preserve these rollback files:

- the stock Display UF2;
- the full 16 MiB Display flash image;
- every pre-experiment sector/volume backup and checksum.

Read-only tracing subsequently found the compiled defaults and both final
effect points. A first constructor-default patch failed physical acceptance and
was restored to stock. V2 changed the lightshow application argument and forced
the existing sound guard to skip the boot voice call. Its physical test proved
the voice suppression, but LEDs remained because their live object initializes
earlier. A boot watchpoint located that separate selector-10 constructor; V3
changes it to zero. `tools/fw2_patch_display_startup.py` refuses any Display
UF2 except the verified FX0177 v07 stock hash. Every deployed sector was
independently read back successfully. Stock-UF2 and full-flash recovery remain
available. The final V3 physical cold-boot test passed: the stock animation and
voice were both absent. See `docs/FW2_V07_STARTUP_PATCH.md` for exact hashes.

## First-generation FreeWili only

Older first-generation hardware exposes the stock Display Settings serial
console. The helper verifies every menu before changing values and then selects
**Save Settings as Startup**:

```shell
python3 tools/fw2_set_night_defaults.py \
  --method legacy-console \
  --port /dev/cu.usbserial-FX0177
```

This legacy route is not applicable to FW2 v07.
