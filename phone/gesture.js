// Hand gestures from the glove's hand IMU (phone page). No DOM, so node can test it (analysis/test_gesture_js.mjs).
// Gestures are fixed; what each one DOES is set by the user on the page (a command phrase run through voice.js, or
// "listen"). Some gestures need ~1 s without big motion first, and taps are only acted on after the hand is calm
// again for 0.4 s, so a swing, a waggle or walking shouldn't fire one. A swing (hand faster than 1200 deg/s with a
// forearm IMU, 800 without one; or the forearm IMU faster than 1000 deg/s;
// it was 400 until 2026-11-13, but lifting the hand to knock moved the wrist 680-980 deg/s and locked out every tap) locks gestures out for 2 s.
//   tap2  : two sharp knocks on the back of the hand (accel jump > 1.2 g vs ~5 ms back), 0.10-0.45 s apart
//           Opens the club dial after calm, or confirms while the dial is open (no prior calm needed there).
//   hold  : hold a taught pose still for 1 s (gravity within 25 deg of the taught direction, < 25 deg/s)
//   twist : twist the wrist back and forth quickly: one gyro axis crosses +-400 deg/s with alternating sign 3+ times in 1 s
//           (300 let a firm 350 deg/s waggle through; with only the hand IMU a waggle and a twist differ only in size)
//   shake : shake the hand: one accel axis (gravity removed) crosses +-1.5 g with alternating sign 3+ times in 0.8 s
//   dial  : turn the wrist one way like a dial, out of >= 0.4 s of calm: the rotation (as a 3D vector, so the IMU's angle on the
//           glove doesn't matter) reaches >= 90 deg in 0.25-1.0 s (prototype turns 110-193 deg; a 72 deg hand turn between range shots was a false dial at 60) with a peak >= 300 deg/s (measured turns: 440-850 deg/s, 0.3-0.8 s;
//           a slow 105 deg hand turn after a swing, 170 deg/s over 1.3 s, was a false dial at 150 / 1.5), the net turn is >= 50 % of the
//           turning path (real dials 0.59-0.96 with a bounce-back; swings 0.07-0.24; a twist ~0), accel within 1.5 g of 1 g, then settled (< 80 deg/s) for 0.15 s.
//           Reports dir (+1/-1 along the glove's turn axis, learnt from the first dial; the page maps it to clockwise) and
//           steps (1 per ~150 deg, at most 3). It skips the 1.5 s cool-down so club changes can follow each other.
//   tap4  : four knocks in a row, no calm needed before. The run ends 0.5 s after the last knock, so two knocks
//           cannot open the club dial while a four-knock run is still in progress. The default action is listening.
// Club-change mode (2026-11-13; replaces the one-shot dial for the club): after startClubMode() the wrist turn away
// from where it was when the mode began works like a jog dial. The turn is followed along the learnt dial axis (gyro
// integrated, its bias taken in the first 0.25 s): stepping starts past 25 deg and stops under 15 deg (no flicking at the edge); up to 50 deg steps one club every 0.9 s;
// 50-90 deg every 0.45 s; over 90 deg every 0.2 s; the sign picks next/previous ("clubstep" events). Turning back under
// 15 deg stops. A swing or 20 s with no movement ends the mode ("clubmode" with on:false); tap2 again confirms it on the page.
// While the mode is on, only tap2 is recognised.
// Frame = [t_s, hand gx gy gz (deg/s), hand ax ay az (g), arm gx gy gz, arm ax ay az] (same as swing.js).

export const GESTURES = ["tap2", "tap4", "hold", "twist", "shake", "dial"];
export const SWING_FRAMES = 6;   // ~25 ms at 240 Hz: a real downswing stays over the limit for tens of ms, a knock for one sample
export const TAP_THRESHOLDS = Object.freeze({
  clubCount: 2, voiceCount: 4,
  accelJumpG: 1.2, lookbackMs: 5.5, handGyroDps: 800,
  ringMs: 60, minGapMs: 100, maxGapMs: 450, timeoutMs: 500,
  calmMs: 400, busyGyroDps: 150, busyAccelDeviationG: 0.35, cooldownMs: 1500,
  swingHandDps: 800, swingHandWithArmDps: 1200, swingArmDps: 1000,
  swingFrames: 1, clubModeSwingFrames: SWING_FRAMES, swingHoldoffMs: 2000,
  diagnosticJumpG: 0.35, // observation floor only, to capture weak impulses without logging sensor noise
});
const tap = TAP_THRESHOLDS;
const ms = (seconds) => +(seconds * 1000).toFixed(1);

