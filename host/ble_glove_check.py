"""Connect to the SensorGlove over the PC's own Bluetooth and check the forearm (LSM6DSOX) IMU.

  python ble_glove_check.py            # 15 s of live readings at 50 Hz
  python ble_glove_check.py --seconds 30

Uses the glove firmware's BLE protocol (xiao_ble_glove.ino):
  data notification: seq u32, n u8, armOk u8, then n frames of t_us u32 + 12 x i16
                     (hand gyro xyz, hand acc xyz, arm gyro xyz, arm acc xyz); n = 0 is a status packet
  ctrl writes: "start <hz> <batch> <mic>", "stop", "status"
"""
import argparse, asyncio, struct, sys, time
from bleak import BleakClient, BleakScanner

DATA = "7e5a0002-2f3b-4c1d-9a8e-0b1c2d3e4f50"
CTRL = "7e5a0003-2f3b-4c1d-9a8e-0b1c2d3e4f50"
ACC_G = 0.488e-3   # 16 g range, g per LSB
GYRO_DPS = 70e-3   # 2000 dps range, dps per LSB


async def main(seconds):
    print("scanning for SensorGlove ...")
    dev = await BleakScanner.find_device_by_name("SensorGlove", timeout=15)
    if not dev:
        sys.exit("SensorGlove not found: is the blue LED blinking? Press reset on the glove XIAO to wake it.")
    print("found", dev.address)
    state = {"frames": 0, "last": 0.0, "arm": None}

    def on_data(_, d: bytearray):
        if len(d) < 6:
            return
        n, arm_ok = d[4], d[5]
        state["arm"] = arm_ok
        if n == 0 and len(d) >= 15:
            mv, chg = struct.unpack_from("<HB", d, 6)
            extra = ""
            if len(d) >= 39:   # firmware 2026-10-28+: failed hand IMU reads, hand IMU recoveries
                fails, fixes = struct.unpack_from("<IH", d, 33)
                extra = f", hand reads failed {fails}, recovered {fixes}x"
            print(f"status: arm IMU {'yes' if arm_ok else 'NO'}, battery {mv} mV, charging {chg}{extra}")
            return
        for i in range(n):
            off = 6 + 28 * i
            if off + 28 > len(d):
                break
            v = struct.unpack_from("<I12h", d, off)[1:]
            state["frames"] += 1
            if not any(v[:6]):   # a real hand reading always has gravity in it
                state["hand0"] = state.get("hand0", 0) + 1
            now = time.time()
            if now - state["last"] >= 0.25:
                state["last"] = now
                ha = [x * ACC_G for x in v[3:6]]
                ag = [x * GYRO_DPS for x in v[6:9]]
                aa = [x * ACC_G for x in v[9:12]]
                print(f"hand acc {ha[0]:+5.2f} {ha[1]:+5.2f} {ha[2]:+5.2f} g | "
                      f"ARM acc {aa[0]:+5.2f} {aa[1]:+5.2f} {aa[2]:+5.2f} g  gyro {ag[0]:+7.1f} {ag[1]:+7.1f} {ag[2]:+7.1f} dps")

    async with BleakClient(dev) as c:
        print("connected, MTU", c.mtu_size)
        await c.start_notify(DATA, on_data)
        await c.write_gatt_char(CTRL, b"status", response=False)
        await asyncio.sleep(1)
        await c.write_gatt_char(CTRL, b"start 50 1 0", response=False)  # 50 Hz, 1 frame per packet, no mic
        print(f"streaming {seconds:.0f} s: tilt the 4438 and watch the ARM acc values")
        await asyncio.sleep(seconds)
        await c.write_gatt_char(CTRL, b"stop", response=False)
        await asyncio.sleep(0.3)
    print(f"frames received: {state['frames']}, arm IMU present: {'yes' if state['arm'] else 'NO'}, "
          f"hand all-zero frames: {state.get('hand0', 0)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=15)
    asyncio.run(main(ap.parse_args().seconds))
