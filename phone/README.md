# Phone glove page

Use Android Chrome with Web Bluetooth. Open the page at a secure origin (HTTPS, or loopback on the phone). For local development on the device that runs the browser:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory phone
```

Open `http://127.0.0.1:8765/` on that device. For a separate phone, serve the files over HTTPS or use the [R10 Bridge's Android build](../r10-bridge/README.md) to serve them on the phone. Tap **Connect sensor glove** (**센서 장갑 연결**) to select `SensorGlove`.

The page, voice commands and spoken feedback support English and Korean. The first visit uses Korean when the browser language starts with `ko`, and English otherwise. Select **KO / EN** in the settings area to save a preference. Try “seven iron, half swing”, “last one was fat”, or “7번 하프”. The phone uses the same command lists as the Python host.

Hold the gloved hand still for about a second, then tap the back of it twice to open club selection. Turn your wrist to step through the clubs and tap twice again to confirm. With club selection closed, four taps start Chrome voice listening by default. Pause briefly after the last tap and wait for listening to start before speaking. You can change the four-tap action or turn off tap beeps and vibration in **Gesture commands** (**손짓 명령**).

Camera pose loads MediaPipe and its model when you start the camera. Chrome voice recognition can use a network service. The BLE recorder, swing detector, and gesture detector can run without either feature. Enable **Receive R10 shots** (**R10 결과 받기**) to connect to a running bridge.

Songyul page code uses [PolyForm Noncommercial 1.0.0](../LICENSE). See [THIRD_PARTY.md](../THIRD_PARTY.md) for browser dependencies.
