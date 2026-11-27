"""Write a simulated session (sim_swing.py) as a pose-glove phone-page log, to test the page's swing analysis
(swing.js) and glove_log.py without the glove.

The log looks like the page's "기록" file: glove frames [phone_ms, seq, glove_t_us, 12 raw int16] at the chosen rate
(gyro 0.07 dps/LSB, so it clips at 2293 dps like the real chips; acc 0.000488 g/LSB), impact clips with the glove
time of the impact arriving ~1.5 s later, a clock fit, and some lost frames. Extra keys for testing: "truth" (impact
times in glove seconds and swing kinds) and "expected" (swing_eye.analyse on the original 400 Hz data at the true impact).

  python3 sim_to_page_log.py OUT.json [--seed 0] [--kinds good,early,decel,good] [--hz 240] [--lose 0.002]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim_swing import make_session  # noqa: E402
from swing_eye import analyse  # noqa: E402

GYRO, ACC = 70e-3, 0.488e-3
KEYS = ("hand_gyro", "hand_acc", "arm_gyro", "arm_acc")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--kinds", default="good,early,decel,good,early,decel")
    ap.add_argument("--hz", type=float, default=240)
    ap.add_argument("--lose", type=float, default=0.002, help="share of frames lost over Bluetooth")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed + 1000)
    d, _ = make_session(a.seed, a.kinds.split(","))
    expected = []
    for (ti, kind), (ta, tp0, tp1) in zip(d["truth"], d["phases"]):
        an = analyse(d, ti)
        expected.append({"t_s": ti, "kind": kind, "top_s": an["top"], "take_s": an["take"],
                         "true_tempo": (0.5 * (tp0 + tp1) - ta) / (ti - 0.5 * (tp0 + tp1)), "true_pause_s": tp1 - tp0,
                         "true_back_s": 0.5 * (tp0 + tp1) - ta, "true_down_s": ti - 0.5 * (tp0 + tp1)}
                        | {k: float(v) for k, v in an["metrics"].items()})
    T = d["t"][-1]
    t_new = np.arange(0, T, 1 / a.hz)
    cols = []
    for k in KEYS:
        for j in range(3):
            cols.append(np.interp(t_new, d["t"], d[k][:, j]))
    X = np.stack(cols, 1)
    raw = np.empty_like(X)
    raw[:, [0, 1, 2, 6, 7, 8]] = X[:, [0, 1, 2, 6, 7, 8]] / GYRO
    raw[:, [3, 4, 5, 9, 10, 11]] = X[:, [3, 4, 5, 9, 10, 11]] / ACC
    raw = np.clip(np.round(raw), -32768, 32767).astype(int)
    t0_us = 123_456_789                                   # glove clock doesn't start at 0
    offset_ms = 50_000.0                                  # phone clock = glove clock + offset + Bluetooth delay
    keep = rng.random(len(t_new)) >= a.lose
    frames = []
    for i in np.flatnonzero(keep):
        t_us = int(t0_us + t_new[i] * 1e6)
        phone = t_us / 1000 + offset_ms + 8 + rng.exponential(6)
        frames.append([round(phone, 1), int(i), t_us] + raw[i].tolist())
    clips = []
    for n, (ti, kind) in enumerate(d["truth"], 1):
        t_us = int(t0_us + (ti + rng.normal(0, 0.0005)) * 1e6)  # the sound clip's impact time, ~0.5 ms error
        arrive = t_us / 1000 + offset_ms + 1500
        clips.append({"kind": "impact", "id": n, "t_us": t_us, "pre": 4000, "total": 16000, "rate": 16000, "peak": 18000,
                      "firstNow": round(arrive - 300, 1), "lastNow": round(arrive, 1), "samples": []})
    log = {"meta": {"page": "sim_to_page_log.py", "seed": a.seed, "hz": a.hz, "units": "as the pose-glove page"},
           "glove": frames, "clips": clips, "motion": [], "pose": [], "cap": [], "status": [], "impacts": [], "events": [], "labels": [],
           "sync": {"note": "phone_ms = glove_ms + b + a * (glove_ms - t0), glove_ms = t_us / 1000", "a": 0.0, "b": offset_ms + 8, "t0": t0_us / 1000},
           "truth": [{"t_s": (t0_us / 1e6) + ti, "kind": kind} for ti, kind in d["truth"]],
           "expected": [e | {"t_s": (t0_us / 1e6) + e["t_s"]} for e in expected]}
    Path(a.out).write_text(json.dumps(log))
    print(f"{a.out}: {len(frames)} frames at {a.hz:g} Hz ({len(t_new) - len(frames)} lost), {len(clips)} swings")


if __name__ == "__main__":
    main()
