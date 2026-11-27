# Third-party notices

## Included

[third-party/arduino-ble/](third-party/arduino-ble/) contains two patches against ArduinoBLE 2.1.0 and a copy of the upstream LGPL 2.1 text. The patches use LGPL-2.1-or-later, as do the affected upstream files. See the [patch notice and upstream source link](third-party/arduino-ble/README.md).

The [PolyForm Project](https://github.com/polyformproject/polyform-licenses/tree/1.0.0) license text and [Creative Commons legal code](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.txt) are reproduced in full.

## External dependencies and references

| Item | Use and upstream terms |
| --- | --- |
| [Seeed nRF52 mbed board core](https://github.com/Seeed-Studio/ArduinoCore-mbed) | XIAO build, board definitions, Wire, SPI, PDM and bundled components. See upstream file notices, including Arduino LGPL, Mbed Apache 2.0 and Nordic terms. |
| [ArduinoBLE](https://github.com/arduino-libraries/ArduinoBLE/tree/2.1.0) | BLE peripheral and receiver library. LGPL-2.1-or-later. |
| [Seeed Arduino LSM6DS3](https://github.com/Seeed-Studio/Seeed_Arduino_LSM6DS3) | Onboard IMU. MIT, with upstream SparkFun notices. |
| [Adafruit LSM6DS](https://github.com/adafruit/Adafruit_LSM6DS) | External IMU. BSD 3-Clause. |
| [Adafruit BusIO](https://github.com/adafruit/Adafruit_BusIO) and [Adafruit Unified Sensor](https://github.com/adafruit/Adafruit_Sensor) | Driver dependencies. MIT and Apache 2.0, respectively. |
| [Arduino CLI](https://github.com/arduino/arduino-cli) and [Adafruit nRF Util](https://github.com/adafruit/Adafruit_nRF52_nrfutil) | Firmware build and upload tooling. GPL-3.0 and upstream Nordic/Adafruit license terms, respectively. |
| [pySerial](https://github.com/pyserial/pyserial), [NumPy](https://github.com/numpy/numpy), [SciPy](https://github.com/scipy/scipy), [PyYAML](https://github.com/yaml/pyyaml), [Matplotlib](https://matplotlib.org/stable/project/license.html) | Host and analysis dependencies. BSD-3-Clause, BSD-3-Clause, BSD-3-Clause, MIT and Matplotlib's PSF-based license, respectively. |
| [Bleak](https://github.com/hbldh/bleak) | Optional computer-side BLE diagnostics. MIT. |
| [Transformers](https://github.com/huggingface/transformers), [PyTorch](https://github.com/pytorch/pytorch), and [Whisper-small](https://huggingface.co/openai/whisper-small) | Optional local transcription. Apache 2.0, BSD-3-Clause and Apache 2.0, respectively, per their upstream repositories or model card. |
| [MediaPipe Tasks Vision](https://github.com/google-ai-edge/mediapipe) and [Pose Landmarker model](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker#models) | Optional camera pose. The browser loads the Apache 2.0 runtime via jsDelivr and downloads the model from Google's model host. See upstream model terms. Runtime and model files stay upstream. |
| [Android SDK](https://developer.android.com/studio/terms) and [OpenJDK](https://openjdk.org/legal/gplv2+ce.html) | External Android platform and build tools. See SDK terms and OpenJDK GPL-2.0 with Classpath Exception. |
| [gsp-r10-adapter](https://github.com/mholow/gsp-r10-adapter) | MIT-licensed interoperability reference consulted for TCP message names and sequence. Songyul implements its own receiver in Java and Python. |
| [Web Bluetooth](https://webbluetoothcg.github.io/web-bluetooth/), [Web Speech](https://webaudio.github.io/web-speech-api/), and [RFC 6455](https://www.rfc-editor.org/rfc/rfc6455) | Browser APIs and WebSocket protocol reference. The browser provides speech recognition. |
