"""Load a pose-glove phone-page log ("기록" -> swing-glove-*.json) and analyse its swings in Python.

  python3 glove_log.py LOG.json [more.json ...] [--out DIR] [--npz]

Per log it writes DIR/<log name>/summary.md (what is in the file: rate, lost frames, battery, clips, camera,
labels), swings.csv (swing_eye.analyse per swing, next to the page's own numbers when the log has them) and
swings.png (hand and forearm rate + wrist hinge per swing, with takeaway / top / impact marked). --npz also saves
take.npz in the host/stream.py layout, so the older tools (swing_eye.py take.npz, calib.py) read it.

As a library:
  from glove_log import load, to_stream
  L = load("swing-glove-....json")       # frames in dps / g, glove seconds, clips, pose, sync, labels...
  d = to_stream(L)                       # uniform 400 Hz dict for swing_eye.find_swings / analyse (with clip_t)

Handles every page version so far: logs before 2026-10-24 have no "sync" (the glove->phone clock is fitted here the
same way as the page's ClockFit), no camera capture times and no motion clips; "impacts", "events", "labels" and
"swings" come in later versions.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from swing_eye import FS, analyse, axis_rate, find_swings  # noqa: E402

GYRO_DPS, ACC_G, SAT_DPS = 70e-3, 0.488e-3, 2293
ROOT = Path(__file__).resolve().parent.parent


def fit_clock(phone_ms, glove_ms, win=2000.0):
    """Glove -> phone clock from packet arrivals (the page's ClockFit): Bluetooth only ever delays, so the fastest
    arrival per 2 s window traces the true offset; Theil-Sen slope, 25th-percentile intercept."""
    off = phone_ms - glove_ms
    k = np.floor((glove_ms - glove_ms[0]) / win).astype(int)
    pts = []
    for w in np.unique(k):
        i = np.flatnonzero(k == w); j = i[np.argmin(off[i])]
        pts.append((glove_ms[j], off[j]))
    x, y = np.array(pts).T
    if len(x) >= 4:
        sl = [(y[b] - y[a]) / (x[b] - x[a]) for a in range(len(x)) for b in range(a + 1, len(x)) if x[b] != x[a]]
        a = float(np.clip(np.median(sl), -150e-6, 150e-6))
    else:
        a = 0.0
    t0 = float(glove_ms[0])
    r = np.sort(y - a * (x - t0))
    return {"a": a, "b": float(r[int(0.25 * (len(r) - 1))]), "t0": t0, "fitted_here": True}


def load(path):
    path = Path(path)
    d = json.loads(path.read_text())
    g = np.asarray(d["glove"], dtype=float)
    L = {"path": str(path), "name": path.stem, "meta": d.get("meta", {}), "page": d.get("meta", {}).get("page", "before 2026-10-24")}
    L["phone_ms"], L["seq"], t_us = g[:, 0], g[:, 1].astype(np.int64), g[:, 2]
    L["t"] = t_us / 1e6
    raw = g[:, 3:15]
    L["hand_gyro"], L["hand_acc"] = raw[:, 0:3] * GYRO_DPS, raw[:, 3:6] * ACC_G
    L["arm_gyro"], L["arm_acc"] = raw[:, 6:9] * GYRO_DPS, raw[:, 9:12] * ACC_G
    L["lost"] = int(np.clip(np.diff(L["seq"]) - 1, 0, None).sum()) if len(g) > 1 else 0
    L["sync"] = dict(d["sync"], fitted_here=False) if d.get("sync") else fit_clock(L["phone_ms"], t_us / 1000)
    s = L["sync"]
    L["to_phone"] = lambda t_s: t_s * 1000 + s["b"] + s["a"] * (t_s * 1000 - s["t0"])
    L["clips"] = [{"kind": c["kind"], "id": c["id"], "t": c["t_us"] / 1e6, "rate": c["rate"], "pre": c["pre"], "peak": c.get("peak"),
                   "arrived_ms": c.get("lastNow"), "audio": np.asarray(c.get("samples", []), dtype=np.int16)} for c in d.get("clips", [])]
    L["motion"] = [{"id": m["id"], "t": np.asarray(m["t"]) / 1e6, "impact_frame": m.get("impactFrame"), "rate": m.get("rate"),
                    "gyro": np.asarray(m["g"], dtype=float).reshape(-1, 6) * GYRO_DPS} for m in d.get("motion", [])]
    pose = d.get("pose", [])
    L["pose_ms"] = np.array([p[0] for p in pose]) if pose else np.zeros(0)
    L["pose"] = [np.asarray(p[1:], dtype=float).reshape(33, 3) if len(p) > 1 else None for p in pose]
    L["cap_ms"] = np.asarray(d.get("cap", []), dtype=float)
    for k in ("impacts", "events", "labels", "swings", "status"):
        L[k] = d.get(k, [])
    for k in ("truth", "expected"):        # simulated logs (sim_to_page_log.py)
        if k in d:
            L[k] = d[k]
    return L


def to_stream(L, fs=FS):
    """Uniform-rate dict in stream.py's layout for swing_eye (which assumes FS = 400 Hz). Time starts at 0 = the
    first glove frame; t0_s keeps the glove time of that zero. Impact sound clips become clip_t."""
    t = L["t"] - L["t"][0]
    grid = np.arange(0, t[-1], 1 / fs)
    d = {"t": grid, "t0_s": float(L["t"][0]), "sat_dps": SAT_DPS - 3}
    for k in ("hand_gyro", "hand_acc", "arm_gyro", "arm_acc"):
        d[k] = np.stack([np.interp(grid, t, L[k][:, j]) for j in range(3)], 1)
    d["clip_t"] = np.array([c["t"] - L["t"][0] for c in L["clips"] if c["kind"] == "impact"])
    d["hand_only"] = not np.abs(L["arm_gyro"]).any()   # a bare XIAO: swings and tempo from the hand IMU alone
    return d


def summary(L):
    t = L["t"]; dur = t[-1] - t[0] if len(t) > 1 else 0
    dt = np.diff(t)
    lines = [f"# {L['name']}", "",
             f"- Page version {L['page']}, saved {L['meta'].get('saved', '?')}, requested {L['meta'].get('hz', '?')} Hz",
             f"- Glove: {len(t)} frames over {dur:.1f} s = {len(t) / max(dur, 1e-9):.0f} Hz (median gap {np.median(dt) * 1000:.2f} ms, "
             f"longest {dt.max() * 1000:.0f} ms), lost {L['lost']} by sequence number",
             f"- Clock: phone = glove + {L['sync']['b'] / 1000:.3f} s, drift {L['sync']['a'] * 1e6:+.0f} ppm"
             + (" (fitted here; this log has no sync)" if L["sync"].get("fitted_here") else " (from the page)")]
    mv = [s["mv"] for s in L["status"] if s.get("mv")]
    if mv:
        lines.append(f"- Battery {min(mv) / 1000:.2f}-{max(mv) / 1000:.2f} V")
    sat_h = int((np.abs(L["hand_gyro"]) >= SAT_DPS - 3).sum()); sat_a = int((np.abs(L["arm_gyro"]) >= SAT_DPS - 3).sum())
    lines.append(f"- Peak rate: hand {np.abs(L['hand_gyro']).max():.0f}, forearm {np.abs(L['arm_gyro']).max():.0f} deg/s; "
                 f"samples at the {SAT_DPS} deg/s limit: hand {sat_h}, forearm {sat_a}")
    kinds = {}
    for c in L["clips"]:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    lines.append(f"- Sound clips: {', '.join(f'{v} {k}' for k, v in kinds.items()) or 'none'}; 833 Hz motion clips: {len(L['motion'])}")
    if len(L["pose_ms"]):
        found = sum(p is not None for p in L["pose"])
        lines.append(f"- Camera: {len(L['pose'])} pose frames, person found in {found} ({found / len(L['pose']):.0%})"
                     + (f", capture times for {len(L['cap_ms'])}" if len(L["cap_ms"]) else ""))
    for k, name in (("impacts", "impacts noted by the page"), ("labels", "labels"), ("events", "events"), ("swings", "swings analysed on the phone")):
        if L[k]:
            lines.append(f"- {len(L[k])} {name}")
    return lines


def analyse_log(L, out):
    d = to_stream(L)
    rows, panels = [], []
    for ti in find_swings(d):
        a = analyse(d, ti)
        m = a["metrics"]
        t_glove = ti + d["t0_s"]
        src = "sound" if len(d["clip_t"]) and np.min(np.abs(d["clip_t"] - ti)) < 1e-6 else "motion"
        page = next((s for s in L["swings"] if abs(s["t_imp"] - t_glove) < 0.1), None)
        truth = next((e for e in L.get("expected", []) if abs(e["t_s"] - t_glove) < 0.1), None)
        rows.append({"t_glove_s": round(t_glove, 4), "t_in_log_s": round(ti, 3), "impact_from": src,
                     **{k: round(v, 3) for k, v in m.items()},
                     "page_tempo": page and page["tempo"], "page_release_ms": page and page["release_ms"],
                     "club": page and page.get("club"), "truth_kind": truth and truth["kind"],
                     "true_tempo": truth and round(truth["true_tempo"], 3)})
        panels.append((ti, a))
    if rows:
        with open(out / "swings.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
        figure(panels, out / "swings.png", L["name"])
    return rows


def figure(panels, path, title):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(panels); cols = min(3, n); nr = (n + cols - 1) // cols
    fig, axs = plt.subplots(nr, cols, figsize=(cols * 4.6, nr * 3.0), squeeze=False)
    for ax, (ti, a) in zip(axs.flat, panels):
        tt = a["tt"]
        ax.plot(tt, a["wh"], color="#1f77b4", lw=1, label="hand deg/s")
        ax.plot(tt, a["wa"], color="#ff7f0e", lw=1, label="forearm deg/s")
        ax2 = ax.twinx(); ax2.plot(tt, a["beta"], color="#2ca02c", lw=1.2, label="hinge deg"); ax2.tick_params(labelsize=7, colors="#2ca02c")
        for x, c in ((a["take"], "#777777"), (a["top"], "#9467bd"), (0, "#d62728")):
            ax.axvline(x, color=c, ls="--", lw=0.9)
        m = a["metrics"]
        ax.set_title(f"t={ti:.1f} s  tempo {m['tempo']:.1f}  release {m['release_ms']:+.0f} ms", fontsize=8)
        ax.set_xlim(tt[0], tt[-1]); ax.tick_params(labelsize=7)
    for ax in list(axs.flat)[n:]:
        ax.axis("off")
    axs.flat[0].legend(fontsize=6, loc="upper left")
    fig.suptitle(f"{title}: takeaway (grey), top (purple), impact (red)", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "results" / "glove_log"))
    ap.add_argument("--npz", action="store_true")
    a = ap.parse_args()
    for p in a.logs:
        L = load(p)
        out = Path(a.out) / L["name"]; out.mkdir(parents=True, exist_ok=True)
        lines = summary(L)
        rows = analyse_log(L, out)
        lines += ["", f"## Swings found: {len(rows)}", ""]
        if rows:
            lines += ["| # | t in log (s) | impact from | tempo | release (ms) | hinge top (deg) | hand peak (deg/s) | saturated | phone tempo | truth |",
                      "|---|---|---|---|---|---|---|---|---|---|"]
            for i, r in enumerate(rows, 1):
                tr = f"{r['truth_kind']} {r['true_tempo']}" if r["truth_kind"] else ""
                lines.append(f"| {i} | {r['t_in_log_s']:.1f} | {r['impact_from']} | {r['tempo']:.2f} | {r['release_ms']:+.0f} | {r['hinge_top_deg']:.0f} "
                             f"| {r['hand_dps_peak']:.0f} | {r['saturated']} | {r['page_tempo'] if r['page_tempo'] is not None else ''} | {tr} |")
        else:
            lines.append("No swing in this log (forearm faster than 400 deg/s, or the hand faster than 800 deg/s without a forearm IMU).")
        if a.npz:
            d = to_stream(L)
            np.savez_compressed(out / "take.npz", **{k: v for k, v in d.items() if isinstance(v, np.ndarray)})
            lines.append(f"\nSaved take.npz ({FS} Hz, stream.py layout).")
        (out / "summary.md").write_text("\n".join(lines) + "\n")
        print("\n".join(lines)); print(f"-> {out}\n")


if __name__ == "__main__":
    main()
