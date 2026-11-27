#!/usr/bin/env python3
"""Record from xiao_usb_stream (USB) or xiao_ble_receiver (BLE glove via a USB dongle XIAO) into one .npz.

  python3 stream.py /dev/ttyACM0 --seconds 10 --hz 400 --mic --out take.npz
  python3 stream.py /dev/ttyACM0 --info
  python3 stream.py --list                 # show serial ports
  python3 stream.py --selftest             # parser test with synthetic packets, no board needed

npz keys: t (s, board clock), seq, hand_gyro (dps, N x 3), hand_acc (g), arm_gyro, arm_acc, arm_ok,
audio (int16, 16 kHz) and audio_first (sample index of audio[0]), status (t, vbat_mV, charging, hz, dropped, mtu),
and from the BLE glove: clip_audio (n x 8000 int16, 0.25 s before + after each impact), clip_t (impact time, same clock as t),
clip_peak.
Needs pyserial and numpy.
"""
import argparse
import struct
import sys
import time

ACC, GYR = 0.488e-3, 70e-3  # g per LSB at +-16 g, dps per LSB at +-2000 dps
SYNC = b"\xa5\x5a"


class Parser:
    """Feed bytes, get (type, payload) tuples. Resyncs on bad sums and counts them."""

    def __init__(self):
        self.buf = bytearray(); self.bad = 0

    def feed(self, data):
        self.buf += data; out = []
        while True:
            i = self.buf.find(SYNC)
            if i < 0:
                del self.buf[:-1]; return out
            if i:
                del self.buf[:i]
            if len(self.buf) < 5:
                return out
            typ, n = self.buf[2], self.buf[3] | self.buf[4] << 8
            if n > 4096:
                self.bad += 1; del self.buf[:2]; continue
            if len(self.buf) < 7 + n:
                return out
            body = bytes(self.buf[5:5 + n]); s = self.buf[5 + n] | self.buf[6 + n] << 8
            if (typ + self.buf[3] + self.buf[4] + sum(body)) & 0xFFFF != s:
                self.bad += 1; del self.buf[:2]; continue
            out.append((typ, body)); del self.buf[:7 + n]


