// 833 Hz gyro around each impact, from the IMUs' own FIFOs (2026-10-25).
// The live stream is limited to ~250 Hz by the phone's Bluetooth, so the full-rate detail near impact is kept on
// the glove and sent after the swing, like the sound clips (packet kind 2).
// - Both IMUs put GYRO ONLY into their FIFO at 833 Hz (gyro + accel would hold only ~0.4 s on the LSM6DS3TR-C).
// - motion_drain() pulls a few samples from each FIFO every ~10 ms into RAM rings of ~1.6 s, stamping each sample
//   with micros(): the newest sample is "now", older ones are spaced by the ODR measured at boot (each chip's
//   oscillator differs by a few %, so the nominal 833 Hz is not used).
// - motion_cut(impact_us) copies -0.25 s..+0.25 s around the impact into a send buffer: frames of
//   hand gx gy gz, arm gx gy gz (int16), the arm sampled at the hand sample times (nearest).
// Needs fast_i2c.h (TWIM). Registers: LSM6DS3TR-C FIFO_CTRL3 0x08, CTRL5 0x0A, STATUS1-4 0x3A-0x3D, DATA 0x3E;
// LSM6DSOX FIFO_CTRL3 0x09, CTRL4 0x0A, STATUS1-2 0x3A-0x3B, DATA_OUT_TAG 0x78 + 6 bytes.
#pragma once
#include "fast_i2c.h"

const int MRING = 1340;                          // ~1.5 s at ~869 Hz
struct MSample { uint32_t t; int16_t g[3]; };
static MSample mHand[MRING], mArm[MRING];
static uint32_t mHandN = 0, mArmN = 0;           // samples written so far (ring index = n % MRING)
static float mOdrHand = 833, mOdrArm = 833;      // measured at boot
static bool mArmOn = false, mArmBurst = true;    // mArmBurst: multi-word reads roll back to the TAG register
static uint32_t mLastDrain = 0, mHandErr = 0, mArmErr = 0;

static inline bool m_wr(const FastBus &b, uint8_t reg, uint8_t v) { uint8_t d[2] = {reg, v}; return fast_write(b, 0x6A, d, 2); }

// FIFO word counts (unread)
static inline int m_hand_words() { uint8_t s[4]; if (!fast_read(BUS_HAND, 0x6A, 0x3A, s, 4)) return -1; return s[0] | ((s[1] & 0x07) << 8); }
static inline int m_arm_words()  {   // LSM6DSOX: 10-bit count; when full (FIFO_FULL_IA / OVR) take the max and drain repeatedly
  uint8_t s[2]; if (!fast_read(BUS_ARM, 0x6A, 0x3A, s, 2)) return -1;
  int w = s[0] | ((s[1] & 0x03) << 8); if (w == 0 && (s[1] & 0x60)) w = 1023; return w; }

static inline void m_fifo_on(bool arm) {
  m_wr(BUS_HAND, 0x0A, 0x00);                    // bypass: clears the FIFO
  m_wr(BUS_HAND, 0x08, 0x08);                    // FIFO_CTRL3: gyro no decimation, accel not in FIFO
  m_wr(BUS_HAND, 0x0A, 0x38 | 0x06);             // FIFO_CTRL5: ODR_FIFO 833 Hz, continuous
  if (arm) {
    m_wr(BUS_ARM, 0x0A, 0x00);
    m_wr(BUS_ARM, 0x09, 0x70);                   // FIFO_CTRL3: BDR_GY 833 Hz, BDR_XL off
    m_wr(BUS_ARM, 0x0A, 0x06);                   // FIFO_CTRL4: continuous
  }
}

// Call after fast_i2c_init(). Measures each FIFO's real rate over ~0.5 s.
static inline void motion_init(bool armOk) {
  mArmOn = armOk;
  m_fifo_on(armOk);
  uint32_t t0 = micros(); delay(500);
  int hw = m_hand_words(), aw = mArmOn ? m_arm_words() : 0; uint32_t dt = micros() - t0;
  if (hw > 30) mOdrHand = (hw / 3) * 1e6f / dt;  // 3 words (x, y, z) per gyro sample
  if (mArmOn && aw > 10) mOdrArm = aw * 1e6f / dt;
  m_fifo_on(armOk);                              // restart clean so the rings start at "now"
  mLastDrain = micros();
}

