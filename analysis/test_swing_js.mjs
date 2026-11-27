// Runs the phone page's swing analysis (phone/swing.js) on a page-format log and compares it with the truth and
// with swing_eye.py's numbers ("expected", written by sim_to_page_log.py). Frames and clip arrivals are replayed in
// phone-time order, as the page would see them. A real log without "expected" just prints the swings.
//   node test_swing_js.mjs LOG.json [path/to/swing.js]
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const [logPath, swingPath] = process.argv.slice(2);
const { SwingDetector, swingLine } = await import(swingPath ? pathToFileURL(swingPath).href : "../phone/swing.js");
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
}
