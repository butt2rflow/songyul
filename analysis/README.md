# Swing and gesture analysis

Use Python 3 and Node.js with native ES modules. Install the host requirements plus SciPy and Matplotlib in your virtual environment.

Run these commands from the repository root.

```sh
python -m pip install -r host/requirements.txt scipy matplotlib
test_dir=$(mktemp -d)
kinds=$(python -c 'print(",".join(["good", "early", "decel"] * 10))')
python analysis/sim_to_page_log.py "$test_dir/swing.json" --kinds "$kinds"
node analysis/test_swing_js.mjs "$test_dir/swing.json"
node analysis/test_gesture_js.mjs "$test_dir/swing.json"
node analysis/test_voice_js.mjs
```

The simulator generates glove frames and impact clips without real recordings. The swing replay compares JavaScript detections against the simulator and the Python analysis. The gesture check exercises synthetic tap, twist, shake, hold and club-selection inputs. The 30-swing replay above can report a false shake during a simulated waggle. The voice test compares the Korean and English matchers in Python and JavaScript and checks locale selection and spoken feedback.

Regenerate the English swing simulation figure from the repository root.

```sh
python analysis/swing_eye.py --figure docs/images/swing-sim.png
```

The swing simulation figure is generated directly from the synthetic sessions.

Regenerate the pose figure from the repository root in a Python 3.12 virtual environment.

```sh
python -m pip install mediapipe==0.10.21 matplotlib
pose_dir=$(mktemp -d)
python analysis/pose_demo.py docs/images/pose-demo.mp4 "$pose_dir"
cp "$pose_dir/pose-curves.png" docs/images/pose-curves.png
```

MediaPipe Pose runs its bundled full model on the frames of the AI-generated golfer video, which already has a pose overlay. The plot uses the newly detected landmarks. Add `--lang ko` and use a Korean-capable font such as Noto Sans CJK KR for Korean labels.

For your own recordings:

- `python analysis/swing_eye.py take.npz` reports swing metrics from an NPZ take.
- `python analysis/glove_log.py swing-glove-session.json --npz` converts a phone session and reports detected swings.
- `calib.py` fits the hinge axes from a wrist alignment routine.

Songyul analysis code uses [PolyForm Noncommercial 1.0.0](../LICENSE).
