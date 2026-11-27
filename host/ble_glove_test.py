"""Test the SensorGlove from the PC's own Bluetooth (no receiver XIAO): IMU rate ceiling and mic clips.

  python ble_glove_test.py rate                      # 200, 400, 600, 800 Hz, 8 s each
  python ble_glove_test.py rate --hz 200 300 --seconds 15
  python ble_glove_test.py mic --seconds 60 --out clips/   # swing + clap = impact clip; double-tap + speak = voice clip

Protocol (xiao_ble_glove.ino): data notifications are
  IMU    : seq u32, n u8 (1..8), armOk u8, then n frames of t_us u32 + 12 x i16
  status : seq u32, 0, armOk, vbat u16, charging u8, dropped u32, hz u16
  clip   : id u16, chunk u16, 0xFE, kind (0 impact, 1 voice); chunk 0 = t_us u32, pre u16, total u16, rate u16, peak u16,
           chunks 1.. = int16 samples
ctrl writes: "probe", "start <hz> <batch> <mic>", "stop", "status".
"""
import argparse, asyncio, pathlib, struct, sys, time, wave
import numpy as np
from bleak import BleakClient, BleakScanner

DATA = "7e5a0002-2f3b-4c1d-9a8e-0b1c2d3e4f50"
CTRL = "7e5a0003-2f3b-4c1d-9a8e-0b1c2d3e4f50"
GYRO_DPS = 70e-3


class Rx:
    def __init__(self):
        self.reset()
        self.probe_len = None

    def reset(self):
        self.frames = 0; self.missing = 0; self.next_seq = None; self.packets = 0
        self.status = []; self.clips = {}; self.max_hand = 0.0; self.max_arm = 0.0; self.t_first = None
        self.stream = []   # (glove t_us, hand gx gy gz, arm gx gy gz) raw, for checking motion clips

    def on(self, _, d: bytearray):
        if getattr(self, "raw", None) is not None: self.raw.append((time.time(), bytes(d)))
        if self.probe_len is None and len(d) > 30 and d[:8] == bytes(range(8)):
            self.probe_len = len(d); return
        if len(d) < 6:
            return
        n = d[4]
        if n == 0xFE:
            cid, ch = struct.unpack_from("<HH", d); kind = {1: "voice", 2: "motion"}.get(d[5], "impact")
            c = self.clips.setdefault((kind, cid), {"parts": {}, "kind": kind, "seen": time.time()})
            if ch == 0 and len(d) >= 18:
                c["t_us"], c["pre"], c["total"], c["rate"], c["peak"] = struct.unpack_from("<IHHHH", d, 6)
            else:
                c["parts"][ch] = np.frombuffer(bytes(d[6:]), "<i2")
            return
        if n == 0:
            if len(d) >= 15:
                mv, chg, dropped, hz = struct.unpack_from("<HBIH", d, 6)
                self.status.append((mv, chg, dropped, hz))
            return
        seq = struct.unpack_from("<I", d)[0]
        if self.next_seq is not None and seq != self.next_seq:
            self.missing += (seq - self.next_seq) % 2**32
        self.next_seq = (seq + n) % 2**32
        self.packets += 1; self.frames += n
        if self.t_first is None:
            self.t_first = time.time()
        for i in range(n):
            off = 6 + 28 * i
            if off + 28 > len(d):
                break
            v = struct.unpack_from("<12h", d, off + 4)
            self.stream.append((struct.unpack_from("<I", d, off)[0],) + v[0:3] + v[6:9])
            self.max_hand = max(self.max_hand, max(abs(x) for x in v[0:3]) * GYRO_DPS)
            self.max_arm = max(self.max_arm, max(abs(x) for x in v[6:9]) * GYRO_DPS)


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stream import Take   # same clip assembly as the recorder: chunks placed by number, up to 2 lost chunks left silent


def motion_frames(c):
    """Kind-2 clip -> (t_us per frame, N x 6 int16, nominal rate). Per-frame times come from the glove."""
    t, f = Take.motion_frames(c)
    return t, f, c["rate"] / 10.0


