// Runs the phone page's swing analysis (phone/swing.js) on a page-format log and compares it with the truth and
// with swing_eye.py's numbers ("expected", written by sim_to_page_log.py). Frames and clip arrivals are replayed in
// phone-time order, as the page would see them. A real log without "expected" just prints the swings.
//   node test_swing_js.mjs LOG.json [path/to/swing.js]
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
import { ClockFit } from "../phone/glove.js";

const [logPath, swingPath] = process.argv.slice(2);
const { analyse, SwingDetector, swingLine, swingPhasePose } = await import(swingPath ? pathToFileURL(swingPath).href : "../phone/swing.js");
const log = JSON.parse(readFileSync(logPath, "utf8"));
const G = 70e-3, A = 0.488e-3;
const events = log.glove.map((f) => [f[0], "f", f]).concat((log.clips || []).filter((c) => c.kind === "impact").map((c) => [c.lastNow, "c", c]));
events.sort((x, y) => x[0] - y[0]);
const found = [];
const det = new SwingDetector((s) => found.push(s));
for (const [, kind, x] of events) {
  if (kind === "c") { det.sound(x.t_us / 1e6); continue; }
  const v = x.slice(3).map((r, j) => r * ([0, 1, 2, 6, 7, 8].includes(j) ? G : A));
  det.frame([x[2] / 1e6, ...v]);
}
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : v.toFixed(d));
console.log(`${found.length} swings found` + (log.truth ? ` of ${log.truth.length}` : ""));
const exp = log.expected || [];
const rows = [];
for (const s of found) {
  const e = exp.find((q) => Math.abs(q.t_s - s.t_imp) < 0.1);
  rows.push({ s, e });
  console.log(`#${s.n} ${e ? e.kind.padEnd(5) : "?    "} src=${s.source.padEnd(5)} dt=${e ? fmt((s.t_imp - e.t_s) * 1000, 1) + " ms" : "–"}` +
    `  tempo ${fmt(s.tempo, 2)}${e ? " (py " + fmt(e.tempo, 2) + ", true " + fmt(e.true_tempo, 2) + ")" : ""}` +
    `  release ${fmt(s.release_ms, 0)}${e ? " (py " + fmt(e.release_ms, 0) + ")" : ""} ms` +
    `  hinge top ${fmt(s.hinge_top, 0)}${e ? " (py " + fmt(e.hinge_top_deg, 0) + ")" : ""}` +
    `  hand peak ${fmt(s.hand_dps_peak, 0)}${e ? " (py " + fmt(e.hand_dps_peak, 0) + ")" : ""}  sat ${s.saturated}  ${fmt(s.rate_hz, 0)} Hz`);
  console.log(`     "${swingLine(s)}"  back ${fmt(s.back_s, 3)} down ${fmt(s.down_s, 3)} s` + (e ? `  (py back ${fmt(e.top_s - e.take_s, 3)} down ${fmt(-e.top_s, 3)}; true back ${fmt(e.true_back_s, 3)} down ${fmt(e.true_down_s, 3)} pause ${fmt(e.true_pause_s * 1000, 0)} ms)  arm back ${fmt(s.arm_back_deg, 0)} deg, flat ${fmt(s.pause_ms, 0)} ms` : ""));
}
if (exp.length) {
  const m = rows.filter((r) => r.e);
  const err = (f, g) => m.map((r) => Math.abs(f(r.s) - g(r.e)));
  const med = (v) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : NaN; };
  const max = (v) => Math.max(...v);
  const tT = err((s) => s.tempo, (e) => e.true_tempo), tP = m.map((r) => Math.abs(r.e.tempo - r.e.true_tempo));
  console.log(`|tempo - true| JS median ${fmt(med(tT), 3)} max ${fmt(max(tT), 3)}; Python median ${fmt(med(tP), 3)} max ${fmt(max(tP), 3)} (true top = middle of the pause)`);
  const tE = err((s) => s.tempo / 1, (e) => e.tempo), rE = err((s) => s.release_ms, (e) => e.release_ms), hE = err((s) => s.hinge_top, (e) => e.hinge_top_deg);
  console.log(`matched ${m.length}/${exp.length}; |tempo - py| median ${fmt(med(tE), 3)} max ${fmt(max(tE), 3)}; ` +
    `|release - py| median ${fmt(med(rE), 1)} max ${fmt(max(rE), 1)} ms; |hinge top - py| median ${fmt(med(hE), 1)} max ${fmt(max(hE), 1)} deg`);
  const missed = exp.length - m.length, extra = found.length - m.length;
  if (missed || extra) {
    console.log(`MISSED ${missed}, EXTRA ${extra}`);
    process.exitCode = 1;
  }
  for (const { s } of m) {
    assert.ok(s.t_address < s.t_top && s.t_top < s.t_impact, `swing ${s.n}: phase order`);
    assert.equal(s.t_impact, 0);
    assert.ok(Math.abs(s.t_top + s.down_s) <= 0.02, `swing ${s.n}: top is near pause midpoint`);
    assert.ok(Math.abs(s.t_address + s.back_s + s.down_s) < 1e-9, `swing ${s.n}: address matches tempo`);
    // The simulated follow-through runs for 0.55 s, with a slowing forearm and some added gyro wobble.
    assert.ok(s.t_finish >= 0.3 && s.t_finish <= 0.85, `swing ${s.n}: unexpected finish ${s.t_finish}`);
  }
}

