"""Swing analysis for the glove: find swings, estimate the trail-wrist angle, compute coach-style numbers,
and recognise the swing kind from a few reference swings (part 5's prototype method).

Works on any dict/npz with the host/stream.py keys: t, hand_gyro, hand_acc, arm_gyro, arm_acc (dps, g).
  run on simulation:  python3 analysis/swing_eye.py
  run on a recording: python3 analysis/swing_eye.py take.npz
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

ROOT = Path(__file__).resolve().parent.parent
FS = 400


def find_swings(d, thresh=400, gap=3.0):
    """Impact times (s). A swing = forearm turning faster than `thresh` dps; impact = strongest ring in the hand
    accel near the forearm's speed peak (a practice swing without a ball falls back to that peak)."""
    hand_only = d.get("hand_only", False)               # no forearm IMU: use the hand, after the downswing starts
    t = d["t"]; wa = gaussian_filter1d(np.linalg.norm(d["hand_gyro" if hand_only else "arm_gyro"], axis=1), 4)
    if hand_only:
        thresh = max(thresh, 800)
    acc = d["hand_acc"]
    hp = acc - gaussian_filter1d(acc, 0.7, axis=0)               # keep only the fast ring of the ball strike
    clipped = gaussian_filter1d((np.abs(acc) >= 15.9).astype(float), 3, axis=0) > 0.01
    ring = np.linalg.norm(np.where(clipped, 0, hp), axis=1)    # an axis clipped at 16 g has fake edges; use the others
    out, i = [], 0
    while i < len(t):
        if wa[i] > thresh:
            j = min(len(t), i + int(0.5 * FS)); pk = i + int(np.argmax(wa[i:j]))
            lo, hi = max(0, pk - int(0.15 * FS)), min(len(t), pk + int(0.25 * FS))  # a slowing swing peaks before impact
            imp = lo + int(np.argmax(ring[lo:hi])) if ring[lo:hi].max() > 0.8 else pk
            ti = t[imp]
            if "clip_t" in d and len(d["clip_t"]):  # an impact sound from the glove is the most exact clock
                c = np.asarray(d["clip_t"]); k = int(np.argmin(np.abs(c - ti)))
                if abs(c[k] - ti) < 0.3:
                    ti = float(c[k])
            out.append(ti); i = imp + int(gap * FS)
        else:
            i += 1
    return out


def axis_rate(g):
    """Rotation rate about the sensor's main turning axis (found from the data, so the mounting angle does not
    matter). Sign: positive in the downswing (the biggest peak)."""
    u, s, vt = np.linalg.svd(g - g.mean(0), full_matrices=False)
    w = g @ vt[0]
    return w if w[np.argmax(np.abs(w))] > 0 else -w