def motion_done(c):
    return Take.motion_done(c)


def report_motion(c, rx, out, when):
    """Check a motion clip against the live stream of the same gyro: same shape, no time offset."""
    t, f, rate = motion_frames(c)
    np.save(out / f"motion_{c['id']:03d}.npy", np.column_stack([t, f]))
    hand = np.linalg.norm(f[:, 0:3], axis=1) * GYRO_DPS
    st = np.array(rx.stream, float)
    steps = np.diff(t) if len(t) > 1 else np.zeros(1)
    msg = f"  {when:5.1f}s motion clip {c['id']}: {len(f)} frames ({rate:.1f} Hz chip), {(t[-1] - t[0]) / 1000:.0f} ms, " \
          f"largest gap {steps.max() / 1000:.1f} ms, hand gyro peak {hand.max():.0f} dps at {(t[hand.argmax()] - t[c['pre']]) / 1000:+.1f} ms from impact"
    if len(st) > 20:
        w = (st[:, 0] > t[0] - 2e5) & (st[:, 0] < t[-1] + 2e5)
        if w.sum() > 20:
            ss = np.linalg.norm(st[w, 1:4], axis=1) * GYRO_DPS
            best = None
            for lag in range(-30000, 30001, 250):            # us: shift the 833 Hz trace, compare with the stream
                y = np.interp(st[w, 0], t + lag, hand, left=np.nan, right=np.nan); ok = ~np.isnan(y)
                if ok.sum() > 10 and np.std(y[ok]) > 0 and np.std(ss[ok]) > 0:
                    r = np.corrcoef(y[ok], ss[ok])[0, 1]
                    if best is None or r > best[1]: best = (lag, r)
            if best: msg += f"; vs the {w.sum()}-frame stream: best shift {best[0] / 1000:+.2f} ms, r = {best[1]:.3f}"
    print(msg)


def clip_audio(c):
    parts = {k: bytes(v.tobytes()) for k, v in c["parts"].items()}
    cc = dict(c, parts=parts)
    return Take.clip_samples(cc) if Take.clip_done(cc) else None


async def connect():
    print("scanning for SensorGlove ...")
    dev = await BleakScanner.find_device_by_name("SensorGlove", timeout=15)
    if not dev:
        sys.exit("SensorGlove not found: is the blue LED blinking? Press RST to wake it.")
    return dev


