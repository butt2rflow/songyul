# Firmware

| Sketch | Role |
| --- | --- |
| `xiao_ble_glove` | Two IMUs and PDM audio. Advertises as `SensorGlove`. The board's USB port is for flashing and diagnostics. |
| `xiao_ble_receiver` | Receives glove notifications and emits framed packets over USB serial for `host/stream.py`. |
| `xiao_usb_stream` | Direct USB capture of IMU and live mic data. This sketch does not drive D10. Power the external breakout from 3V3 for this bench configuration. |

Build each sketch as a separate Arduino project using the Seeed mbed core for the XIAO nRF52840 Sense. See the [quick start](../README.md#quick-start) and [pin notes](../docs/README.md). Keep the three `proto.h` copies in sync with `python3 host/check_proto.py`.

Songyul firmware source uses [PolyForm Noncommercial 1.0.0](../LICENSE). The [external dependencies](../THIRD_PARTY.md) retain their licenses.