def analyse(d, t_imp, pre=2.2, post=0.4, cal=None):
    """cal = result of calib.calibrate (the "정렬" routine). Without it the hinge axis is guessed from the swing itself
    and the wrist is assumed straight (0 deg) at address."""
    t = d["t"]; m = (t >= t_imp - pre) & (t <= t_imp + post)
    tt = t[m] - t_imp
    # sign: positive in the downswing, judged by the mean rate 0.30-0.04 s before impact: on real ball strikes (range
    # 2026-10-26) the biggest peak was the impact jolt / recoil, pointing the other way, sometimes ~30 ms before the
    # sound time. Same rule as the phone's swing.js.
    def down_pos(w):
        b = (tt > -0.30) & (tt < -0.04)
        return -w if b.any() and w[b].mean() < 0 else w
    hand_only = d.get("hand_only", False)
    wh = down_pos(axis_rate(d["hand_gyro"][m]))
    wa = wh if hand_only else down_pos(axis_rate(d["arm_gyro"][m]))
    if hand_only:
        beta = np.zeros(len(tt))                         # no forearm IMU: the hinge can't be measured
    elif cal is not None and cal.get("ok"):
        from calib import wrist_angle
        beta, _ = wrist_angle(d, m, cal)                 # real angle: gravity at address + hinge-axis gyro rates
    else:
        beta = np.cumsum(wa - wh) / FS                   # trail-wrist hinge (deg), zero at address
        beta -= np.median(beta[tt < -pre + 0.4])
    i0 = int(np.argmin(np.abs(tt)))
    # Top and takeaway from the forearm ANGLE, not its rate (2026-10-26, same as the phone page's swing.js): near the
    # top the rate sits at 0 +- a few deg/s for the pause, so "last negative rate" jumped 40-70 ms, and a rate
    # threshold at takeaway fired 50-90 ms late. Gyro bias is removed first (the rate while still at address).
    still = tt < -pre + 0.4
    phi = np.cumsum(wa - np.median(wa[still])) / FS
    imin = int(np.argmin(phi[:i0 + 1])); p_addr = float(np.median(phi[still])); amp = max(1.0, p_addr - phi[imin])
    flat = phi <= phi[imin] + 0.01 * amp                 # the stretch within 1 % of the furthest-back angle
    a0, a1 = imin, imin
    while a0 > 0 and flat[a0 - 1]:
        a0 -= 1
    while a1 < i0 and flat[a1 + 1]:
        a1 += 1
    t_top = 0.5 * (tt[a0] + tt[a1])
    top = int(np.searchsorted(tt, t_top))
    # takeaway against the highest angle in the 1.2 s before the furthest-back point (a hand that settles slightly off
    # its starting angle at address made the window-start reference fire 0.7 s early on a real swing)
    near = (tt[:imin] >= tt[imin] - 1.2)
    p_ref = float(phi[:imin][near].max()) if near.any() else p_addr
    at = np.where(phi[:imin] >= p_ref - 0.01 * amp)[0]
    take = int(at[-1]) if len(at) else 0
    bmax = beta[take:i0 + 1].max()
    after = np.where(beta[top:i0 + 1] < 0.5 * bmax)[0]
    rel = (tt[top + after[0]] if len(after) else 0.0) * 1000
    sat = int((np.abs(d["hand_gyro"][m]) >= d.get("sat_dps", 1999)).sum())   # sim clips at 2000, the real chips at 2293
    nan = float("nan")
    metrics = dict(tempo=float((t_top - tt[take]) / max(1e-3, -t_top)), release_ms=nan if hand_only else float(rel),
                   hinge_top_deg=nan if hand_only else float(bmax), hinge_at_impact_deg=nan if hand_only else float(beta[i0]),
                   arm_dps_impact=float(wa[i0]), hand_dps_peak=float(wh.max()), hand_peak_ms=float(tt[int(np.argmax(wh))] * 1000),
                   saturated=sat)
    # picture for the reference comparison: backswing and downswing each stretched to a fixed length
    seg = lambda x, a, b, n: np.interp(np.linspace(a, b, n), np.arange(len(x)), x)
    j1 = min(len(tt) - 1, i0 + int(0.2 * FS))
    vec = np.concatenate([np.concatenate([seg(x, take, top, 50), seg(x, top, j1, 80)]) * s
                          for x, s in ((wh, 1 / 1000), (wa, 1 / 1000), (beta, 1 / 100))])
    return dict(tt=tt, wh=wh, wa=wa, beta=beta, top=float(tt[top]), take=float(tt[take]), metrics=metrics, vec=vec)


def proto_eval(Z_ref, y_ref, Z_te, y_te, kinds, k, rng, reps=30):
    accs = []
    mu = Z_ref.mean(0)
    nz = lambda Z: (Z - mu) / np.linalg.norm(Z - mu, axis=1, keepdims=True)
    for _ in range(reps):
        P = np.stack([nz(Z_ref[rng.choice(np.where(y_ref == c)[0], k, replace=False)]).mean(0) for c in kinds])
        P /= np.linalg.norm(P, axis=1, keepdims=True)
        accs.append(float((np.array(kinds)[(nz(Z_te) @ P.T).argmax(1)] == y_te).mean()))
    return float(np.mean(accs))


def collect(sessions):
    rows = []
    for d in sessions:
        found = find_swings(d)
        for ti, kind in d["truth"]:
            near = [f for f in found if abs(f - ti) < 0.1]
            if near:
                a = analyse(d, near[0]); a["kind"] = kind; a["dt_ms"] = (near[0] - ti) * 1000; rows.append(a)
    return rows


