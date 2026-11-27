// R10 shots from the R10 Bridge app on the same phone (ws://127.0.0.1:8765), paired with glove swings.
// The app relays the Garmin Golf app's E6 link: one {"type":"shot", shot, t_wall_ms, ball, club} per shot.
// See r10-bridge/README.md.

import { text } from "./strings.js";

export const R10_URL = "ws://127.0.0.1:8765";

// A shot reaches the page a little after the impact (R10 → Garmin app → bridge), and the glove's swing row
// arrives ~2 s after its impact too, so either can come first. A shot pairs with the latest unpaired swing whose
// impact is MIN_LAG_MS..MAX_LAG_MS before the shot's arrival; until then the shot waits up to WAIT_MS.
export const MIN_LAG_MS = 150, MAX_LAG_MS = 8000, WAIT_MS = 6000;

/** Pure pairing step. swings: [{n, impactPhoneMs}], shots: [{arrivalMs, swing}] (swing null = unpaired).
 *  Fills shot.swing / shot.lagMs where possible; returns the shots it paired now. */
export function pairShots(swings, shots, nowMs) {
  const used = new Set(shots.filter((s) => s.swing != null).map((s) => s.swing));
  const paired = [];
  // oldest shot first, so two quick shots take the two swings in order
  for (const s of shots.filter((x) => x.swing == null && !x.gaveUp).sort((a, b) => a.arrivalMs - b.arrivalMs)) {
    let best = null;
    for (const w of swings) {
      if (w.impactPhoneMs == null || used.has(w.n)) continue;
      const lag = s.arrivalMs - w.impactPhoneMs;
      if (lag < MIN_LAG_MS || lag > MAX_LAG_MS) continue;
      if (!best || w.impactPhoneMs > best.impactPhoneMs) best = w;
    }
    if (best) {
      s.swing = best.n; s.lagMs = +(s.arrivalMs - best.impactPhoneMs).toFixed(1);
      used.add(best.n); paired.push(s);
    } else if (nowMs - s.arrivalMs > WAIT_MS) {
      s.gaveUp = true;   // no swing showed up: R10 saw a ball the glove missed, or the glove was off
    }
  }
  return paired;
}

const BRIDGE_STATUS = new Set(["e6Waiting", "e6Error", "garminConnected", "garminDisconnected"]);

function legacyStatus(message) {
  // Older Android builds send just the Korean status string.
  const marker = "\u0000";
  for (const key of BRIDGE_STATUS) {
    const [before, after] = text(key, "ko", marker).split(marker);
    if (message.startsWith(before) && message.endsWith(after)) {
      return [key, message.slice(before.length, message.length - after.length)];
    }
  }
  return ["legacyStatus", message];
}

/** WebSocket client that reconnects on its own. onShot(msg, arrivalMs), onState(key, connected, detail). */
export class R10Link {
  constructor(onShot, onState, url = R10_URL) {
    this.onShot = onShot; this.onState = onState; this.url = url;
    this.ws = null; this.want = false; this.timer = null;
  }
  start() { this.want = true; this.open(); }
  stop() {
    this.want = false; clearTimeout(this.timer);
    if (this.ws) { this.ws.onclose = null; this.ws.close(); this.ws = null; }
    this.onState("r10Off", false);
  }
  open() {
    if (!this.want) return;
    let ws;
    try { ws = new WebSocket(this.url); } catch (e) { this.retry("r10SocketError", e.message); return; }
    this.ws = ws;
    ws.onopen = () => this.onState("r10SocketOpen", true);
    ws.onmessage = (e) => {
      const t = performance.now();
      let m; try { m = JSON.parse(e.data); } catch { return; }
      if (m.type === "shot") this.onShot(m, t);
      else if (m.type === "status") {
        if (BRIDGE_STATUS.has(m.code)) this.onState(m.code, true, m.detail);
        else {
          const [key, detail] = legacyStatus(String(m.text ?? ""));
          this.onState(key, true, detail);
        }
      }
    };
    ws.onclose = () => this.retry("r10Retry");
    ws.onerror = () => {};
  }
  retry(key, detail) {
    this.ws = null;
    if (!this.want) return;
    this.onState(key, false, detail);
    clearTimeout(this.timer); this.timer = setTimeout(() => this.open(), 3000);
  }
}

/** One spoken/printed line for a paired shot. Signs follow the R10 app: + = right of target for a right-hander. */
export function shotLine(m, language = "ko") {
  const b = m.ball || {}, c = m.club || {};
  const t = (key, ...args) => text(key, language, ...args);
  const side = (v, l, r) => Math.abs(v) > 0.5 ? t("directionDegrees", t(v > 0 ? r : l), Math.abs(v).toFixed(0)) : t("straight");
  return t("shotSpoken", (b.BallSpeed ?? 0).toFixed(0), side(b.LaunchDirection ?? 0, "left", "right"),
    side(c.ClubAnglePath ?? 0, "outIn", "inOut"));
}
