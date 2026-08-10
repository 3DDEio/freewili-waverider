# WaveRider splash assets

`WAVERIDR.FWI` is the 480 x 320 RGB565 startup image read by FreeWili Main
firmware. `waverider-splash-480x320.png` is its reviewable source, while
`waverider-splash-source.png` preserves the full generated artwork.

Rebuild the native image from any replacement PNG or JPEG:

```text
python3 -m pip install 'freewili>=0.0.51,<1'
python3 tools/build_splash.py assets/splash/waverider-splash-source.png
```

Install and preview it over the FreeWili **Main** USB serial port:

```text
python3 deploy/fw2_asset_upload.py --port /dev/cu.usbmodemFX01771 --show
```

The helper compensates for the FW2 v07 Files submenu being nested under
Hardware. It writes `1:/images/WAVERIDR.FWI`; it does not replace device
firmware or either SD-card image.

## Generation brief

Use case: logo-brand. Create an original 480 x 320 embedded-device startup
splash with a powerful, friendly blue whale surfing a single ocean wave whose
curling crest becomes a clean audio waveform/radio signal. Use a deep midnight
navy background, bold minimal vector-like shapes, bright cyan, turquoise,
white, and one warm yellow accent. Center the mark in the upper two-thirds with
the exact word `WaveRider` centered once below it. Keep generous safe margins,
high contrast, no device frame, no watermark, no photorealism, and no tiny
details.
