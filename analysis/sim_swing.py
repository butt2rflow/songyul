"""Simulated right-hand (trail) glove data for golf swings, in the same units and keys as host/stream.py.

Planar swing model:
- arm angle phi(t) in the swing plane: address 0 -> top -A -> impact 0 (fast) -> finish +B
- trail-wrist hinge beta(t): 0 -> beta_top at the top, held during the downswing ("lag"), released to 0 at impact
The hand segment turns at phi - beta (the hinge adds to the backswing; releasing it speeds the hand up), the forearm at phi. Gyro = angular rate about the swing-plane normal (plus a
little off-plane wobble). Accel = centripetal + tangential + gravity (plane tilted 60 deg) + a ball-strike ring at impact.
Each sensor is mounted with its own random rotation per session. Gyro is clipped at +-2000 dps and accel at +-16 g,
like the real chips.

Kinds:
- good:  release starts late in the downswing and finishes at impact
- early: release starts at the top ("casting") and the wrist is already flat well before impact
- decel: good wrist action but the arm slows into impact (lower impact speed, weaker strike)

make_session(...) -> dict like stream.py's npz plus "truth": list of (impact_time_s, kind).
"""
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.ndimage import gaussian_filter1d
from scipy.spatial.transform import Rotation

FS = 400
KINDS = ("good", "early", "decel")


def person(rng, scale=1.0):
    """Body/style parameters that stay fixed for one golfer. scale > 1 makes a different golfer."""
    j = lambda lo, hi: rng.uniform(lo, hi)
    return dict(A=j(95, 120), B=j(130, 170), Tb=j(0.75, 1.0) * scale, Td=j(0.24, 0.32) * scale,
                v_imp=j(850, 1150) / scale, beta_top=j(75, 100), r_hand=j(0.55, 0.65), r_arm=j(0.35, 0.45),
                b_addr=j(8, 25))  # the trail wrist is already a little bent back at address


def swing(rng, P, kind):
    """One swing: returns t (s), phi, beta (deg) and impact time. Small swing-to-swing variation on top of P."""
    v = lambda x, s=0.05: x * (1 + rng.normal(0, s))
    A, B, Tb, Td, vi, bt = v(P["A"]), v(P["B"]), v(P["Tb"]), v(P["Td"], .04), v(P["v_imp"]), v(P["beta_top"])
    if kind == "decel":
        vi *= rng.uniform(0.55, 0.7)
    t_addr, pause, fin = rng.uniform(1.0, 1.5), rng.uniform(0.04, 0.10), 0.55
    tt = np.array([0, t_addr, t_addr + Tb, t_addr + Tb + pause, t_addr + Tb + pause + Td, t_addr + Tb + pause + Td + fin, t_addr + Tb + pause + Td + fin + 0.8])
    t_imp = tt[4]
    swing.phases = (tt[1], tt[2], tt[3])   # takeaway, top reached, downswing starts (after the pause); read by make_session
    phi_k = np.array([0, 0, -A, -A, 0, B, B]); dphi_k = np.array([0, 0, 0, 0, vi, 0, 0])
    if kind == "decel":
        dphi_k[4] = vi
    t = np.arange(0, tt[-1], 1 / FS)
    phi = CubicHermiteSpline(tt, phi_k, dphi_k)(t)
    # wrist hinge: set at the top, held, then released
    t_top = tt[3]
    rel0 = {"good": rng.uniform(0.55, 0.72), "decel": rng.uniform(0.55, 0.72), "early": rng.uniform(0.0, 0.2)}[kind]
    rel1 = {"good": 1.0, "decel": 1.0, "early": rng.uniform(0.55, 0.75)}[kind]
    tb = np.array([0, t_addr, t_addr + 0.75 * Tb, t_top + rel0 * Td, t_top + rel1 * Td, t_imp + 0.25, tt[-1]])
    tb = np.maximum.accumulate(tb + np.arange(len(tb)) * 1e-4)
    b0 = P["b_addr"] * (1 + rng.normal(0, 0.1))
    b_k = np.array([b0, b0, bt, bt * rng.uniform(0.92, 1.0), b0 * rng.uniform(0.6, 1.0), -35, -35])
    beta = CubicHermiteSpline(tb, b_k, np.zeros(len(tb)))(t)
    if kind == "early":  # after an early release the hand keeps flipping past flat through impact
        beta -= np.exp(-0.5 * ((t - t_imp) / 0.08) ** 2) * rng.uniform(10, 25)
    sm = lambda x: gaussian_filter1d(x, 0.012 * FS)  # muscles do not make kinks
    return t, sm(phi), sm(beta), t_imp, kind