export class GestureDetector {
  constructor(onGesture, opts = {}) {
    this.on = onGesture;
    this.enabled = { tap2: true, tap4: true, hold: true, twist: true, shake: true, dial: true, ...(opts.enabled || {}) };
    this.holdRef = opts.holdRef || null;           // unit gravity vector of the taught pose, or null (hold off)
    this.armOk = !!opts.armOk;
    this.hist = [];                                  // ~0.1 s of frames for the tap "5 ms back" check
    this.lastBusy = -Infinity; this.lock = -Infinity; this.cool = -Infinity;
    this.tapRun = null; this.nextTapRun = 0; this.gyroX = [null, null, null]; this.accX = [null, null, null];
    this.lp = null; this.cand = null; this.calmSince = null;
    this.busyStart = -Infinity; this.preCalm = 0;     // start of the current motion, and how long it was calm before it
    this.holdSince = null; this.holdArmed = true; this.last = null;
    this.dl = null; this.prevT = null; this.handLock = -Infinity; this.dialAxis = opts.dialAxis || null;   // dial in progress; swing lock from the hand IMU only
    this.dialLog = [];                              // last few dial checks, accepted or not, with the reason (for tuning on a real glove)
    this.onDialNote = opts.onDialNote || null;      // page hook: keep each check beyond this page's life
    this.onTapCandidate = opts.onTapCandidate || null;
    this.onTapSequence = opts.onTapSequence || null;
    this.lastTapCandidate = null;
    this.tapImpulse = null;
    this.mode = null;                               // club-change mode state, or null
  }
  startClubMode(t) { this.mode = { t0: t, ang: [0, 0, 0], th: 0, g0: null, glp: null, biasSum: [0, 0, 0], biasN: 0, lastStep: -Infinity, lastAny: -Infinity, on: false, wait: 0, lastAct: t }; this.dl = null; }
  stopClubMode() { this.mode = null; }
  clubMode(t, g, gm, dt, acc) {
    const M = this.mode;
    if (!M.glp) M.glp = acc.slice(); else for (let k = 0; k < 3; k++) M.glp[k] += 0.05 * (acc[k] - M.glp[k]);   // gravity, ~80 ms low-pass
    if (this.fastN >= SWING_FRAMES) { this.mode = null; this.on({ name: "clubmode", on: false, why: "swing", t }); return; }
    if (t - M.t0 < 0.25) { if (gm < 30) { for (let k = 0; k < 3; k++) M.biasSum[k] += g[k]; M.biasN++; } return; }
    for (let k = 0; k < 3; k++) M.ang[k] += (g[k] - (M.biasN ? M.biasSum[k] / M.biasN : 0)) * dt;
    const mag = Math.hypot(...M.ang);
    if (!this.dialAxis && mag > 25) {                 // no axis learnt yet: the first clear turn sets it (largest component positive)
      const u = M.ang.map((x) => x / mag), big = u.reduce((m, x, k) => (Math.abs(x) > Math.abs(u[m]) ? k : m), 0);
      this.dialAxis = u.map((x) => x * Math.sign(u[big]));
    }
    // the turn angle: the gyro rate about the dial axis, integrated, and pulled towards the angle gravity has turned
    // about the same axis since the mode began (drift-free while the axis isn't near vertical). Gyro alone drifted to
    // -370 deg in 35 s on the real glove (2026-11-14) and the club never stopped stepping.
    let th = 0;
    if (this.dialAxis) {
      const ax = this.dialAxis, dot = (u, v) => u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
      const b = M.biasN ? M.biasSum.map((x) => x / M.biasN) : [0, 0, 0];
      M.th += dot(g.map((x, k) => x - b[k]), ax) * dt;
      const gd = dot(M.glp, ax), gp = M.glp.map((x, k) => x - gd * ax[k]), gn = Math.hypot(...gp);
      if (gn > 0.4) {
        const gu = gp.map((x) => x / gn);
        if (!M.g0) M.g0 = gu;
        else {
          const cr = [M.g0[1] * gu[2] - M.g0[2] * gu[1], M.g0[2] * gu[0] - M.g0[0] * gu[2], M.g0[0] * gu[1] - M.g0[1] * gu[0]];
          const thG = -Math.atan2(dot(cr, ax), dot(M.g0, gu)) * 180 / Math.PI;   // the body turns opposite to gravity seen from it
          M.th += 0.02 * (thG - M.th);                                          // ~0.2 s to settle at 240 Hz
        }
      }
      th = M.th;
    }
    const a = Math.abs(th);
    // stepping starts past 25 deg and stops under 15 deg, so a wrist resting near the edge doesn't flick the club
    // back and forth (first real try, 2026-11-13: -,+,-,+ at 20-21 deg); re-starting within 0.6 s of the last step waits
    if (!M.on && a >= 25) { M.on = true; M.lastStep = -Infinity; M.wait = M.lastAny + 0.6; }
    else if (M.on && a < 15) M.on = false;
    const every = !M.on ? null : a < 50 ? 0.9 : a < 90 ? 0.45 : 0.2;
    if (gm > 30) M.lastAct = t;
    if (every !== null && t >= M.wait && t - M.lastStep >= every) { M.lastStep = t; M.lastAny = t; M.lastAct = t; this.on({ name: "clubstep", dir: th > 0 ? 1 : -1, deg: Math.round(th), t }); }
    if (t - M.lastAct > 20) { this.mode = null; this.on({ name: "clubmode", on: false, why: "idle", t }); }
  }
  setHoldRef(v) { const n = Math.hypot(...v); this.holdRef = n ? v.map((x) => x / n) : null; }