def simulate(figure_path=None):
    from sim_swing import KINDS, make_session, person
    rng = np.random.default_rng(7)
    me = person(np.random.default_rng(100))
    plan = lambda r, n: list(r.permutation(np.repeat(KINDS, n)))
    S = lambda seed, P=None, scale=1.0, n=8: make_session(seed, plan(np.random.default_rng(seed), n), P=P, golfer_scale=scale)[0]
    day1 = [S(1, me, n=10)]                                   # the reference session: my swings, glove put on once
    day2 = [S(s, me, n=8) for s in (2, 3, 4)]                 # later days: glove put on again (new mounting angles)
    friend = [S(s, None, rng.uniform(0.85, 1.2), 8) for s in (11, 12, 13)]  # other golfers
    R = {}
    n_true = sum(len(x["truth"]) for x in day1 + day2 + friend)
    ref, te2, tef = collect(day1), collect(day2), collect(friend)
    R["found"] = f"{len(ref) + len(te2) + len(tef)} of {n_true} swings found"
    err = np.abs([r["dt_ms"] for r in ref + te2 + tef])
    R["impact_err_ms_motion_only"] = {"median": float(np.median(err)), "p90": float(np.percentile(err, 90)), "max": float(err.max())}
    snd = []
    for d in day2 + friend:   # same swings again, now with the glove's impact sound clips (true impact + 0.3 ms jitter)
        d2 = dict(d); d2["clip_t"] = np.array([ti for ti, _ in d["truth"]]) + np.random.default_rng(5).normal(0, 3e-4, len(d["truth"]))
        snd += [r["dt_ms"] for r in collect([d2])]
    snd = np.abs(snd)
    R["impact_err_ms_with_sound"] = {"median": float(np.median(snd)), "p90": float(np.percentile(snd, 90)), "max": float(snd.max())}
    Zr, yr = np.stack([r["vec"] for r in ref]), np.array([r["kind"] for r in ref])
    # friends give their own references (first 10 of their swings), tested on the rest of theirs
    own = [collect([S(s, None, sc, 10), S(s + 50, None, sc, 8)]) for s, sc in ((11, 0.9), (12, 1.1), (13, 1.2))]
    accs = {k: [] for k in (1, 3, 5)}
    for rows in own:
        a, b = rows[:len(rows) // 2], rows[len(rows) // 2:]
        Za, ya = np.stack([r["vec"] for r in a]), np.array([r["kind"] for r in a])
        Zb, yb = np.stack([r["vec"] for r in b]), np.array([r["kind"] for r in b])
        for k in accs:
            if min((ya == c).sum() for c in KINDS) >= k:
                accs[k].append(proto_eval(Za, ya, Zb, yb, KINDS, k, rng))
    R["friend_own_refs"] = {k: float(np.mean(v)) for k, v in accs.items() if v}
    for name, te in (("me_later", te2), ("friend", tef)):
        Zt, yt = np.stack([r["vec"] for r in te]), np.array([r["kind"] for r in te])
        R[name] = {k: proto_eval(Zr, yr, Zt, yt, KINDS, k, rng) for k in (1, 3, 5)}
        # same comparison without the eye: the raw gyro window, not aligned to the backswing/top
        raw = lambda rows: np.stack([np.concatenate([np.interp(np.linspace(-1.6, 0.2, 260), r["tt"], np.linalg.norm(np.c_[r["wh"]], axis=1))]) for r in rows])
        R[name + "_raw"] = {k: proto_eval(raw(ref), yr, raw(te), yt, KINDS, k, rng) for k in (1, 3, 5)}
    R["metrics_by_kind"] = {k: {m: float(np.median([r["metrics"][m] for r in ref + te2 if r["kind"] == k]))
                                for m in ("tempo", "release_ms", "hinge_top_deg", "hinge_at_impact_deg", "arm_dps_impact", "hand_dps_peak", "saturated")}
                            for k in KINDS}
    # alignment ("정렬 시작") vs. no alignment: wrist-angle error against the simulator's true angle
    from calib import calibrate
    E = {"no_align": [], "align": [], "no_align_address": [], "align_address": [], "no_align_impact": [], "align_impact": []}
    for seed in (21, 22, 23, 24, 25, 26):
        d, _ = make_session(seed, plan(np.random.default_rng(seed), 4), P=me, calib=True, mount_deg=25)
        cal = calibrate(d, d["calib_span"])
        if not cal["ok"]:
            continue
        for ti, kind in d["truth"]:
            near = [f for f in find_swings(d) if abs(f - ti) < 0.1]
            if not near:
                continue
            m = (d["t"] >= near[0] - 2.2) & (d["t"] <= near[0] + 0.4)
            tt = d["t"][m] - near[0]; w = (tt > -1.5) & (tt < 0.05); bt = d["beta_true"][m]
            i0 = int(np.argmin(np.abs(tt)))
            for name, c in (("no_align", None), ("align", cal)):
                b = analyse(d, near[0], cal=c)["beta"]
                E[name].append(float(np.sqrt(np.mean((b[w] - bt[w]) ** 2))))
                E[name + "_address"].append(float(abs(b[0] - bt[0]))); E[name + "_impact"].append(float(abs(b[i0] - bt[i0])))
    R["wrist_angle_err_deg"] = {k: float(np.median(v)) for k, v in E.items()}
    R["saturated_swings"] = f"{sum(r['metrics']['saturated'] > 0 for r in ref + te2 + tef)} of {len(ref + te2 + tef)}"
    if figure_path is None:
        (ROOT / "results").mkdir(exist_ok=True)
        (ROOT / "results/swing_sim.json").write_text(json.dumps(R, indent=1), encoding="utf-8")
    print(json.dumps(R, indent=1))
    figure(ref + te2, R, figure_path or ROOT / "figs/swing-sim.png")


def figure(rows, R, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "figure.facecolor": "#fbfaf7"})
    C = {"good": "#2e7d4f", "early": "#c0392b", "decel": "#a86a00"}
    L = {"good": "Good swing", "early": "Early release", "decel": "Slowing into impact"}
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.5), layout="constrained",
                          gridspec_kw={"width_ratios": [1.2, 1, 0.9]})
    for k in ("good", "early"):
        r = next(x for x in rows if x["kind"] == k)
        ax[0].plot(r["tt"], r["beta"], color=C[k], lw=2.2, label=L[k])
    ax[0].axvline(0, color="#555", lw=1, ls="--")
    ax[0].text(0.02, 0.93, "Impact", transform=ax[0].get_xaxis_transform(), fontsize=10, color="#555")
    ax[0].set(xlim=(-1.6, 0.35), xlabel="Time from impact (s)", ylabel="Trail wrist extension (°)")
    ax[0].set_title("Wrist angle from the glove", loc="left", weight="bold")
    ax[0].legend(fontsize=9, loc="lower left")
    for k in C:
        rr = [x for x in rows if x["kind"] == k]
        ax[1].scatter([x["metrics"]["release_ms"] for x in rr], [x["metrics"]["arm_dps_impact"] for x in rr], s=22, color=C[k], label=L[k], alpha=.8)
    ax[1].set(xlabel="Half-release timing (ms from impact)", ylabel="Forearm speed at impact (°/s)")
    ax[1].set_title("Release timing and forearm speed", loc="left", weight="bold")
    ax[1].legend(fontsize=9, loc="lower left")
    ks = [1, 3, 5]
    for name, lab, ls in (("me_later", "Same golfer, later session", "-"), ("friend", "Different golfer", "--")):
        ax[2].plot(ks, [R[name][k] * 100 for k in ks], ls, marker="o", color="#1f6fb2", label=lab)
        ax[2].plot(ks, [R[name + "_raw"][k] * 100 for k in ks], ls, marker="o", color="#999", label=lab + " (raw gyro)")
    ax[2].set(ylim=(30, 102), xticks=ks, xlabel="Reference swings per type", ylabel="Accuracy (%)")
    ax[2].set_title("Swing classification accuracy", loc="left", weight="bold")
    ax[2].legend(fontsize=8.5, loc="lower right")
    fig.suptitle("Glove swing analysis with simulated data", fontsize=15, weight="bold")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=120)
    plt.close(fig)
    print(output)


def real(path):
    d = dict(np.load(path, allow_pickle=True))
    for ti in find_swings(d):
        m = analyse(d, ti)["metrics"]
        print(f"swing at {ti:6.2f} s: tempo {m['tempo']:.1f}:1, wrist half-released {m['release_ms']:+.0f} ms, "
              f"hinge at top {m['hinge_top_deg']:.0f}°, at impact {m['hinge_at_impact_deg']:.0f}°, "
              f"forearm {m['arm_dps_impact']:.0f} dps at impact" + (f", gyro saturated {m['saturated']} samples" if m["saturated"] else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", nargs="?", type=Path)
    parser.add_argument("--figure", type=Path, help="write the simulation figure to this path")
    args = parser.parse_args()
    if args.recording:
        if args.figure:
            parser.error("--figure requires simulated data")
        real(args.recording)
    else:
        simulate(args.figure)