def sensors(rng, t, phi, beta, t_imp, kind, P, Rh, Ra):
    """Gyro (dps) and accel (g) for the hand and forearm sensors, in each sensor's own mounted frame."""
    dt = 1 / FS
    out = {}
    for seg, ang, r, Rm in (("hand", phi - beta, P["r_hand"], Rh), ("arm", phi, P["r_arm"], Ra)):
        w = np.gradient(ang, dt)                     # deg/s about the plane normal
        wr = np.radians(w); al = np.gradient(wr, dt)
        wob = rng.normal(0, 1, (len(t), 2)).cumsum(0); wob -= np.linspace(0, 1, len(t))[:, None] * wob[-1]
        gyro = np.stack([wob[:, 0] * 2, wob[:, 1] * 2, w], 1)
        g_in = np.sin(np.radians(60)); th = np.radians(ang)
        acc = np.stack([-r * wr ** 2 / 9.81 + g_in * np.cos(th),     # radial (centripetal toward the shoulder)
                        r * al / 9.81 - g_in * np.sin(th),           # tangential
                        np.full(len(t), np.cos(np.radians(60)))], 1)
        if seg == "hand":
            acc[:, 0] -= 0.08 * np.radians(np.gradient(beta, dt)) ** 2 / 9.81  # wrist's own spin, small
        k = (t >= t_imp)
        ring = np.exp(-(t - t_imp) / 0.015) * np.sin(2 * np.pi * 260 * (t - t_imp)) * k
        amp = (rng.uniform(6, 11) if kind != "decel" else rng.uniform(3, 6)) * (1 if seg == "hand" else 0.3)
        acc += ring[:, None] * amp * np.array([0.3, 1.0, 0.5])
        gyro = Rm.apply(gyro) + rng.normal(0, 0.6, gyro.shape) + rng.normal(0, 1.0, 3)
        acc = Rm.apply(acc) + rng.normal(0, 0.012, acc.shape)
        out[seg + "_gyro"] = np.clip(gyro, -2000, 2000); out[seg + "_acc"] = np.clip(acc, -16, 16)
    out["beta_true"] = beta.copy()
    return out


def calib_segment(rng, Rh, Ra, cycles=5):
    """The alignment routine: wrist straight and still for 2 s, then bend it back and straighten it `cycles` times while
    the forearm drifts a little (nobody holds it perfectly still), then 1 s still. Same hinge geometry as the swing model:
    hand frame = forearm frame turned by -beta about z."""
    dt = 1 / FS
    T = 2.0 + cycles * rng.uniform(1.0, 1.4) + 1.0
    t = np.arange(0, T, dt)
    amp = rng.uniform(45, 70)
    c = np.clip((t - 2.0) / (T - 3.0), 0, 1)
    beta = amp * np.sin(np.pi * c * cycles) ** 2 * (c > 0) * (c < 1)
    beta = gaussian_filter1d(beta, 0.03 * FS)
    # forearm: slow random rotation (deg/s) about all three axes, faded in after the still start
    w_arm = np.stack([gaussian_filter1d(rng.normal(0, 1, len(t)), 0.25 * FS) for _ in range(3)], 1)
    w_arm *= rng.uniform(15, 35) / max(1e-6, w_arm.std()) * (np.clip((t - 1.8) / 0.4, 0, 1) * np.clip((T - 0.8 - t) / 0.4, 0, 1))[:, None]
    R = Rotation.from_euler("xyz", rng.uniform(-40, 40, 3), degrees=True)  # starting pose of the forearm
    f_arm, f_hand, g_hand = [], [], []
    for i in range(len(t)):
        Rh_seg = Rotation.from_rotvec([0, 0, -np.radians(beta[i])])
        f = R.inv().apply([0, 0, 1.0])                         # what an accelerometer reads at rest: 1 g "up"
        f_arm.append(f); f_hand.append(Rh_seg.inv().apply(f))
        db = (beta[min(i + 1, len(t) - 1)] - beta[max(i - 1, 0)]) / (2 * dt)
        g_hand.append(Rh_seg.inv().apply(w_arm[i]) + np.array([0, 0, -db]))
        R = R * Rotation.from_rotvec(np.radians(w_arm[i]) * dt)
    out = {"arm_gyro": Ra.apply(w_arm) + rng.normal(0, 0.6, (len(t), 3)), "hand_gyro": Rh.apply(np.array(g_hand)) + rng.normal(0, 0.6, (len(t), 3)),
           "arm_acc": Ra.apply(np.array(f_arm)) + rng.normal(0, 0.012, (len(t), 3)), "hand_acc": Rh.apply(np.array(f_hand)) + rng.normal(0, 0.012, (len(t), 3)),
           "beta_true": beta}
    return out


