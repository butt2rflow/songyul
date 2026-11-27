# ArduinoBLE 2.1.0 patches

These patches modify ArduinoBLE, copyright Arduino SA and its contributors. They use the upstream GNU Lesser General Public License, version 2.1 or later. The [LGPL 2.1 text](LICENSE) is included here. Upstream source and copyright notices are available from [ArduinoBLE 2.1.0](https://github.com/arduino-libraries/ArduinoBLE/tree/2.1.0).

- `cordio-rx-buffer.patch` (2026-10-22) increases the Cordio receive buffer to hold the fragments of a full glove notification. Use it for the XIAO receiver.
- `experimental-acl-credits.patch` (2026-10-27) adds ACL credit recovery and diagnostics. It is optional. The glove sketch builds without it.

After installing ArduinoBLE 2.1.0, run from the Songyul repository root. Set `arduino_ble_dir` to the installed library directory containing `src/`.

```sh
arduino_ble_dir=~/Arduino/libraries/ArduinoBLE
patch -d "$arduino_ble_dir" -p1 < third-party/arduino-ble/cordio-rx-buffer.patch
```

The same command with the experimental patch applies the optional changes. If distributing compiled firmware that incorporates ArduinoBLE, follow the upstream license for the linked library and any modifications.
