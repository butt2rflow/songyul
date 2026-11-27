# R10 Bridge

R10 Bridge is unofficial and is not affiliated with Garmin or E6/TruGolf. It uses the Garmin Golf app's own E6 connection with host `127.0.0.1` and port `2483` when both apps run on the same phone. Follow the Garmin Golf and E6/TruGolf apps' terms.

## Android

Build the APK with `./r10-bridge/android/r10bridge/build.sh` from the repository root. The script needs a JDK, zip, Android SDK Platform 34 and Build Tools 34.0.0. Set `ANDROID_HOME` if the SDK is somewhere other than `/usr/lib/android-sdk`. The build bundles the sibling Songyul phone page and signs locally with a debug key.

1. Install the generated `r10-bridge/android/r10bridge/build/r10bridge.apk` on an Android device (API 26 or later).
2. In R10 Bridge, start the receiver (**수신 켜기**). In Garmin Golf, select the E6 PC connection and set the host and port above. Start a Garmin Golf session.
3. Open the glove page from R10 Bridge in Android Chrome at `http://127.0.0.1:8765/`. Connect the glove and enable **R10 결과 받기**. Each incoming shot is paired with a preceding swing when the timestamps match.

The Android WebSocket and page server use loopback. The shot receiver also listens on the local network. Use a trusted network. Android adds shot JSONL and raw message recordings to the phone's local storage. Review those files before sharing.

## Python receiver

```sh
python3 r10-bridge/r10_e6_server.py --port 2483 --out data/r10
```

For a separate PC on the same trusted network, enter the PC's IP in Garmin Golf. The Python tool writes JSONL and does not host the phone page. Use the Android bridge for live WebSocket pairing.

The bridge source and diagrams here are Songyul's own. See [THIRD_PARTY.md](../THIRD_PARTY.md) for the protocol reference. Songyul bridge code uses [PolyForm Noncommercial 1.0.0](../LICENSE). The flow diagram uses [CC BY-NC-SA 4.0](../LICENSE-CAD-DOCS).
