# Songyul (손결)

a sensor glove that reads your golf swing

![Songyul: the glove electronics next to real data from one swing, hand and forearm rotation and the impact sound from the glove mic](docs/images/hero.png)

**Name.** *Son* means hand and *gyul* means grain or texture.  
**Status.** Early, changes often. Photos show the v1 hardware; the v3 case layout is in `cad/`.

Two IMUs track the hand and forearm. The onboard mic captures impact sound. The phone page shows swing tempo, wrist release and gesture controls.

![Pose overlay on a swing (AI-generated golfer, pose drawn by our pipeline)](docs/images/pose-demo.gif)  
*Demo clip: the golfer is AI-generated; the skeleton is drawn by our pose pipeline. [MP4](docs/images/pose-demo.mp4)*

## What it looks like

| Worn | Parts | Inside |
|---|---|---|
| ![Side view of the worn glove](docs/images/glove-worn-side.png) | ![Hand case and forearm strap laid out](docs/images/glove-parts-laid-out.png) | ![Open forearm case: XIAO, cable and IMU](docs/images/glove-forearm-case-open.png) |
| ![Assembled hand case beside the forearm strap](docs/images/glove-case-and-strap.png) | ![Closed forearm IMU case](docs/images/forearm-imu-case-closed.png) | ![LSM6DSOX breakout next to a ruler](docs/images/forearm-imu-with-ruler.jpg) |
| ![XIAO nRF52840 Sense close-up with leads](docs/images/xiao-closeup.jpg) | ![XIAO, battery and IMU wired together](docs/images/glove-electronics.jpg) | |

## How it is wired

![Wiring from the XIAO to the external IMU, battery and wake button](docs/wiring.svg)

<details><summary>v1 layout and wiring drawings</summary>

![Where each part sits on the hand (v1)](docs/images/layout-v1.png)
![v1 wiring](docs/images/wiring-v1.png)

</details>

## What it measures

**Swing from the hand IMU.** Tempo is backswing time over downswing time; impact shows up on both the gyro and the glove mic.

![A real 7-iron swing from the hand IMU alone](docs/images/real-swing-imu.png)

**Impact sound.** The glove mic sits on the hand, so it keeps headroom where a phone behind the ball clips.

![Anatomy of a range shot recorded by a phone](docs/images/range-shot-anatomy.png)
![Phone mic vs glove mic on the same kind of strike](docs/images/phone-vs-glove-mic.png)
![Good strikes have a sharp high-frequency crack; a fat shot is a dull dip](docs/images/good-vs-fat-strike.png)
![High-frequency energy before the strike: fat vs clean shots](docs/images/fat-vs-clean-energy.png)

**Pose from video** (for comparison with the glove).

![Pose frames through a swing](docs/images/pose-frames.png)
![Shoulder turn, hip turn and head sway from video pose landmarks](docs/images/pose-curves.png)
![Simulated glove readings](docs/images/swing-sim.png)

## Phone page

![Real phone screen recording at an indoor range: right after the swing, glove values (blue) and R10 values (green) pop up over the camera with the impact sound and vibration pictures. Face blurred](docs/images/real-screen.gif)

*A real session, recorded from the phone screen (Korean UI, face blurred). Right after impact the card shows the glove's tempo, wrist release, hinge and hand speed (blue) and the R10's ball speed, launch, path and face (green), with the impact sound and impact vibration below.*

![Hand and forearm rotation for one real swing, with address, top, impact and finish marked and the paired R10 ball speed](docs/images/real-swing-gyro.png)

The phone page and voice commands support English and Korean. Use the **KO / EN** buttons in the settings area to change the language. The three screenshots below use simulated swings and impact audio; the gesture panel in them still shows the older tap mapping.

Tap the back of your gloved hand twice to open club selection. Turn your wrist to choose a club, then tap twice again to confirm. With the club dial closed, four taps start voice listening by default.

| Swing table | Voice and gesture commands | Fat-shot audio |
|---|---|---|
| ![Swing table with club, tempo and wrist release](docs/images/phone-swing-table.png) | ![Voice and gesture command settings](docs/images/phone-voice-gesture.png) | ![Impact waveform and spectrogram with a fat-shot label](docs/images/phone-fat-shot-recorder.png) |