def make_session(seed, kinds, P=None, golfer_scale=1.0, mount_deg=20, calib=False):
    """A continuous recording with several swings separated by idle time (and a waggle now and then)."""
    rng = np.random.default_rng(seed)
    P = P or person(rng, golfer_scale)
    Rh = Rotation.from_rotvec(rng.normal(0, 1, 3) / np.sqrt(3) * np.radians(mount_deg))
    Ra = Rotation.from_rotvec(rng.normal(0, 1, 3) / np.sqrt(3) * np.radians(mount_deg))
    parts, truth, phases, t0 = [], [], [], 0.0
    if calib:  # the voice command "정렬 시작" starts this routine at the beginning of the session
        parts.append(calib_segment(rng, Rh, Ra)); t0 = len(parts[-1]["beta_true"]) / FS
    span = (0.0, t0)
    for kind in kinds:
        t, phi, beta, ti, kd = swing(rng, P, kind)
        if rng.random() < 0.3:  # a small pre-shot waggle in the idle part
            # smooth in and out (Hann window): a waggle that starts at full speed in one sample made 100 g accel spikes
            m = (t > 0.2) & (t < 0.8); win = np.where(m, np.sin(np.pi * (t - 0.2) / 0.6) ** 2, 0)
            beta = beta + win * 15 * np.sin(2 * np.pi * 2.5 * (t - 0.2))
        parts.append(sensors(rng, t, phi, beta, ti, kd, P, Rh, Ra)); truth.append((t0 + ti, kind))
        phases.append(tuple(t0 + x for x in swing.phases)); t0 += len(t) / FS
        idle = int(rng.uniform(1.5, 3.0) * FS)  # walking back, re-teeing: slow random motion
        z = {k: np.repeat(parts[-1][k][-1:], idle, 0) + (rng.normal(0, 0.5 if "gyro" in k else 0.01, (idle, 3)) if k != "beta_true" else 0) for k in parts[-1]}
        parts.append(z); t0 += idle / FS
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    d["t"] = np.arange(len(d["hand_gyro"])) / FS
    d["truth"] = truth
    d["phases"] = phases   # per swing: (takeaway, top reached, downswing starts), seconds
    if calib:
        d["calib_span"] = span
    d["hinge_axes_true"] = (Rh.apply([0, 0, 1.0]), Ra.apply([0, 0, 1.0]))
    return d, P


if __name__ == "__main__":
    d, P = make_session(0, ["good", "early", "decel"])
    print({k: v.shape for k, v in d.items() if hasattr(v, "shape")}, d["truth"])
    print("max |hand gyro| %.0f dps, saturated samples %d" % (abs(d["hand_gyro"]).max(), int((abs(d["hand_gyro"]) >= 2000).sum())))
