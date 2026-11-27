"""Alignment ("정렬") for the glove: find the trail-wrist hinge axis in each sensor's own frame and the straight-wrist
reference, from a 15-20 s routine started by the voice command "정렬 시작".

Routine (GUIDE below is what the app says aloud):
  1. wrist straight, hold still 2 s       -> straight-wrist reference (both sensors' gravity directions)
  2. bend the wrist back and straighten, 5x -> hinge axis
  3. hold still 1 s
The forearm may drift; the axis fit does not need it to be still.

Hinge-axis fit (Seel, Schauer & Raisch 2012, "Joint axis and position estimation from inertial measurement data"):
for a hinge, |w_hand x j_hand| = |w_arm x j_arm| at every moment. Solve for the two unit axes (4 angles) by least squares.
Then the wrist rate is w_hand.j_hand - w_arm.j_arm, and at any still moment the wrist angle follows from gravity.
"""
import numpy as np
from scipy.optimize import least_squares

FS = 400
GUIDE = [(0.0, "정렬을 시작할게요. 손목을 곧게 펴고 가만히 있어 주세요."),
         (2.0, "이제 손목을 뒤로 젖혔다가 펴기를 다섯 번 해 주세요."),
         (9.0, "손목을 곧게 펴고 가만히 있어 주세요."),
         (10.5, "정렬이 끝났어요.")]


def unit(th, ph):
    return np.array([np.cos(ph) * np.cos(th), np.cos(ph) * np.sin(th), np.sin(ph)])


def sph(v):
    v = v / np.linalg.norm(v); return np.arctan2(v[1], v[0]), np.arcsin(np.clip(v[2], -1, 1))


def _plane_angle(f, j, ref):
    """Angle (deg) of gravity f around axis j, measured from the direction ref (both projected on the plane normal to j)."""
    a = ref - (ref @ j) * j; a /= np.linalg.norm(a); b = np.cross(j, a)
    fp = f - np.outer(f @ j, j)
    return np.degrees(np.arctan2(fp @ b, fp @ a))


def calibrate(d, span):
    t = d["t"]; m = (t >= span[0]) & (t < span[1])
    gh, ga = np.radians(d["hand_gyro"][m]), np.radians(d["arm_gyro"][m])
    fh, fa = d["hand_acc"][m], d["arm_acc"][m]
    tt = t[m] - span[0]
    still = (tt < 1.8) & (np.linalg.norm(gh, axis=1) < np.radians(8)) & (np.linalg.norm(ga, axis=1) < np.radians(8))
    if still.sum() < 0.5 * FS:
        return {"ok": False, "why": "손목을 곧게 편 채로 2초 동안 가만히 있지 않았어요"}
    f_h0, f_a0 = fh[still].mean(0), fa[still].mean(0)
    f_h0 /= np.linalg.norm(f_h0); f_a0 /= np.linalg.norm(f_a0)

    act = np.linalg.norm(gh, axis=1) > np.radians(10)
    G1, G2 = gh[act], ga[act]
    res = lambda x: np.linalg.norm(np.cross(G1, unit(*x[:2])), axis=1) - np.linalg.norm(np.cross(G2, unit(*x[2:])), axis=1)
    u, s, vt = np.linalg.svd(G1 - G1.mean(0), full_matrices=False)  # the hand turns mostly about the hinge: a good start
    best = None
    rng = np.random.default_rng(0)
    for k in range(12):
        x0 = np.r_[sph(vt[0]), sph(rng.normal(size=3))] if k else np.r_[sph(vt[0]), sph(vt[0])]
        r = least_squares(res, x0)
        if best is None or r.cost < best.cost:
            best = r
    jh, ja = unit(*best.x[:2]), unit(*best.x[2:])
    # signs: the two axes must point the same way through the joint. With the wrong pairing the forearm's own turning
    # leaks into the wrist angle, so the wrist would not come back to straight at the end of the routine.
    end = lambda s: abs(np.sum(gh @ jh - s * (ga @ ja)) / FS)
    ja = ja * (1 if end(1) <= end(-1) else -1)
    rate = np.degrees(gh @ jh - ga @ ja)
    ang = np.cumsum(rate) / FS
    if ang[np.argmax(np.abs(ang))] < 0:  # the routine starts by bending back: make that positive
        jh, ja, rate, ang = -jh, -ja, -rate, -ang
    rng_deg = float(ang.max() - ang.min())
    rms_mps = float(np.sqrt(np.mean(best.fun ** 2)))
    cal = {"ok": True, "j_hand": jh, "j_arm": ja, "f_hand0": f_h0, "f_arm0": f_a0, "range_deg": rng_deg,
           "fit_rms_dps": float(np.degrees(rms_mps)), "end_drift_deg": float(ang[-1])}
    # sign between the gravity angle and the gyro angle, checked on the routine itself
    gang = static_angle(fh, fa, cal)
    cal["g_sign"] = 1.0 if np.corrcoef(gang, ang)[0, 1] >= 0 else -1.0
    problems = []
    if abs(cal["end_drift_deg"]) > 10:
        problems.append("마지막에 손목이 곧게 돌아오지 않았어요")
    if rng_deg < 30:
        problems.append(f"손목을 {rng_deg:.0f}°만 젖혔어요. 조금 더 크게 해 주세요")
    if abs(f_h0 @ jh) > 0.97 or abs(f_a0 @ ja) > 0.97:  # within ~14 deg of vertical: gravity cannot show the angle
        problems.append("손목 축이 거의 수직이에요. 팔을 내리고 다시 해 주세요")
    if cal["fit_rms_dps"] > 25:
        problems.append("움직임이 불규칙했어요. 아래팔을 덜 움직이고 다시 해 주세요")
    cal["problems"] = problems
    cal["ok"] = not problems
    return cal


def static_angle(fh, fa, cal):
    """Wrist angle (deg) from gravity alone, valid when the hand is still (address, finish)."""
    a_h = _plane_angle(np.atleast_2d(fh), cal["j_hand"], cal["f_hand0"])
    a_a = _plane_angle(np.atleast_2d(fa), cal["j_arm"], cal["f_arm0"])
    v = (a_h - a_a + 180) % 360 - 180
    return v * cal.get("g_sign", 1.0)


def wrist_angle(d, m, cal, still_n=int(0.3 * FS)):
    """Wrist angle over the samples in mask m: gravity gives the start (the first still_n samples are address),
    the hinge-axis gyro rates carry it through the swing."""
    gh, ga = d["hand_gyro"][m], d["arm_gyro"][m]
    rate = gh @ cal["j_hand"] - ga @ cal["j_arm"]
    b0 = float(np.median(static_angle(d["hand_acc"][m][:still_n], d["arm_acc"][m][:still_n], cal)))
    return b0 + np.cumsum(rate) / FS, b0


def report(cal):
    if not cal.get("ok") and "j_hand" not in cal:
        return "정렬 실패: " + cal["why"]
    msg = f"정렬 {'완료' if cal['ok'] else '다시 필요'}: 손목을 {cal['range_deg']:.0f}° 움직였고, 맞춤 오차 {cal['fit_rms_dps']:.0f} °/s"
    return msg + ("" if cal["ok"] else ". " + ". ".join(cal["problems"]))