## Where it is going

The glove is the data collector. Next: label real swings with launch-monitor results, train a model, and give a short coaching comment after every shot, later without the launch monitor. See [ROADMAP.md](ROADMAP.md).

## Range setup

![Range setup from above: phone on a floor-level mini tripod in front of the golfer, Garmin R10 about 2 m behind the ball](docs/images/setup-topview.png)

## Quick start

1. **Gather the parts.** Use a Seeed Studio XIAO nRF52840 Sense, an Adafruit LSM6DSOX STEMMA QT breakout (4438), a four-wire STEMMA QT cable, a protected 3.7 V single-cell LiPo (prototype used 350 mAh), an optional normally open 6 × 6 mm button, and a sleeve or strap. For the current detector, mount the XIAO on the hand and the breakout on the forearm. See the [wiring diagram notes](docs/README.md) and [v3 case fit notes](cad/README.md).
2. **Build and flash from source.** Install the Seeed mbed board core and libraries with Arduino CLI. The Linux toolchain uses `adafruit-nrfutil` on your PATH for the build's DFU packaging and for upload. Set `port` to the connected board's serial port.

   ```sh
   seeed=https://files.seeedstudio.com/arduino/package_seeeduino_boards_index.json
   arduino-cli core update-index --additional-urls "$seeed"
   arduino-cli core install Seeeduino:mbed@2.9.3 --additional-urls "$seeed"
   arduino-cli lib install "Seeed Arduino LSM6DS3@2.0.7" "Adafruit LSM6DS@4.7.4" "ArduinoBLE@2.1.0"

   board=Seeeduino:mbed:xiaonRF52840Sense
   port=/dev/ttyACM0
   arduino-cli compile --fqbn "$board" firmware/xiao_ble_glove
   arduino-cli upload --fqbn "$board" --port "$port" firmware/xiao_ble_glove
   ```

   For a USB recorder, compile and flash `firmware/xiao_ble_receiver` on a second XIAO. Apply the [ArduinoBLE receive-buffer patch](third-party/arduino-ble/README.md) before compiling that sketch. For a direct USB bench check, flash `firmware/xiao_usb_stream` on the glove board and follow its power wiring note.

3. **Record a take.** Connect the receiver over USB, wake the glove and use the receiver's port. The recorder saves motion and, with `--mic`, impact audio from the BLE glove or live audio from the USB sketch.

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install -r host/requirements.txt
   python host/stream.py --list
   python host/stream.py /dev/ttyACM0 --seconds 10 --hz 240 --mic --out take.npz
   ```

   To use Bluetooth directly from Android Chrome, open the [phone page](phone/README.md). Reproduce the swing and gesture checks with [synthetic data](analysis/README.md).

## Repository map

| Folder | Contents |
| --- | --- |
| [firmware/](firmware/) | BLE glove, BLE-to-USB receiver, and direct USB sketch |
| [host/](host/) | Recorder, packet decoder, voice commands and optional BLE tools |
| [analysis/](analysis/) | Swing metrics, calibration, log reader and simulated checks |
| [cad/](cad/) | Current OpenSCAD case models and STL exports |
| [docs/](docs/) | Wiring diagram and hardware notes |
| [phone/](phone/) | Web Bluetooth client, swing and gesture detectors, optional camera pose and voice |
| [r10-bridge/](r10-bridge/) | Optional Android bridge and Python shot receiver |
| [third-party/](third-party/) | ArduinoBLE patches and their license |

## Licensing

Songyul is **source-available**. Its noncommercial licenses fall outside the OSI Open Source Definition.

- Songyul code uses [PolyForm Noncommercial 1.0.0](LICENSE).
- The CAD and material in `docs/` use [CC BY-NC-SA 4.0](LICENSE-CAD-DOCS).
- Third-party material keeps its own terms. See [THIRD_PARTY.md](THIRD_PARTY.md).
- [Commercial use requires a separate license](COMMERCIAL.md).

**No outside PRs for now.**
