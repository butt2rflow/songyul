"""Receive R10 shots sent by the Garmin Golf app's E6 connection.

Run:  python3 r10-bridge/r10_e6_server.py [--port 2483] [--out data/r10]
Then in the Garmin Golf app pick the E6 Connect (PC) link and enter this PC's IP and port 2483.

Protocol (JSON over TCP; see the reference in THIRD_PARTY.md). The app sends Handshake, Challenge, then per shot
SetBallData, SetClubData, SendShot; we ACK each, and after a shot send Disarm, ShotComplete, Arm.
Every 10 s we send a Ping once the app has answered the last one.

Each shot is appended to <out>/r10-shots-YYYYMMDD.jsonl with the PC clock (wall + monotonic) at
SendShot, the raw R10 ball/club values, and a running shot number. Raw values are kept as the app
sends them: SpinAxis in degrees (the adapter flips the sign and wraps >90 for GSPro; we don't).
"""
import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ack(sub, details="Success."):
    return {"Details": details, "SubType": sub, "Type": "ACK"}


def sim(sub, **extra):
    return {"Type": "SimCommand", "SubType": sub, **extra}


def split_json(text):
    """The app can send several JSON objects in one packet ("{..}{..}"); yield each."""
    dec, i = json.JSONDecoder(), 0
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        obj, i = dec.raw_decode(text, i)
        yield obj


class Session:
    shot_no = 0  # shared across reconnects within one run

    def __init__(self, reader, writer, out_dir, on_shot=None):
        self.r, self.w, self.out_dir, self.on_shot = reader, writer, out_dir, on_shot
        self.ball = self.club = None
        self.got_pong = False
        self.buf = ""

    async def send(self, obj):
        self.w.write(json.dumps(obj).encode())
        await self.w.drain()

    async def pinger(self):
        while True:
            await asyncio.sleep(10)
            if self.got_pong:
                self.got_pong = False
                await self.send(sim("Ping"))

    def record(self):
        Session.shot_no += 1
        shot = {"shot": Session.shot_no, "t_wall": time.time(), "t_mono": time.monotonic(),
                "iso": datetime.now().isoformat(timespec="milliseconds"),
                "ball": self.ball, "club": self.club}
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"r10-shots-{datetime.now():%Y%m%d}.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(shot) + "\n")
        b, c = self.ball or {}, self.club or {}
        print(f"[shot {shot['shot']}] {shot['iso'][11:]}  ball {b.get('BallSpeed', 0):.1f} mph"
              f"  launch {b.get('LaunchAngle', 0):.1f}°  dir {b.get('LaunchDirection', 0):+.1f}°"
              f"  spin {b.get('TotalSpin', 0):.0f} rpm axis {b.get('SpinAxis', 0):+.1f}°"
              f"  club {c.get('ClubHeadSpeed', 0):.1f}  path {c.get('ClubAnglePath', 0):+.1f}°"
              f"  face {c.get('ClubAngleFace', 0):+.1f}°  → {path.name}", flush=True)
        if self.on_shot:
            self.on_shot(shot)

    async def handle(self, m):
        t = m.get("Type")
        if t == "Handshake":
            await self.send({"Type": "Handshake", "Challenge": "", "E6Version": "",
                             "ProtocolVersion": "", "RequiredProtocolVersion": ""})
        elif t == "Challenge":
            self.got_pong = True
            await self.send({"Type": "Authentication", "Success": "true"})
            await self.send(sim("Arm"))  # ready for a shot (the app showed a red "!" without this)
        elif t == "Pong":
            self.got_pong = True
        elif t == "SetBallData":
            self.ball = m.get("BallData")
            await self.send(ack("SetBallData"))
        elif t == "SetClubData":
            self.club = m.get("ClubData")
            await self.send(ack("SetClubData"))
        elif t == "SendShot":
            self.record()
            await self.send(ack("SendShot"))
            await self.send(sim("Disarm"))
            await asyncio.sleep(0.5)
            await self.send(sim("ShotComplete", Details={"BallData": self.ball, "ClubData": self.club,
                                                          "BallInHole": False, "BallLocation": "Fairway"}))
            self.ball = self.club = None
            await asyncio.sleep(0.5)
            await self.send(sim("Arm"))
        elif t == "SetClubType":
            await self.send(ack("SetClubType"))
            await self.send(sim("Arm"))
        elif t == "Disconnect":
            self.w.close()
        else:
            await self.send(ack(t or "Unknown"))

    async def run(self):
        peer = self.w.get_extra_info("peername")
        print(f"app connected from {peer}", flush=True)
        ping = asyncio.create_task(self.pinger())
        try:
            while data := await self.r.read(65536):
                self.buf += data.decode("utf-8", "replace")
                try:
                    msgs = list(split_json(self.buf))
                    self.buf = ""
                except json.JSONDecodeError:
                    continue  # incomplete object: wait for the rest
                for m in msgs:
                    await self.handle(m)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            ping.cancel()
            self.w.close()
            print(f"app disconnected ({peer})", flush=True)


async def serve(port, out_dir, on_shot=None):
    async def client(r, w):
        await Session(r, w, out_dir, on_shot).run()
    server = await asyncio.start_server(client, "0.0.0.0", port)
    print(f"E6 receiver listening on TCP port {port} on all interfaces", flush=True)
    return server


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=2483)
    ap.add_argument("--out", type=Path, default=ROOT / "data/r10")
    a = ap.parse_args()

    async def go():
        server = await serve(a.port, a.out)
        async with server:
            await server.serve_forever()
    try:
        asyncio.run(go())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