class Take:
    def __init__(self):
        self.imu, self.audio, self.status, self.text, self.clips = [], [], [], [], {}

    def add(self, typ, p):
        if typ == 1 and len(p) == 33:
            seq, t, fl = struct.unpack_from("<IIB", p); v = struct.unpack_from("<12h", p, 9)
            self.imu.append((seq, t, fl, v))
        elif typ == 2:
            first, t = struct.unpack_from("<II", p); self.audio.append((first, p[8:]))
        elif typ == 3 and len(p) == 15:
            self.status.append(struct.unpack("<IHBHIH", p))
        elif typ == 5 and len(p) >= 6 and p[4] == 0xFE:
            cid, ch = struct.unpack_from("<HH", p); kind = {1: "voice", 2: "motion"}.get(p[5], "impact")
            c = self.clips.setdefault((kind, cid), {"parts": {}, "kind": kind, "id": cid})
            if ch == 0:
                c["t_us"], c["pre"], c["total"], c["rate"], c["peak"] = struct.unpack_from("<IHHHH", p, 6)
            else:
                c["parts"][ch] = p[6:]
            if self.clip_done(c) and not c.get("reported"):
                c["reported"] = True
                return c
        elif typ == 4:
            s = p.decode("utf-8", "replace"); self.text.append(s); print("board:", s)

    @staticmethod
    def clip_missing(c):
        """Chunk numbers not received (BLE loses about 1 in 1500 chunks even at 20 ms pacing)."""
        if "total" not in c or not c["parts"]:
            return None
        per = max(len(x) for x in c["parts"].values()) // 2
        n = -(-c["total"] // per)
        return [k for k in range(1, n + 1) if k not in c["parts"]], n

    # ---- motion clips (kind 2): 833 Hz gyro around an impact; chunk 0 = t_us u32, impact frame u16, frames u16,
    # rate x10 u16, flags u16 (bit0 arm, bit1 per-frame times); chunks 1.. = 14-byte frames: dt u16 (10 us), 6 x i16
    @staticmethod
    def motion_frames(c):
        """-> (t_us per frame, N x 6 raw int16 hand gx gy gz arm gx gy gz). Lost chunks simply leave their frames out."""
        import numpy as np
        rows = []
        for k in sorted(c["parts"]):
            b = bytes(c["parts"][k]); b = b[:len(b) // 14 * 14]
            if b: rows.append(np.frombuffer(b, np.dtype([("dt", "<u2"), ("g", "<i2", 6)])))
        if not rows:
            return np.zeros(0), np.zeros((0, 6), np.int16)
        f = np.concatenate(rows)
        return c["t_us"] + f["dt"].astype(float) * 10, f["g"]

    @classmethod
    def motion_done(cls, c):
        if "total" not in c or not c["parts"]:
            return False
        got = sum(len(bytes(x)) // 14 for x in c["parts"].values())
        per = max(len(bytes(x)) // 14 for x in c["parts"].values()) or 1
        last = -(-c["total"] // per)
        return got >= c["total"] or (last in c["parts"] and c["total"] - got <= 2 * per)   # <= 2 chunks lost

    @classmethod
    def clip_done(cls, c):
        if c.get("kind") == "motion":
            return cls.motion_done(c)
        m = cls.clip_missing(c)
        return m is not None and (m[1] in c["parts"] or not m[0]) and len(m[0]) <= 2  # last chunk seen; <= 2 gaps

    @staticmethod
    def clip_samples(c):
        import numpy as np
        per = max(len(x) for x in c["parts"].values()) // 2
        out = np.zeros(c["total"], "<i2")   # a lost chunk stays silent instead of shifting later samples
        for k, x in c["parts"].items():
            a = np.frombuffer(x, "<i2"); s0 = (k - 1) * per
            out[s0:s0 + len(a)] = a[:max(0, c["total"] - s0)]
        return out

    def arrays(self):
        import numpy as np
        d = {}
        if self.imu:
            seq = np.array([r[0] for r in self.imu]); t = np.array([r[1] for r in self.imu], float)
            t = np.unwrap(t / 2**32 * 2 * np.pi) / (2 * np.pi) * 2**32 / 1e6  # micros() wraps every ~71 min
            v = np.array([r[3] for r in self.imu], float)
            d.update(seq=seq, t=t - t[0], hand_gyro=v[:, 0:3] * GYR, hand_acc=v[:, 3:6] * ACC,
                     arm_gyro=v[:, 6:9] * GYR, arm_acc=v[:, 9:12] * ACC,
                     arm_ok=np.array([r[2] & 1 for r in self.imu], bool), via_ble=bool(self.imu[0][2] & 2))
        if self.audio:
            d["audio_first"] = self.audio[0][0]
            d["audio"] = np.frombuffer(b"".join(a for _, a in self.audio), "<i2")
        if self.status:
            d["status"] = np.array(self.status, float)
        done = [c for c in self.clips.values() if self.clip_done(c)]
        t0 = self.imu[0][1] if self.imu else 0
        imp = [c for c in done if c["kind"] == "impact"]; voi = [c for c in done if c["kind"] == "voice"]
        if imp:
            d["clip_audio"] = np.stack([self.clip_samples(c) for c in imp])
            d["clip_t"] = np.array([((c["t_us"] - t0) % 2**32) / 1e6 for c in imp])
            d["clip_peak"] = np.array([c["peak"] for c in imp])
        if voi:
            d["voice_audio"] = np.stack([self.clip_samples(c) for c in voi])  # 8 kHz
            d["voice_t"] = np.array([((c["t_us"] - t0) % 2**32) / 1e6 for c in voi])
        mot = [c for c in done if c["kind"] == "motion"]
        if mot:   # all motion clips back to back; motion_id says which clip a frame belongs to
            ts, gs, ids, imps = [], [], [], []
            for c in mot:
                tm, g = self.motion_frames(c)
                ts.append(((tm - t0) % 2**32) / 1e6); gs.append(g.astype(float)); ids.append(np.full(len(g), c.get("id", 0)))
                imps.append(ts[-1][min(c["pre"], len(ts[-1]) - 1)] if len(ts[-1]) else np.nan)
            g = np.concatenate(gs)
            d.update(motion_t=np.concatenate(ts), motion_hand_gyro=g[:, 0:3] * GYR, motion_arm_gyro=g[:, 3:6] * GYR,
                     motion_id=np.concatenate(ids), motion_impact_t=np.array(imps), motion_rate=np.array([c["rate"] / 10 for c in mot]))
        d["clips_incomplete"] = len(self.clips) - len(done)
        return d

    def report(self, bad):
        a = self.arrays()
        if "t" in a and len(a["t"]) > 1:
            gaps = int((a["seq"][-1] - a["seq"][0] + 1) - len(a["seq"]))
            print(f"IMU: {len(a['t'])} frames over {a['t'][-1]:.2f} s = {(len(a['t']) - 1) / a['t'][-1]:.0f} Hz, "
                  f"missing {gaps}, arm IMU {'yes' if a['arm_ok'].any() else 'no'}, via {'BLE' if a['via_ble'] else 'USB'}")
            print(f"  hand |gyro| max {abs(a['hand_gyro']).max():.0f} dps, arm |gyro| max {abs(a['arm_gyro']).max():.0f} dps "
                  f"(2293 = saturated), hand |acc| max {abs(a['hand_acc']).max():.1f} g")
        if "audio" in a:
            print(f"audio: {len(a['audio'])} samples = {len(a['audio']) / 16000:.2f} s")
        if "status" in a:
            s = a["status"][-1]
            print(f"status: battery {s[1]:.0f} mV, charging {bool(s[2])}, {s[3]:.0f} Hz set, dropped {s[4]:.0f}, packet {s[5]:.0f} B")
        if "motion_t" in a:
            print(f"motion clips (833 Hz gyro): {len(a['motion_impact_t'])}, {len(a['motion_t'])} frames")
        if "clip_t" in a or a.get("clips_incomplete"):
            if "voice_t" in a:
                print(f"voice clips: {len(a['voice_t'])}")
            print(f"impact sounds: {len(a.get('clip_t', []))} clips" + (f", {a['clips_incomplete']} incomplete" if a["clips_incomplete"] else "")
                  + (" at " + ", ".join(f"{x:.2f}" for x in a["clip_t"]) + " s" if "clip_t" in a else ""))
        print(f"bad packets: {bad}")
        return a


def selftest():
    import numpy as np
    def pkt(typ, p):
        n = len(p); s = (typ + (n & 255) + (n >> 8) + sum(p)) & 0xFFFF
        return SYNC + bytes([typ, n & 255, n >> 8]) + p + struct.pack("<H", s)
    stream = bytearray(b"\x00junk\xa5")
    for i in range(400):
        if i == 200:  # a corrupted packet between two good ones must be skipped, not break its neighbours
            bad = bytearray(pkt(1, b"\x00" * 33)); bad[-1] ^= 0xFF; stream += bad
        stream += pkt(1, struct.pack("<IIB12h", i, 1000 + 2500 * i, 1, *([700, 0, -700, 2048, 0, 0] * 2)))
        if i % 16 == 0:
            stream += pkt(2, struct.pack("<II", i * 256, 0) + b"\x01\x00" * 256)
    stream += pkt(3, struct.pack("<IHBHIH", 0, 3900, 1, 400, 0, 0))
    clip = (np.arange(8000) % 100).astype("<i2").tobytes()  # one 8000-sample impact clip in 112-sample chunks, impact at t = 0.5 s
    stream += pkt(5, struct.pack("<HHBB", 1, 0, 0xFE, 0) + struct.pack("<IHHHH", 1000 + 500000, 4000, 8000, 16000, 20000))
    for k in range(0, 8000, 112):
        stream += pkt(5, struct.pack("<HHBB", 1, 1 + k // 112, 0xFE, 0) + clip[2 * k:2 * (k + 112)])
    voice = (np.arange(20000) % 50).astype("<i2").tobytes()  # a voice clip with the same id: must not mix with the impact clip
    stream += pkt(5, struct.pack("<HHBB", 1, 0, 0xFE, 1) + struct.pack("<IHHHH", 2000000, 0, 20000, 8000, 0))
    for k in range(0, 20000, 112):
        stream += pkt(5, struct.pack("<HHBB", 1, 1 + k // 112, 0xFE, 1) + voice[2 * k:2 * (k + 112)])
    pr, tk = Parser(), Take()
    for k in range(0, len(stream), 61):  # arbitrary chunking like a serial port
        for typ, p in pr.feed(bytes(stream[k:k + 61])):
            tk.add(typ, p)
    a = tk.report(pr.bad)
    assert len(a["t"]) == 400 and abs(a["hand_gyro"][0, 0] - 49.0) < 1e-6 and abs(a["hand_acc"][0, 0] - 0.999424) < 1e-6
    assert len(a["audio"]) == 25 * 256 and pr.bad >= 1 and a["status"][0][1] == 3900
    assert a["voice_audio"].shape == (1, 20000) and a["voice_audio"][0, 7] == 7
    assert a["clip_audio"].shape == (1, 8000) and a["clip_audio"][0, 150] == 50 and abs(a["clip_t"][0] - 0.5) < 1e-9
    import struct as _s
    fr = b"".join(_s.pack("<H6h", i * 115 + (500 if i >= 10 else 0), i, 0, 0, -i, 0, 0) for i in range(20))  # 50 ms gap after frame 9
    mc = {"kind": "motion", "id": 3, "t_us": 1_000_000, "pre": 5, "total": 20, "rate": 8690, "peak": 3, "parts": {1: fr[:14 * 15], 2: fr[14 * 15:]}}
    assert Take.motion_done(mc); tm, g = Take.motion_frames(mc)
    assert len(tm) == 20 and tm[9] == 1_000_000 + 9 * 1150 and tm[10] - tm[9] == 6150 and g[12, 0] == 12 and g[12, 3] == -12
    gap = {"total": 300, "parts": {1: b"\x01\x00" * 112, 3: b"\x05\x00" * 76}}  # chunk 2 lost in the air
    assert Take.clip_done(gap) and Take.clip_missing(gap)[0] == [2]
    g = Take.clip_samples(gap); assert len(g) == 300 and g[111] == 1 and g[112] == 0 and g[223] == 0 and g[224] == 5
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", nargs="?")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--hz", type=int, default=400)
    ap.add_argument("--mic", action="store_true", help="USB board: record the mic live. BLE receiver: get a 0.5 s impact sound clip after each swing")
    ap.add_argument("--out")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    import serial
    if a.list:
        from serial.tools import list_ports
        for p in list_ports.comports():
            print(p.device, p.description, p.vid and f"{p.vid:04x}:{p.pid:04x}")
        return
    if not a.port:
        sys.exit("give the serial port (see --list)")
    ser = serial.Serial(a.port, 115200, timeout=0.05)
    pr, tk = Parser(), Take()
    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            for typ, p in pr.feed(ser.read(65536)):
                tk.add(typ, p)
    ser.write(b"stop\n"); pump(0.3); ser.reset_input_buffer(); pr.buf.clear()
    if a.info:
        ser.write(b"info\n"); pump(2); tk.report(pr.bad); return
    ser.write(f"start {a.hz} {int(a.mic)}\n".encode())  # USB: live mic; BLE receiver: impact clips
    print(f"recording {a.seconds:.0f} s ...")
    end = time.time() + 5  # the BLE receiver scans, connects and probes before data flows
    while not tk.imu and time.time() < end:
        pump(0.05)
    if not tk.imu:
        ser.write(b"stop\n"); sys.exit("no IMU data: check the board (USB) or that the glove is awake (BLE)")
    pump(a.seconds)
    ser.write(b"stop\n"); pump(0.5)
    arr = tk.report(pr.bad)
    if a.out:
        import numpy as np
        np.savez(a.out, **arr); print("saved", a.out)


if __name__ == "__main__":
    main()