// A brief slowdown and a sensor gap must not count as a full quiet interval.
const frame = (t, arm, hand) => [t, 0, 0, hand, 0, 0, 1, 0, 0, arm, 0, 0, 1];
const impact = 3;
const motion = Array.from({ length: 421 }, (_, i) => {
  const arm = i < 200 ? 0 : i < 275 ? -120 : i <= 308 ? 650 : i < 320 ? 0 : i < 345 ? -120 : 0;
  return frame(i / 100, arm, 2 * arm);
});
const near = (actual, expected) => {
  assert.notEqual(actual, null);
  assert.ok(Math.abs(actual - expected) < 1e-6, `${actual} != ${expected}`);
};
near(analyse(motion, impact).t_finish, 0.45);
assert.equal(analyse(motion.filter((f) => f[0] < 3.59), impact).t_finish, null);
near(analyse(motion.filter((f) => f[0] < 3.55 || f[0] > 3.74), impact).t_finish, 0.75);
assert.equal(analyse(motion, impact, 2290, true).t_finish, null);
const earlySound = [];
const earlyDetector = new SwingDetector((s) => earlySound.push(s));
for (const f of motion) {
  if (f[0] === 3.1) earlyDetector.sound(impact);
  earlyDetector.frame(f);
}
assert.equal(earlySound.length, 1);
assert.equal(earlySound[0].source, "sound");
near(earlySound[0].t_finish, 0.45);

// A waggle can cross the forearm trigger without producing a swing or any phases.
const waggles = [];
const waggleDetector = new SwingDetector((s) => waggles.push(s));
let triggered = false;
for (let i = 0; i <= 600; i++) {
  const rate = i >= 200 && i < 320 ? 650 * Math.sin((i - 200) * Math.PI / 30) : 0;
  waggleDetector.frame(frame(i / 100, rate, rate));
  triggered ||= waggleDetector.pending !== null;
}
assert.ok(triggered, "waggle must exercise the forearm trigger");
assert.deepEqual(waggles, []);

// Phone timestamps include clock drift. Angles use pixel aspect and median address widths.
const clock = new ClockFit();
Object.assign(clock, { a: 0.0001, b: 500, t0: 1000 });
const pose = (time, dx, dy, hip) => {
  const row = [time, ...Array(99).fill(0)];
  const put = (joint, x, y) => row.splice(1 + 3 * joint, 3, x, y, 1);
  put(0, 0.45, 0.3);
  put(12, dx, dy);
  put(15, 0.25, 0.75);
  put(24, hip, 0);
  return row;
};
const sw = { t_imp: 2, t_address: -1, t_top: -0.25, t_impact: 0, t_finish: 0.5 };
const poses = [
  pose(500, 0.2, 0, 0.4), pose(1250, 0.4, 0, 0.3), pose(1400, 0.5, 0, 0.3), pose(1500, 0.6, 0, 0.3),
  pose(2190.1, 0, 0.5, 0.6), pose(2310.1, 0, 0, 0), [2500.1], pose(2501, 0.5, 0, 0.3), pose(3060.3, 0.5, 0, 0.3)
];
const { phases, pose_at } = swingPhasePose(sw, clock, poses, 2);
assert.deepEqual(phases, { address: 1500, top: 2250.1, impact: 2500.1, finish: 3000.2 });
assert.deepEqual(pose_at.top, { frame_index: 4, phone_ms: 2190.1, shoulder_turn_deg: pose_at.top.shoulder_turn_deg,
  hip_turn_deg: 0, head_x: 0.45, lead_wrist_xy: [0.25, 0.75] });
near(pose_at.top.shoulder_turn_deg, 60);
assert.equal(pose_at.address.shoulder_turn_deg, 0);
assert.equal(pose_at.impact, null, "nearest row with no person wins over a more distant pose");
assert.equal(pose_at.finish, null, "60.1 ms is outside the match window");
near(swingPhasePose(sw, clock, [...poses.slice(0, -1), pose(3060.2, 0.5, 0, 0.15)], 2).pose_at.finish.hip_turn_deg, 60);
assert.equal(swingPhasePose({ ...sw, t_address: null }, clock, poses, 2).pose_at.top.shoulder_turn_deg, null);
assert.deepEqual(swingPhasePose(sw, new ClockFit(), poses, 2).phases, { address: null, top: null, impact: null, finish: null });
assert.equal(swingPhasePose({ ...sw, t_finish: null }, clock, poses, 2).phases.finish, null);
console.log("PASS phase timing, waggle rejection, clock mapping, nearest pose and angles");
