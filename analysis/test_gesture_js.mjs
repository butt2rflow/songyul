// Tests the phone page's gesture detector (phone/gesture.js): made-up gestures that must fire, made-up
// motions that must not (waggle, walking, single/triple tap), simulated swings (sim_to_page_log.py logs).
//   node test_gesture_js.mjs [sim logs...]
import { readFileSync } from "node:fs";
import { GestureDetector } from "../phone/gesture.js";
const FS = 240, dt = 1 / FS;
let seed = 7; const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
const noise = (s) => (rnd() - 0.5) * 2 * s;

// frame builder: gravity g (unit, in g), gyro w (deg/s), extra accel e (g)
const fr = (t, g, w = [0, 0, 0], e = [0, 0, 0], arm = [0, 0, 0]) => [t, w[0] + noise(2), w[1] + noise(2), w[2] + noise(2),
  g[0] + e[0] + noise(0.01), g[1] + e[1] + noise(0.01), g[2] + e[2] + noise(0.01), arm[0], arm[1], arm[2], 0, 0, 1];
function seq(parts) {            // parts: [seconds, (tau, t) => [g, w, e]]
  const out = []; let t = 0;
  for (const [dur, fn] of parts) { for (let i = 0; i < dur * FS; i++, t += dt) { const [g, w, e, arm] = fn(i * dt); out.push(fr(t, g, w, e, arm)); } }
  return out;
}
const still = (g = [0, 0, 1]) => [2.0, () => [g, [0, 0, 0], [0, 0, 0]]];
const knock = (tau, at) => { const x = tau - at; return x >= 0 && x < 0.02 ? 2.6 * Math.exp(-x / 0.004) * Math.cos(2 * Math.PI * 180 * x) : 0; };
const taps = (times) => [0.8, (tau) => [[0, 0, 1], [noise(30), noise(30), noise(30)], [0, 0, times.reduce((s, a) => s + knock(tau, a), 0)]]];
const twist = (amp = 520, hz = 2.6, dur = 0.8) => [dur, (tau) => [[0, 0, 1], [0, 0, amp * Math.sin(2 * Math.PI * hz * tau)], [0.3 * Math.sin(2 * Math.PI * hz * tau), 0, 0]]];
const shake = (amp = 2.6, hz = 4, dur = 0.75) => [dur, (tau) => [[0, 0, 1], [80 * Math.sin(2 * Math.PI * hz * tau), 0, 0], [amp * Math.sin(2 * Math.PI * hz * tau), 0, 0]]];
const toPose = [0.5, (tau) => { const k = tau / 0.5, g = [Math.sin(k * Math.PI / 2), 0, Math.cos(k * Math.PI / 2)]; return [g, [0, 180 * Math.sin(Math.PI * k), 0], [0, 0, 0]]; }];
const hold = [1.6, () => [[1, 0, 0], [0, 0, 0], [0, 0, 0]]];
const walk = [6, (tau) => [[0, 0, 1], [60 * Math.sin(2 * Math.PI * 1.8 * tau), 40 * Math.cos(2 * Math.PI * 0.9 * tau), 0], [0.35 * Math.sin(2 * Math.PI * 1.8 * tau), 0, 0.25 * Math.sin(2 * Math.PI * 3.6 * tau)]]];
// dial: one-way wrist roll about x by `deg` in `dur` s (half-sine rate), gravity turning with it
const dial = (deg, dur = 0.4) => { const p = deg * Math.PI / (2 * dur); return [dur, (tau) => { const ang = deg * (1 - Math.cos(Math.PI * tau / dur)) / 2 * Math.PI / 180; return [[0, Math.sin(ang), Math.cos(ang)], [p * Math.sin(Math.PI * tau / dur), 0, 0], [0, 0, 0]]; }]; };
// a dial about a tilted axis, like the real glove (2026-11-13: hand IMU saw x +122 / z -98 deg for one turn)
const dialTilt = (deg, dur = 0.5) => { const [d, fn] = dial(deg, dur); return [d, (tau) => { const [g, w, e] = fn(tau); return [g, [0.78 * w[0], 0.1 * w[0], -0.62 * w[0]], e]; }]; };
// the same dial with the forearm IMU rolling too (it turns with the wrist: ~1.5x the hand rate, > 400 deg/s)
const dialArm = (deg, dur = 0.4) => { const [d, fn] = dial(deg, dur); return [d, (tau) => { const [g, w, e] = fn(tau); return [g, w, e, [1.5 * w[0], 0, 0]]; }]; };
const stillAt = (deg) => [1.0, () => [[0, Math.sin(deg * Math.PI / 180), Math.cos(deg * Math.PI / 180)], [0, 0, 0], [0, 0, 0]]];
const waggle = (amp) => [1.6, (tau) => [[0, 0, 1], [amp * Math.sin(2 * Math.PI * 2.5 * tau), 0, 0], [0.2 * Math.sin(2 * Math.PI * 2.5 * tau), 0, 0]]];