// Hand (LSM6DS3TR-C): gyro-only pattern x, y, z words; FIFO_STATUS3/4 give the next word's place in the pattern.
static inline void m_drain_hand(uint32_t now) {
  uint8_t s[4]; if (!fast_read(BUS_HAND, 0x6A, 0x3A, s, 4)) { mHandErr++; return; }
  // DIFF_FIFO is 11 bits: a full FIFO (2048 words, ~0.78 s of gyro) reads 0 with FIFO_FULL_SMART / OVER_RUN set.
  // Missing that left the ring empty once idle draining stopped (2026-10-25).
  int words = s[0] | ((s[1] & 0x07) << 8), pat = (s[2] | ((s[3] & 0x03) << 8)) % 3;
  if (words == 0 && (s[1] & 0x60)) words = 2048;
  uint8_t junk[4];
  if (pat) { fast_read(BUS_HAND, 0x6A, 0x3E, junk, 2 * (3 - pat)); words -= 3 - pat; }   // realign to x
  int n = min(words / 3, 24); if (n <= 0) return;
  static uint8_t buf[24 * 6];
  if (!fast_read(BUS_HAND, 0x6A, 0x3E, buf, n * 6)) { mHandErr++; return; }
  int left = words / 3 - n;                      // samples still in the FIFO after these (newer than ours)
  for (int i = 0; i < n; i++) {
    MSample &m = mHand[mHandN % MRING];
    m.t = now - (uint32_t)((n - 1 - i + left) * 1e6f / mOdrHand);
    for (int k = 0; k < 3; k++) m.g[k] = (int16_t)(buf[6 * i + 2 * k] | (buf[6 * i + 2 * k + 1] << 8));
    mHandN++;
  }
}

// Arm (LSM6DSOX): each word = TAG + 6 bytes; tag sensor 0x01 = gyro. Multi-word reads are tried first and
// checked by their tags; if the address does not roll back to TAG, fall back to one word per read.
static inline void m_drain_arm(uint32_t now) {
  int words = m_arm_words(); if (words < 0) { mArmErr++; return; }
  int n = min(words, 24); if (n <= 0) return;
  static uint8_t buf[24 * 7];
  bool ok = true;
  if (mArmBurst) {
    if (!fast_read(BUS_ARM, 0x6A, 0x78, buf, n * 7)) { mArmErr++; return; }
    for (int i = 0; i < n && ok; i++) if ((buf[7 * i] >> 3) != 0x01) ok = false;
    if (!ok) { mArmBurst = false; return; }       // data already consumed; the next drain uses single words
  } else {
    for (int i = 0; i < n; i++) if (!fast_read(BUS_ARM, 0x6A, 0x78, buf + 7 * i, 7)) { mArmErr++; n = i; break; }
  }
  int left = words - n;
  for (int i = 0; i < n; i++) {
    if ((buf[7 * i] >> 3) != 0x01) continue;
    MSample &m = mArm[mArmN % MRING];
    m.t = now - (uint32_t)((n - 1 - i + left) * 1e6f / mOdrArm);
    for (int k = 0; k < 3; k++) m.g[k] = (int16_t)(buf[7 * i + 1 + 2 * k] | (buf[7 * i + 2 + 2 * k] << 8));
    mArmN++;
  }
}

