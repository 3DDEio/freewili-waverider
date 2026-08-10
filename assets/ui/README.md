# WaveRider UI assets

`RSSISCL.FWI` is a 264 x 10 RGB565 image used as the continuous RSSI range.
It avoids the rounded ends and gaps imposed by native bargraph controls.

Rebuild it with:

```text
python3 tools/build_rssi_scale.py
```

Running `deploy/fw2_asset_upload.py --port PORT` uploads this asset together
with the WaveRider splash to the Main SD card.