const run = (frames, opts = {}) => { const got = []; const d = new GestureDetector((x) => got.push(x.name === "dial" ? `dial${x.dir > 0 ? "+" : "-"}${x.steps}` : x.name), { holdRef: [1, 0, 0], ...opts }); for (const f of frames) d.frame(f); return got; };
const cases = [
  ["double tap 0.2 s", [still(), taps([0.1, 0.3]), still()], ["tap2"]],
  ["double tap 0.12 s", [still(), taps([0.1, 0.22]), still()], ["tap2"]],
  ["double tap 0.4 s", [still(), taps([0.1, 0.5]), still()], ["tap2"]],
  ["double tap without prior calm", [taps([0.1, 0.3]), still()], []],
  ["twist x2", [still(), twist(), still()], ["twist"]],
  ["gentler twist 460", [still(), twist(460), still()], ["twist"]],
  ["slow twist 2 Hz", [still(), twist(520, 2.0, 1.0), still()], ["twist"]],
  ["shake x3", [still(), shake(), still()], ["shake"]],
  ["hold taught pose", [still(), toPose, hold, still([1, 0, 0])], ["hold"]],
  ["single tap", [still(), taps([0.1]), still()], []],
  ["taps too far apart (0.6 s)", [still(), taps([0.05, 0.7]), still()], []],
  ["walking", [still(), walk, still()], []],
  ["light waggle 200", [still(), waggle(200), still()], []],
  ["firm waggle 350", [still(), waggle(350), still()], []],
  ["twist without calm before", [twist(), twist(), still()], []],
  ["dial +120 in 0.4 s", [still(), dial(120), stillAt(120)], ["dial+1"]],
  ["dial -120 in 0.4 s", [still(), dial(-120), stillAt(-120)], ["dial-1"]],
  ["dial +100 quick 0.3 s", [still(), dial(100, 0.3), stillAt(100)], ["dial+1"]],
  ["dial +150 (a natural turn) = 1 step", [still(), dial(150, 0.6), stillAt(150)], ["dial+1"]],
  ["dial +300 = 2 steps", [still(), dial(300, 1.0), stillAt(300)], ["dial+2"]],
  ["tilted axis +155 then -155", [still(), dialTilt(155), stillAt(0), [0.0, () => [[0, 0, 1], [0, 0, 0], [0, 0, 0]]], dialTilt(-155), stillAt(0)], ["dial+1", "dial-1"]],
  ["tilted axis -155 first, then +155", [still(), dialTilt(-155), stillAt(0), [0.0, () => [[0, 0, 1], [0, 0, 0], [0, 0, 0]]], dialTilt(155), stillAt(0)], ["dial-1", "dial+1"]],
  ["two dials in a row", [still(), dial(120), stillAt(120), [0.0, () => [[0, 0, 1], [0, 0, 0], [0, 0, 0]]], dial(-120), stillAt(0)], ["dial+1", "dial-1"]],
  ["dial +120, forearm IMU 700 deg/s", [still(), dialArm(120), stillAt(120)], ["dial+1"], { armOk: true }],
  ["dial -120, forearm IMU 470 deg/s", [still(), dialArm(-120, 0.6), stillAt(-120)], ["dial-1"], { armOk: true }],
  ["slow 105 in 1.3 s, like after a swing (no dial)", [still(), dial(105, 1.3), stillAt(105)], []],
  ["turn 72 between shots (no dial)", [still(), dial(72, 0.4), stillAt(72)], []],
  ["small turn 45 (no dial)", [still(), dial(45), stillAt(45)], []],
  ["slow turn 2.5 s (no dial)", [still(), dial(120, 2.5), stillAt(120)], []],
  ["dial without calm before", [waggle(200), dial(90), stillAt(90)], []],
  ["four taps = tap4", [still(), taps([0.1, 0.3, 0.5, 0.7]), still()], ["tap4"]],
  ["four taps without prior calm", [taps([0.1, 0.3, 0.5, 0.7]), still()], ["tap4"]],
  ["three taps = nothing", [still(), taps([0.1, 0.3, 0.5]), still()], []],
  ["five taps = nothing", [still(), [1.2, (tau) => taps([0.1, 0.3, 0.5, 0.7, 0.9])[1](tau)], still()], []],
  ["hold without a taught pose", [still(), toPose, hold, still([1, 0, 0])], [], { holdRef: null }],
];
let pass = 0;
for (const [name, parts, want, opts] of cases) {
  const got = run(seq(parts), opts || {});
  const ok = JSON.stringify(got) === JSON.stringify(want);
  pass += ok; console.log(`${ok ? "ok  " : "FAIL"} ${name.padEnd(28)} got ${JSON.stringify(got)}${ok ? "" : " want " + JSON.stringify(want)}`);
}
console.log(`${pass}/${cases.length} made-up cases`);