// active = a swing is going on (or just ended). Draining costs I2C time (the 240 Hz stream fell to ~183 Hz when it
// ran all the time), so when idle the FIFOs are only reset, every 0.4 s: two short writes, no reading.
// The reset period must stay below the FIFO's capacity: the LSM6DS3TR-C holds 2048 words = 682 gyro samples = only
// ~0.78 s at its real ~869 Hz. A full FIFO overwrites its oldest samples and its count is no longer usable, so the
// sample times computed from it jumped (a 1 s reset gave clips 0.3-0.9 s off; no reset left the ring empty).
// A swing still finds 0-0.4 s of history to drain, and a golf backswing passes 400 dps well before impact.
static uint32_t mLastReset = 0;
static inline void motion_drain(bool active = true) {
  uint32_t now = micros();
  if (!active) {
    if (now - mLastReset > 400000) {
      mLastReset = now;
      m_wr(BUS_HAND, 0x0A, 0x00); m_wr(BUS_HAND, 0x0A, 0x38 | 0x06);
      if (mArmOn) { m_wr(BUS_ARM, 0x0A, 0x00); m_wr(BUS_ARM, 0x0A, 0x06); }
    }
    return;
  }
  if (now - mLastDrain < 10000) return;
  mLastDrain = now;
  m_drain_hand(now);
  if (mArmOn) m_drain_arm(micros());
}

// ---- cut and send ----
// Every frame carries its own time (u16 offset from the clip's first frame, in 10 us units), so gaps or uneven
// drain timing can't shift anything: the clip is "all ring samples within +-0.25 s of the impact", sent as they are.
// (The first version assumed even spacing from the first frame and had to throw windows away at any gap.)
const int MTOT = 460;                            // 0.5 s at up to ~900 Hz
static int16_t mOut[MTOT][6]; static uint16_t mOutDt[MTOT];
static uint32_t mOutT = 0; static uint16_t mOutN = 0, mOutPre = 0, mOutRate = 0;

static inline int m_find(const MSample *r, uint32_t n, uint32_t t) {   // index (absolute) of the sample nearest t
  if (!n) return -1;
  uint32_t lo = n > MRING ? n - MRING : 0, best = lo; uint32_t bd = 0xFFFFFFFF;
  for (uint32_t i = lo; i < n; i++) {                                   // linear: times need not be monotonic
    uint32_t d = (int32_t)(r[i % MRING].t - t) >= 0 ? r[i % MRING].t - t : t - r[i % MRING].t;
    if (d < bd) { bd = d; best = i; }
  }
  return best;
}

// Returns false if no samples near the impact are in the ring.
static inline bool motion_cut(uint32_t impactUs) {
  motion_drain();
  if (!mHandN) return false;
  uint32_t lo = mHandN > MRING ? mHandN - MRING : 0, t0 = impactUs - 250000;
  int n = 0, pre = 0, aj = -1; uint32_t bestD = 0xFFFFFFFF;
  for (uint32_t i = lo; i < mHandN && n < MTOT; i++) {
    const MSample &h = mHand[i % MRING];
    uint32_t off = h.t - t0;                     // unsigned: samples before t0 wrap to huge values
    if (off > 500000) continue;
    if (n == 0) mOutT = h.t;
    int32_t rel = (int32_t)(h.t - mOutT); if (rel < 0 || rel > 655350) continue;   // keep times increasing
    for (int k = 0; k < 3; k++) mOut[n][k] = h.g[k];
    // arm sample nearest in time: search once, then walk forward (a full search per frame cost ~0.1 s)
    if (mArmN && aj < 0) aj = m_find(mArm, mArmN, h.t);
    if (aj >= 0) {
      while ((uint32_t)aj + 1 < mArmN) {
        uint32_t dn = (int32_t)(mArm[(aj + 1) % MRING].t - h.t) >= 0 ? mArm[(aj + 1) % MRING].t - h.t : h.t - mArm[(aj + 1) % MRING].t;
        uint32_t dc = (int32_t)(mArm[aj % MRING].t - h.t) >= 0 ? mArm[aj % MRING].t - h.t : h.t - mArm[aj % MRING].t;
        if (dn <= dc) aj++; else break;
      }
    }
    for (int k = 0; k < 3; k++) mOut[n][3 + k] = (mArmOn && aj >= 0) ? mArm[aj % MRING].g[k] : 0;
    mOutDt[n] = (uint16_t)(rel / 10);
    uint32_t d = (int32_t)(h.t - impactUs) >= 0 ? h.t - impactUs : impactUs - h.t;
    if (d < bestD) { bestD = d; pre = n; }
    n++;
  }
  if (n < 20) return false;
  mOutN = n; mOutPre = pre; mOutRate = (uint16_t)(mOdrHand * 10 + 0.5f);
  return true;
}