async def run(a):
    rx = Rx()
    async with BleakClient(await connect()) as c:
        try:   # BlueZ: AcquireNotify (a socket) instead of D-Bus StartNotify, which merges/loses notifications at ~100/s
            await c.start_notify(DATA, rx.on, bluez={"use_start_notify": False})
        except TypeError:   # other OS backends
            await c.start_notify(DATA, rx.on)
        await c.write_gatt_char(CTRL, b"probe", response=False)
        await asyncio.sleep(1.0)
        got = rx.probe_len or 20
        batch = a.batch or max(1, min(8, (got - 6) // 28))
        print(f"connected; probe: {got} of 244 bytes arrive -> {batch} frames per packet")

        if a.mode == "rate":
            print(f"{'Hz':>5} {'frames':>7} {'got Hz':>7} {'missing':>8} {'glove dropped':>14}  battery")
            for hz in a.hz:
                rx.reset()
                await c.write_gatt_char(CTRL, f"start {hz} {batch} 0".encode(), response=False)
                await asyncio.sleep(a.seconds)
                await c.write_gatt_char(CTRL, b"stop", response=False)
                await asyncio.sleep(0.5)
                dur = a.seconds
                dropped = rx.status[-1][2] if rx.status else -1
                mv = rx.status[-1][0] if rx.status else 0
                print(f"{hz:>5} {rx.frames:>7} {rx.frames / dur:>7.1f} {rx.missing:>8} {dropped:>14}  {mv} mV")
            return

        if a.mode == "listen":   # no hands needed: the PC asks for voice clips and counts what arrives
            rx.reset()
            await c.write_gatt_char(CTRL, f"start {a.mic_hz} {batch} 1".encode(), response=False)
            await asyncio.sleep(1.5)
            for _ in range(a.clips):
                await c.write_gatt_char(CTRL, b"listen", response=False)
                await asyncio.sleep(a.gap)
            await c.write_gatt_char(CTRL, b"stop", response=False)
            await asyncio.sleep(0.5)
            for (kind, cid), cl in sorted(rx.clips.items()):
                need = 1 + -(-cl.get("total", 0) // max(1, max([len(v) for v in cl["parts"].values()] or [1])))
                have = len(cl["parts"]) + ("total" in cl)
                miss = sorted(set(range(1, need)) - set(cl["parts"]))
                print(f"{kind} clip {cid}: {have} of {need} chunks" + (f", missing {miss[:12]}{' ...' if len(miss) > 12 else ''}" if miss else ", complete"))
            print(f"IMU frames {rx.frames}, missing {rx.missing}; glove dropped {rx.status[-1][2] if rx.status else '?'}")
            return

        out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
        rx.raw = []   # every notification, saved as raw.pkl for checking
        await c.write_gatt_char(CTRL, f"start {a.mic_hz} {batch} 1".encode(), response=False)
        print(f"recording {a.seconds:.0f} s at {a.mic_hz} Hz with the mic on:")
        print("  impact: swing the forearm fast (> 400 dps) and clap or hit something at the end of the swing")
        print("  voice : hold still 1 s, double-tap the back of the hand (blue LED on), then speak for 2.5 s")
        saved = set(); t0 = time.time()
        while time.time() - t0 < a.seconds:
            await asyncio.sleep(0.25)
            for key, cl in rx.clips.items():
                if key in saved:
                    continue
                if key[0] == "motion":
                    if motion_done(cl):
                        saved.add(key); report_motion(dict(cl, id=key[1]), rx, out, time.time() - t0)
                    continue
                s = clip_audio(cl)
                if s is None:
                    continue
                saved.add(key)
                kind, cid = key
                f = out / f"{kind}_{cid:03d}.wav"
                with wave.open(str(f), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(cl["rate"]); w.writeframes(s[:cl["total"]].astype("<i2").tobytes())
                rms = float(np.sqrt(np.mean(s.astype(float) ** 2)))
                lost = Take.clip_missing(dict(cl, parts={k: bytes(v.tobytes()) for k, v in cl["parts"].items()}))[0]
                print(f"  {time.time() - t0:5.1f}s {kind} clip {cid}: {cl['total']} samples at {cl['rate']} Hz, lost chunks {lost}, "
                      f"peak {cl.get('peak', 0)}, max |x| {int(np.abs(s).max())}, rms {rms:.0f} -> {f}")
        await c.write_gatt_char(CTRL, b"stop", response=False)
        await asyncio.sleep(0.5)
        import pickle; pickle.dump(rx.raw, open(out / "raw.pkl", "wb"))
        part = [k for k in rx.clips if k not in saved]
        print(f"frames {rx.frames}, missing {rx.missing}, max |gyro| hand {rx.max_hand:.0f} / arm {rx.max_arm:.0f} dps (2293 = saturated), "
              f"clips saved {len(saved)}, incomplete {len(part)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["rate", "mic", "listen"])
    ap.add_argument("--hz", type=int, nargs="+", default=[200, 400, 600, 800])
    ap.add_argument("--batch", type=int, default=0, help="frames per packet (default: as many as the probe allows)")
    ap.add_argument("--mic-hz", type=int, default=200)
    ap.add_argument("--seconds", type=float, default=8)
    ap.add_argument("--out", default="clips")
    ap.add_argument("--gap", type=float, default=6, help="listen mode: seconds between clips")
    ap.add_argument("--clips", type=int, default=3, help="listen mode: voice clips triggered from the PC")
    asyncio.run(run(ap.parse_args()))
