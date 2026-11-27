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

Regenerate the English figures from the repository root.

```sh
python analysis/plot_pose_curves.py docs/images/pose-curves.png
python analysis/swing_eye.py --figure docs/images/swing-sim.png
```

The swing simulation figure is generated directly from the synthetic sessions.

For your own recordings:

- `python analysis/swing_eye.py take.npz` reports swing metrics from an NPZ take.
- `python analysis/glove_log.py swing-glove-session.json --npz` converts a phone session and reports detected swings.
- `calib.py` fits the hinge axes from a wrist alignment routine.

Songyul analysis code uses [PolyForm Noncommercial 1.0.0](../LICENSE).