  frame(f) {
    const t = f[0], g = [f[1], f[2], f[3]], a = [f[4], f[5], f[6]];
    const gm = Math.hypot(...g), am = Math.hypot(...a);
    if (this.lastBusy === -Infinity) this.lastBusy = t;   // the stream's start doesn't count as calm
    const armFast = this.armOk && Math.hypot(f[7], f[8], f[9]) > tap.swingArmDps;
    // a swing = the hand stays fast for SWING_FRAMES samples in a row. One sample over the limit is a knock's jolt: a hard
    // tap read 1,347 deg/s for one sample (12.7 g) and closed club mode as a "swing" (2026-11-14).
    // Outside club mode one sample still locks (a desk bang otherwise let a false shake through in two old logs); in club
    // mode only tap2 counts, so there the lock waits for a real swing and the closing knocks aren't locked out.
    this.fastN = gm > (this.armOk ? tap.swingHandWithArmDps : tap.swingHandDps) ? (this.fastN || 0) + 1 : 0;
    if (this.fastN >= (this.mode ? tap.clubModeSwingFrames : tap.swingFrames) || armFast) {
      this.lock = t + tap.swingHoldoffMs / 1000;
      this.tapResult(this.cand?.tapRun, t, "after_swing_holdoff");
      this.tapResult(this.tapRun, t, "after_swing_holdoff");
      this.cand = null; this.tapRun = null;
    }
    // the dial is a forearm roll, so the forearm IMU races past 400 deg/s on every dial; only the hand lock applies to it
    if (this.fastN >= 1) this.handLock = t + 2;   // dial (off now): unchanged
    const busy = gm > tap.busyGyroDps || Math.abs(am - 1) > tap.busyAccelDeviationG;
    const quietFor = t - this.lastBusy;               // calm time BEFORE this frame
    // gravity estimate (slow low-pass) for the shake check
    if (!this.lp) this.lp = a.slice(); else for (let k = 0; k < 3; k++) this.lp[k] += 0.02 * (a[k] - this.lp[k]);
    this.hist.push(f); while (this.hist.length && this.hist[0][0] < t - 0.1) this.hist.shift();
    const open = t >= this.lock && t >= this.cool;
    const dt = this.prevT === null ? 0 : Math.min(0.05, t - this.prevT); this.prevT = t;
    if (this.mode) this.clubMode(t, g, gm, dt, a);
    if (this.tapRun && this.tapRun.inMode !== !!this.mode) {
      this.tapResult(this.tapRun, t, "other");
      this.tapRun = null;
    }

    // dial: its own small state machine, so a candidate of another gesture doesn't block it. The rotation is followed as a
    // 3D vector because the hand IMU sits at an angle on the glove: a real wrist turn showed up split between x and z
    // (e.g. +122 / -98 deg, 2026-11-13), so "one gyro axis" rejected every turn.
    if (this.enabled.dial && t >= this.handLock && !this.mode) {
      if (!this.dl) {
        if (gm > 60 && quietFor >= 0.4) this.dl = { t0: t, tEnd: t, ang: [0, 0, 0], path: 0, peak: 0, accDev: 0, calm: null };
        else if (gm > 300 && quietFor < 0.4 && t - (this.noCalmAt || -9) > 1.5) {   // a fast turn that started without a pause: log it for tuning
          this.noCalmAt = t; this.dialLog.push({ why: `no pause before (calm ${quietFor.toFixed(2)} s, needs 0.4)`, peak: Math.round(gm) });
          if (this.dialLog.length > 12) this.dialLog.shift();
          if (this.onDialNote) this.onDialNote(this.dialLog[this.dialLog.length - 1]);
        }
      } else {
        const d = this.dl;
        for (let k = 0; k < 3; k++) d.ang[k] += g[k] * dt;
        d.path += gm * dt; d.peak = Math.max(d.peak, gm); d.accDev = Math.max(d.accDev, Math.abs(am - 1));
        if (gm < 80) { if (d.calm === null) d.calm = t; } else { d.calm = null; d.tEnd = t; }   // a hand held in the air drifts ~20-40 deg/s; after a turn it settles slower
        if (t - d.t0 > 2.0) { this.dialNote(d, "too long (no stop within 2 s)"); this.dl = null; }
        else if (d.calm !== null && t - d.calm >= 0.15) {
          const mag = Math.hypot(...d.ang), straight = d.path ? mag / d.path : 0, dur = d.tEnd - d.t0;
          this.dl = null;
          const why = mag < 90 ? "angle < 90" : d.peak < 300 ? "too slow (peak < 300 deg/s)" : straight < 0.5 ? "not one way (back-and-forth or wobbly)"
            : dur < 0.25 ? "too quick (< 0.25 s)" : dur > 1.0 ? "too long (> 1.0 s)" : d.accDev >= 1.5 ? "too jerky (accel)" : "ok";
          this.dialNote(d, why, dur, straight);
          if (why === "ok") {
            // which way: the sign along the glove's own turn axis. The first dial sets the axis (sign fixed so its largest
            // component is positive, so it doesn't depend on which way that first turn went); later dials refine it.
            const u = d.ang.map((x) => x / mag);
            if (!this.dialAxis) { const big = u.reduce((m, x, k) => (Math.abs(x) > Math.abs(u[m]) ? k : m), 0); this.dialAxis = u.map((x) => x * Math.sign(u[big])); }
            const dot = u[0] * this.dialAxis[0] + u[1] * this.dialAxis[1] + u[2] * this.dialAxis[2], dir = dot >= 0 ? 1 : -1;
            const ax = this.dialAxis.map((x, k) => 0.8 * x + 0.2 * dir * u[k]), n = Math.hypot(...ax); this.dialAxis = ax.map((x) => x / n);
            this.tapResult(this.cand?.tapRun, t, "other");
            this.tapResult(this.tapRun, t, "other");
            this.cand = null; this.calmSince = null; this.gyroX = [null, null, null]; this.accX = [null, null, null]; this.tapRun = null;
            this.last = { name: "dial", t };
            this.on({ name: "dial", t, dir, deg: Math.round(dir * mag), steps: Math.max(1, Math.min(3, Math.floor((mag + 70) / 150))) });
            return;
          }
        }
      }
    } else this.dl = null;

    // a candidate waits for 0.4 s of calm, then fires; big motion meanwhile cancels it
    if (this.cand) {
      const run = this.cand.tapRun;
      if (!open || (run && (run.inMode !== !!this.mode || !this.enabled[this.cand.name]))) {
        this.tapResult(run, t, "other");
        this.cand = null;
      }
      else if (busy) this.calmSince = null;
      else if (this.calmSince === null) this.calmSince = t;
      else if (t - this.calmSince >= tap.calmMs / 1000) this.fire(this.cand.name, t);
    }
    if (busy) { if (quietFor > 0.05) { this.busyStart = t; this.preCalm = quietFor; } this.lastBusy = t; }
    const fromCalm = (t0) => this.preCalm >= 1.0 && t0 - this.busyStart < 0.6;   // began within 0.6 s of leaving >= 1 s of calm
    // Wait for the full run before distinguishing a double tap from the opening taps of a voice gesture.
    if (this.tapRun && t - this.tapRun.times.at(-1) > tap.timeoutMs / 1000) {
      const run = this.tapRun;
      this.tapRun = null;
      const name = run.club && run.calm && run.times.length === tap.clubCount ? "tap2"
        : run.voice && run.times.length === tap.voiceCount ? "tap4" : null;
      if (name && this.enabled[name] && open && !this.cand) {
        this.cand = { name, t, tapRun: run }; this.calmSince = null;
      } else {
        this.tapResult(run, t, "timeout");
      }
    }
    if (this.enabled.tap2 || (!this.mode && this.enabled.tap4)) this.checkTap(f, gm, open, fromCalm);
    if (!open || this.cand) { this.gyroX = [null, null, null]; this.accX = [null, null, null]; return; }
    if (this.mode) return;                            // in club-change mode nothing else is recognised
    // shake: gravity-removed accel alternating past +-1.5 g
    if (this.enabled.shake) {
      for (let k = 0; k < 3; k++) {
        const v = a[k] - this.lp[k], s = v > 1.5 ? 1 : v < -1.5 ? -1 : 0;
        const x = this.accX[k];
        if (s && (!x || x.sign !== s)) {
          const cont = x && t - x.t0 < 0.8, list = cont ? x.list.concat([t]) : [t];
          this.accX[k] = { sign: s, t0: list[0], list, ok: cont ? x.ok : fromCalm(t) };
          if (list.length >= 3 && this.accX[k].ok) { this.cand = { name: "shake", t }; this.calmSince = null; return; }
        }
      }
    }
    // twist: one gyro axis alternating past +-300 deg/s, with only moderate accel (else it's a shake)
    if (this.enabled.twist) {
      for (let k = 0; k < 3; k++) {
        const s = g[k] > 400 ? 1 : g[k] < -400 ? -1 : 0, x = this.gyroX[k];
        if (s && (!x || x.sign !== s)) {
          const cont = x && t - x.t0 < 1.0, list = cont ? x.list.concat([t]) : [t];
          this.gyroX[k] = { sign: s, t0: list[0], list, ok: cont ? x.ok : fromCalm(t) };
          if (list.length >= 3 && Math.abs(am - 1) < 2.5 && this.gyroX[k].ok) { this.cand = { name: "twist", t }; this.calmSince = null; return; }
        }
      }
    }
    // hold a taught pose
    if (this.enabled.hold && this.holdRef) {
      const cos = (a[0] * this.holdRef[0] + a[1] * this.holdRef[1] + a[2] * this.holdRef[2]) / (am || 1);
      const near = cos > Math.cos(25 * Math.PI / 180), far = cos < Math.cos(40 * Math.PI / 180);
      if (far) this.holdArmed = true;
      if (near && gm < 25 && Math.abs(am - 1) < 0.15 && this.holdArmed) {
        if (this.holdSince === null) this.holdSince = t;
        else if (t - this.holdSince >= 1.0) { this.holdArmed = false; this.holdSince = null; this.fire("hold", t); }
      } else this.holdSince = null;
    }
  }
  checkTap(f, gm, open, fromCalm) {
    if ((!open || this.cand) && !this.onTapCandidate) return;
    const t = f[0];
    const old = this.hist.find((h) => h[0] >= t - tap.lookbackMs / 1000) || this.hist[0];
    const jump = Math.max(Math.abs(f[4] - old[4]), Math.abs(f[5] - old[5]), Math.abs(f[6] - old[6]));
    if (!(jump > tap.diagnosticJumpG)) {
      if (this.tapImpulse && !this.tapImpulse.strong) this.noteTap(this.tapImpulse.peak, "too_weak");
      this.tapImpulse = null;
      return;
    }
    if (jump <= tap.accelJumpG) {
      if (this.onTapCandidate && !this.tapImpulse?.strong && (!this.tapImpulse || jump > this.tapImpulse.peak.jump)) {
        this.tapImpulse = { peak: { t, jump, gm, ...this.tapCandidateContext() }, strong: false };
      }
      return;
    }
    const prev = this.tapRun?.times.at(-1);
    const gap = t - prev;
    let reason = null, counted = false;
    if (t < this.lock) reason = "after_swing_holdoff";
    else if (!(gm < tap.handGyroDps)) reason = "motion";
    else if (!open || this.cand) reason = "other";
    else if (prev && (gap <= tap.ringMs / 1000 || gap < tap.minGapMs / 1000)) reason = "too_fast";
    else {
      if (prev && gap <= tap.maxGapMs / 1000) this.tapRun.times.push(t);
      else {
        if (prev) {
          reason = "too_slow";
          this.tapResult(this.tapRun, t, reason);
        }
        this.tapRun = { id: ++this.nextTapRun, times: [t], inMode: !!this.mode,
          club: this.enabled.tap2, voice: !this.mode && this.enabled.tap4, calm: fromCalm(t) || !!this.mode };
      }
      counted = true;
    }
    if (this.onTapCandidate) {
      // Keep the first strong decision in each impulse, and always report a count.
      if (counted || !this.tapImpulse?.strong) {
        this.noteTap({ t, jump, gm, ...this.tapCandidateContext() }, reason, counted);
      }
      this.tapImpulse = { strong: true };
    }
  }
  tapCandidateContext() {
    const run = this.tapRun || this.cand?.tapRun;
    return { countAfter: run?.times.length ?? 0, sequenceId: run?.id ?? null,
      gesture: this.cand?.tapRun ? this.cand.name : run ? this.tapGesture(run) : this.mode ? "tap2" : null };
  }
  tapGesture(run, ended = false) {
    if (!run.voice) return "tap2";
    if (!run.club || run.times.length > tap.clubCount) return "tap4";
    return ended && run.times.length === tap.clubCount ? "tap2" : null;
  }
  noteTap({ t, jump, gm, ...context }, rejectReason, counted = false) {
    const gapMs = this.lastTapCandidate === null ? null : ms(t - this.lastTapCandidate);
    this.lastTapCandidate = t;
    this.onTapCandidate(t, { peak: +jump.toFixed(3), handGyroDps: +gm.toFixed(1), gapMs, ...context, rejectReason }, counted);
  }
  tapResult(run, t, outcome, gesture = null) {
    if (run) {
      this.onTapSequence?.(t, { sequenceId: run.id, gesture: gesture ?? this.tapGesture(run, true),
        countReached: run.times.length, durationMs: ms(t - run.times[0]), outcome });
    }
  }
  dialNote(d, why, dur = null, straight = null) {
    this.dialLog.push({ why, ang: d.ang.map((x) => Math.round(x)), mag: Math.round(Math.hypot(...d.ang)), peak: Math.round(d.peak),
      dur: dur === null ? null : +dur.toFixed(2), straight: straight === null ? null : +straight.toFixed(2), accDev: +d.accDev.toFixed(2) });
    if (this.dialLog.length > 12) this.dialLog.shift();
    if (this.onDialNote) this.onDialNote(this.dialLog[this.dialLog.length - 1]);
  }
  fire(name, t) {
    this.tapResult(this.cand?.tapRun, t, "completed", name);
    this.tapResult(this.tapRun, t, "other");
    this.cand = null; this.calmSince = null; this.cool = t + tap.cooldownMs / 1000; this.last = { name, t };
    this.gyroX = [null, null, null]; this.accX = [null, null, null]; this.tapRun = null;
    this.on({ name, t });
  }
}
