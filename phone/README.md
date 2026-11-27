# Phone glove page

Use Android Chrome with Web Bluetooth. Open the page at a secure origin (HTTPS, or loopback on the phone). For local development on the device that runs the browser:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory phone
```

Open `http://127.0.0.1:8765/` on that device. For a separate phone, serve the files over HTTPS or use the [R10 Bridge's Android build](../r10-bridge/README.md) to serve them on the phone. Tap **센서 장갑 연결** to select `SensorGlove`. The page has Korean controls and uses the same Korean command examples as the Python host.

Camera pose loads MediaPipe and its model when you start the camera. Chrome voice recognition can use a network service. The BLE recorder, swing detector, and gesture detector can run without either feature. Enabling **R10 결과 받기** connects to a running bridge.

Songyul page code uses [PolyForm Noncommercial 1.0.0](../LICENSE). See [THIRD_PARTY.md](../THIRD_PARTY.md) for browser dependencies.