// Club-change mode: tap2 starts it, the wrist angle sets the stepping speed, tap2 confirms.
{
  const holdAt = (deg, dur) => [dur, () => [[0, Math.sin(deg * Math.PI / 180), Math.cos(deg * Math.PI / 180)], [0, 0, 0], [0, 0, 0]]];
  const turn = (from, to, dur = 0.3) => { const [d, fn] = dial(to - from, dur); return [d, (tau) => fn(tau)]; };
  const parts = [still(), taps([0.1, 0.3]), holdAt(0, 1.2),                 // tap2 -> mode on (bias taken while still)
    turn(0, 35), holdAt(35, 3.0),                                            // small turn: slow steps (every 0.9 s)
    turn(35, 0), holdAt(0, 1.0),                                             // back to the middle: no steps
    turn(0, -120, 0.5), holdAt(-120, 1.0),                                   // big turn the other way: fast steps (every 0.2 s)
    turn(-120, 0, 0.5), holdAt(0, 1.6),
    taps([0.1, 0.3, 0.5, 0.7]), holdAt(0, 1.5),                            // four taps inside the mode cannot start voice
    taps([0.1, 0.3]), holdAt(0, 1.5)];                                    // tap2 -> confirm and leave
  const ev = [], candidates = [], runs = []; let d;
  d = new GestureDetector((x) => {
    ev.push(x);
    if (x.name === "tap2") { if (d.mode) d.stopClubMode(); else d.startClubMode(x.t); }
  }, { dialAxis: [1, 0, 0], onTapCandidate: (_, row, counted) => { if (counted) candidates.push(row); },
    onTapSequence: (_, row) => runs.push(row) });
  for (const f of seq(parts)) d.frame(f);
  const names = ev.map((x) => x.name === "clubstep" ? (x.dir > 0 ? "+" : "-") : x.name);
  const plus = names.filter((x) => x === "+").length, minus = names.filter((x) => x === "-").length;
  const ok = names.filter((n) => n.startsWith("tap")).join() === "tap2,tap2" && names[0] === "tap2" && names.at(-1) === "tap2"
    && plus >= 3 && plus <= 5 && minus >= 5 && minus <= 9 && !d.mode
    && runs.filter((r) => r.countReached >= 2).map((r) => `${r.gesture}/${r.countReached}/${r.outcome}`).join()
      === "tap2/2/completed,tap2/4/timeout,tap2/2/completed"
    && candidates.slice(2).every((r) => r.gesture === "tap2" && r.sequenceId > runs[0].sequenceId);
  pass += ok; console.log(`${ok ? "ok  " : "FAIL"} club mode: ${plus} slow + steps (want 3-5), ${minus} fast - steps (want 5-9), ends off: ${!d.mode}  ${names.join(" ")}`);
  // a wrist resting near the edge (wobbling 15-24 deg) must not flick the club back and forth
  {
    const ev3 = []; const d3 = new GestureDetector((x) => { ev3.push(x.name === "clubstep" ? (x.dir > 0 ? "+" : "-") : x.name); if (x.name === "tap2") d3.startClubMode(x.t); }, { dialAxis: [1, 0, 0] });
    const wob = [3.0, (tau) => [[0, 0, 1], [60 * Math.cos(2 * Math.PI * 0.8 * tau), 0, 0], [0, 0, 0]]];   // +-12 deg around ~20
    for (const f of seq([still(), taps([0.1, 0.3]), holdAt(0, 1.2), turn(0, 20), holdAt(20, 0.3), wob, holdAt(20, 1)])) d3.frame(f);
    const steps = ev3.filter((x) => x === "+" || x === "-");
    const flips = steps.filter((x, i) => i && x !== steps[i - 1]).length;
    const ok3 = flips === 0; pass += ok3;
    console.log(`${ok3 ? "ok  " : "FAIL"} no flicking at the edge: ${steps.join("") || "(none)"}`);
  }
  // a swing inside the mode ends it
  const ev2 = [], afterSwing = [];
  const d2 = new GestureDetector((x) => { ev2.push(x.name); if (x.name === "tap2") d2.startClubMode(x.t); },
    { dialAxis: [1, 0, 0], onTapCandidate: (_, row) => { if (row.rejectReason === "after_swing_holdoff") afterSwing.push(row); } });
  for (const f of seq([still(), taps([0.1, 0.3]), holdAt(0, 1.2), [0.3, () => [[0, 0, 1], [1500, 0, 0], [0, 0, 0]]],
    taps([0.1, 0.3, 0.5, 0.7]), holdAt(0, 1.5)])) d2.frame(f);
  const ok2 = ev2.includes("clubmode") && !ev2.includes("tap4") && !d2.mode && afterSwing.length >= 4; pass += ok2;
  console.log(`${ok2 ? "ok  " : "FAIL"} swing ends club mode and locks taps: ${JSON.stringify(ev2)}`);
}

// simulated swings (hand IMU only, like the spare XIAO; then with the arm IMU)
const G = 70e-3, Ac = 0.488e-3;
const conv = (x) => [x[2] / 1e6, ...x.slice(3).map((r, j) => r * ([0, 1, 2, 6, 7, 8].includes(j) ? G : Ac))];
for (const p of process.argv.slice(2)) {
  const log = JSON.parse(readFileSync(p, "utf8"));
  const f = log.glove.map(conv);
  const handOnly = run(f.map((x) => x.slice(0, 7).concat([0, 0, 0, 0, 0, 0])));
  const withArm = run(f, { armOk: true });
  console.log(`${p.split("/").pop()}: ${log.truth.length} swings -> gestures hand-only ${JSON.stringify(handOnly)}, with arm IMU ${JSON.stringify(withArm)}` +
    (handOnly.length ? "  (sim waggles rotate the hand about the shoulder radius: ~4 g, a real one ~0.5 g; check with real practice swings)" : ""));
}
if (pass !== cases.length + 3) process.exitCode = 1;
