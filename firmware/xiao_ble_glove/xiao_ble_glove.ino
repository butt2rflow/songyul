// XIAO nRF52840 Sense on the glove -> BLE notifications to xiao_ble_receiver (a second XIAO on the PC's USB).
// IMU live (on-board hand IMU + optional LSM6DSOX arm IMU on D4/D5) plus impact sound clips: the PDM mic fills a
// 1.5 s ring buffer; after each fast swing the loudest moment is taken as impact and 0.25 s before + 0.25 s after
// is sent in chunks between IMU packets (live 16 kHz audio does not fit in BLE).
// Voice commands: double-tap the back of the hand while not swinging -> 2.5 s of voice at 8 kHz is streamed
// (same chunk format, flags byte = 1). The PC turns it into text and runs the matching action.
// Battery powered: LiPo on BAT+/BAT-, charges from USB-C at 100 mA.
// Button D2 -> GND: hold 2 s = deep sleep, press = wake. Also sleeps after 20 min without a connection (was 5; 2026-10-28, so a break at the range needs no RST)
// unless USB power is present. Sleep turns USB off; RST wakes it when no button is wired.
// LEDs: blue blink = advertising, green = streaming, red = on-board IMU missing.
#include <Wire.h>
#include <ArduinoBLE.h>
#include "utility/HCI.h"                 // local ArduinoBLE patch 2026-10-27: transmit credit counters
#ifdef ARDUINOBLE_CREDIT_PATCH
extern volatile uint32_t ble_rx_drops;   // ... and dropped HCI rx packets (HCICordioTransport.cpp)
#define BLE_PEND() HCI.pendingPkt()
#define BLE_MAXP() HCI.maxPkt()
#define BLE_REL() HCI.creditReleases
#define BLE_RXD() ble_rx_drops
#else                                    // original library: report zeros
#define BLE_PEND() 0
#define BLE_MAXP() 0
#define BLE_REL() 0
#define BLE_RXD() 0
#endif
#include <LSM6DS3.h>
#include <Adafruit_LSM6DSOX.h>
#include <PDM.h>
#include "proto.h"
#include "fast_i2c.h"   // IMU reads through TWIM + EasyDMA after setup (Wire took ~1.5-2.5 ms per read)
#include "motion_fifo.h" // 833 Hz gyro kept around each impact, sent after the sound clip (kind 2)
bool motionPending = false; int motionChunk = 0;

// ---- breadcrumb (development, 2026-10-26): the last step reached survives RST and a watchdog reset ----
// 16 bytes at the end of mbed's crash-data RAM (0x20000100-0x200001FF): the section has no initial data and is
// outside .bss, so startup doesn't clear it, and this core doesn't enable mbed crash capture (which writes from the
// start of the region). At boot the previous step + RESETREAS are kept and sent in every status packet (bytes 15..26).
struct Crumb { uint32_t magic, step, detail, boots; };
static volatile Crumb *const crumb = (volatile Crumb *)0x200001F0;
const uint32_t CRUMB_MAGIC = 0xC0FFEE01;
uint32_t prevStep = 0, prevDetail = 0, resetReason = 0; uint16_t bootCount = 0;
enum : uint16_t { S_SETUP = 1, S_SETUP_BLE = 2, S_SETUP_DONE = 3,
  S_LOOP = 10, S_POLLED = 11, S_IDLE = 12, S_IMU_HAND = 20, S_IMU_ARM = 21, S_IMU_SEND = 22, S_DRAIN = 23,
  S_SCAN = 24, S_VOICE = 25, S_CLIP = 26, S_MOTION = 27, S_STATUS = 28, S_BATT = 29, S_HAND_FIX = 30,
  S_CTRL = 40, S_MIC_STOP = 41, S_MIC_START = 42, S_START_DONE = 43, S_STOP = 44, S_LISTEN = 45, S_PROBE = 46,
  S_SLEEP = 47, S_DISCONN = 50, S_STALE = 51 };
inline void step(uint16_t s, uint32_t d = 0) { crumb->step = s; crumb->detail = d; }
void crumbBoot() {
  resetReason = NRF_POWER->RESETREAS; NRF_POWER->RESETREAS = 0xFFFFFFFF;   // bits: 0 pin, 1 watchdog, 2 soft, 3 lockup, 16 wake from off
  if (crumb->magic == CRUMB_MAGIC) { prevStep = crumb->step; prevDetail = crumb->detail; bootCount = crumb->boots + 1; }
  else bootCount = 1;
  crumb->magic = CRUMB_MAGIC; crumb->boots = bootCount; step(S_SETUP);
}

#define SVC_UUID  "7e5a0001-2f3b-4c1d-9a8e-0b1c2d3e4f50"
#define DATA_UUID "7e5a0002-2f3b-4c1d-9a8e-0b1c2d3e4f50"
#define CTRL_UUID "7e5a0003-2f3b-4c1d-9a8e-0b1c2d3e4f50"
const int MAXV = 244;  // data value size; the receiver probes how many bytes really arrive

BLEService svc(SVC_UUID);
BLECharacteristic dataChar(DATA_UUID, BLENotify, MAXV);
BLECharacteristic ctrlChar(CTRL_UUID, BLEWrite | BLEWriteWithoutResponse, 32);

LSM6DS3 hand(I2C_MODE, 0x6A);
Adafruit_LSM6DSOX arm;
bool armOk = false, streaming = false;
uint16_t imuHz = 200; uint32_t periodUs = 5000, nextUs = 0, seq = 0, dropped = 0;
uint8_t batch = 8, nInBatch = 0;
uint8_t buf[MAXV];
uint32_t lastConn = 0, lastStatus = 0, btnDown = 0;
// Stale-link guard (2026-10-26): after the phone's screen went off or the page was left, the glove still believed it
// was connected and never advertised again. A host that sends "hb" opts in; if its heartbeats stop for 8 s while
// connected, the glove drops the link itself. Hosts that never send "hb" (PC scripts, the receiver) are not affected.
uint32_t lastHb = 0; bool hbOn = false;
bool wdtOn = false;   // watchdog running (see wdtStart)
// Hand IMU health (2026-10-28): pulling USB while streaming made every on-board IMU read fail until RST, and the
// loop streamed its uninitialised buffer instead (zeros, or 24833 / -32511 in the phone log). Now a failed read
// sends zeros and is counted; 3 in a row, or a once-a-second register check that no longer matches, runs
// handRecover(): free the bus, power-cycle the IMU if it still doesn't answer, write back the registers saved at boot.
uint8_t handRegA[6], handRegB[10];   // 0x06-0x0B FIFO_CTRL1-5 + DRDY_PULSE_CFG_G, 0x10-0x19 CTRL1_XL..CTRL10_C
bool handSaved = false;
uint32_t handFails = 0, lastRecoverMs = 0; uint16_t handRecovers = 0; uint8_t handFailRun = 0;
uint32_t loopMaxUs = 0, loopLastUs = 0;   // longest gap between loop() passes since the last status (development)
// Forearm IMU health (2026-11-15): at the range the 4438's STEMMA QT plug lifted on impact twice; every read failed
// (zeros) until RST while armOk still said 1, so the clip trigger and the page's swing finder lost the forearm. Now 3
// failed reads in a row, ARM_ZERO_N all-zero samples (a live IMU always reads gravity), or a register check that no
// longer matches mark it dead: armLive = 0 goes to the phone in place of armOk, the clip trigger uses the hand, and
// armRecover() tries every ARM_RETRY_MS to free the bus, power-cycle the 4438 through D10 and write its setup back.
const uint16_t ARM_ZERO_N = 120; const uint32_t ARM_RETRY_MS = 1000;
uint8_t armRegA[5], armRegB[10];     // 0x07-0x0B FIFO_CTRL1-4 + COUNTER_BDR_REG1, 0x10-0x19 CTRL1_XL..CTRL10_C (LSM6DSOX)
bool armSaved = false, armLive = false;
uint32_t armFails = 0, lastArmFixMs = 0; uint16_t armRecovers = 0, armZeroRun = 0; uint8_t armFailRun = 0;
bool devArmOff = false, devFifoOff = false;   // development ("dev arm 0", "dev fifo 0"): skip the forearm read / FIFO drain, to find what breaks hand reads

// ---- impact sound ----
// Clip/voice chunks go out every 20 ms. Measured over the PC's Bluetooth (2026-10-22): 8 ms lost ~7 % of chunks,
// 16 ms ~1 %, 20 ms 1 in 1440. A 0.5 s impact clip then takes ~1.5 s to send, a 2.5 s voice clip ~3.6 s.
const uint32_t CHUNK_US = 20000;
const int SR = 16000, RING = 24000, PRE = 4000, POST = 4000, CLIP = PRE + POST;
const int16_t SWING_RAW = 5714;      // 400 dps at 70 mdps/LSB: "this is a real swing"
const int16_t LOUD_MIN = 3000;       // quietest peak still treated as a ball strike [HW: tune]
int16_t ringBuf[RING]; int16_t pdmTmp[256];
volatile uint32_t ringCount = 0, lastBlockUs = 0;
bool micOn = true, swingActive = false;
uint32_t lastFastUs = 0, scanned = 0, peakIdx = 0; int16_t peakVal = 0;
int16_t clipBuf[CLIP]; uint32_t clipT = 0; uint16_t clipId = 0, clipPeak = 0;
int clipChunk = -1, clipChunks = 0, clipPer = 0; uint32_t lastChunkUs = 0;

// ---- voice command: double tap -> stream 2.5 s of voice at 8 kHz ----
const int VOICE_SR = 8000, VOICE_N = 28000;   // 3.5 s (was 2.5: people start talking ~1-2 s after the blue LED)
// At 20 ms per 112-sample chunk the send runs at 0.7x real time, so the oldest unsent sample is ~1.05 s old at the
// end of a 3.5 s clip; the 1.5 s ring (RING) must stay ahead of that. Don't go past ~4.5 s without a bigger ring.
const int16_t TAP_RAW = 3074;                 // 1.5 g jump between samples at 0.488 mg/LSB [HW: tune]
int16_t lastAz[3] = {0, 0, 0}; uint32_t lastAzUs = 0, tap1Us = 0, quietSinceUs = 0;
bool voiceOn = false; uint32_t voiceStart = 0, voiceT = 0; int voiceChunk = 0, voiceChunks = 0, voicePer = 0; uint16_t voiceId = 0;

void voiceBegin(uint32_t now) {
  if (voiceOn || clipChunk >= 0 || !micOn) return;
  noInterrupts(); voiceStart = ringCount; voiceT = lastBlockUs; interrupts();
  voicePer = (6 + 28 * batch - 6) / 2; voiceChunks = 1 + (VOICE_N + voicePer - 1) / voicePer; voiceChunk = 0;
  voiceId++; voiceOn = true; digitalWrite(LEDB, LOW);   // blue = listening
}

void sendVoiceChunk(uint32_t now) {
  if (!voiceOn || now - lastChunkUs < CHUNK_US) return;
  uint8_t p[MAXV]; put_u16(p, voiceId); put_u16(p + 2, voiceChunk); p[4] = 0xFE; p[5] = 1;
  int len;
  if (voiceChunk == 0) { put_u32(p + 6, voiceT); put_u16(p + 10, 0); put_u16(p + 12, VOICE_N); put_u16(p + 14, VOICE_SR); put_u16(p + 16, 0); len = 18; }
  else {
    int s0 = (voiceChunk - 1) * voicePer, n = min(voicePer, VOICE_N - s0);
    uint32_t need = voiceStart + 2UL * (s0 + n);           // 2 input samples (16 kHz) per output sample
    if (ringCount < need) return;                           // not recorded yet: try again next loop
    int16_t *out = (int16_t *)(p + 6);
    for (int i = 0; i < n; i++) { uint32_t k = voiceStart + 2UL * (s0 + i); out[i] = (ringBuf[k % RING] + ringBuf[(k + 1) % RING]) / 2; }
    len = 6 + 2 * n;
  }
  dataChar.writeValue(p, len); lastChunkUs = now;
  if (++voiceChunk >= voiceChunks) { voiceOn = false; digitalWrite(LEDB, HIGH); }
}

// A tap is a sharp jump in the hand accel. Two taps 0.10-0.45 s apart, after 1 s without swinging, start voice.
// (Was 0.15 s minimum; a natural quick double-tap measured 110 ms apart, 2026-10-22. One knock rings for ~10-20 ms.)
void checkTap(const int16_t *v, uint32_t now) {
  const int16_t *a = v + 3;
  // jump against the sample kept ~5 ms back, so the threshold means the same at 200 or 800 Hz (TAP_RAW was set at 200 Hz)
  int16_t jump = max(abs(a[0] - lastAz[0]), max(abs(a[1] - lastAz[1]), abs(a[2] - lastAz[2])));
  if (now - lastAzUs >= 4500) { memcpy(lastAz, a, 6); lastAzUs = now; }
  if (lastFastUs) { quietSinceUs = now; tap1Us = 0; return; }
  if (now - quietSinceUs < 1000000 || jump < TAP_RAW) return;
  if (tap1Us && now - tap1Us > 100000 && now - tap1Us < 450000) { tap1Us = 0; voiceBegin(now); }
  else if (!tap1Us || now - tap1Us >= 450000) tap1Us = now;
}

void onPDM() {
  int n = PDM.available(); if (n > (int)sizeof(pdmTmp)) n = sizeof(pdmTmp);
  PDM.read(pdmTmp, n);
  uint32_t c = ringCount;
  for (int i = 0; i < n / 2; i++) ringBuf[(c + i) % RING] = pdmTmp[i];
  ringCount = c + n / 2; lastBlockUs = micros();
}

// The PDM mic is started ONCE in setup(), before BLE.begin(), and never restarted (2026-10-26): the core's
// PDMClass::begin() busy-waits on NRF_CLOCK->EVENTS_HFCLKSTARTED, which the BLE stack can clear while the clock is
// already running, so a begin() on every "start" could wait forever (breadcrumb step 42 at the range). start/stop now
// only switch the sound processing (micOn); the mic keeps filling the ring (~1 mA).
bool pdmRunning = false;
void pdmBeginOnce() { if (pdmRunning) return; PDM.onReceive(onPDM); PDM.setBufferSize(sizeof(pdmTmp)); pdmRunning = PDM.begin(1, SR) == 1; }
void micStart() { if (!micOn) return; scanned = ringCount; }
void micStop() {}

void scanSound(uint32_t now) {
  uint32_t end = ringCount;
  if (end - scanned > RING) scanned = end - RING;
  if (swingActive)
    for (; scanned < end; scanned++) { int16_t a = abs(ringBuf[scanned % RING]); if (a > peakVal) { peakVal = a; peakIdx = scanned; } }
  else scanned = end;
  bool was = swingActive;
  swingActive = lastFastUs && (now - lastFastUs) < 600000;
  if (was && !swingActive) {                       // the swing just ended: cut the clip around the loudest moment
    noInterrupts(); uint32_t cnt = ringCount, bus = lastBlockUs; interrupts();
    if (peakVal >= LOUD_MIN && clipChunk < 0 && cnt - (peakIdx - PRE) <= (uint32_t)RING && cnt >= peakIdx + POST) {
      for (int i = 0; i < CLIP; i++) clipBuf[i] = ringBuf[(peakIdx - PRE + i) % RING];
      clipT = bus - (uint32_t)((cnt - peakIdx) * 1000000ULL / SR);
      clipPeak = peakVal; clipId++;
      motionPending = motion_cut(clipT); motionChunk = 0;
      clipPer = (6 + 28 * batch - 6) / 2; clipChunks = 1 + (CLIP + clipPer - 1) / clipPer; clipChunk = 0;
    }
    peakVal = 0; lastFastUs = 0;
  }
}

// kind 2: chunk 0 = t_us of the first frame u32, index of the frame nearest impact u16, frames u16, rate (Hz x 10) u16,
// flags u16 (bit0 arm present, bit1 per-frame times); chunks 1.. = frames of 14 bytes: time offset from the first
// frame u16 (10 us units), then 6 int16 (hand gx gy gz, arm gx gy gz), 70 mdps/LSB
void sendMotionChunk(uint32_t now) {
  if (!motionPending || now - lastChunkUs < CHUNK_US) return;
  const int per = (28 * batch) / 14, chunks = 1 + (mOutN + per - 1) / per;
  uint8_t p[MAXV]; put_u16(p, clipId); put_u16(p + 2, motionChunk); p[4] = 0xFE; p[5] = 2;
  int len = 6;
  if (motionChunk == 0) { put_u32(p + 6, mOutT); put_u16(p + 10, mOutPre); put_u16(p + 12, mOutN); put_u16(p + 14, mOutRate); put_u16(p + 16, (mArmOn ? 1 : 0) | 2); len = 18; }
  else {
    int f0 = (motionChunk - 1) * per, n = min(per, (int)mOutN - f0);
    for (int i = 0; i < n; i++) { put_u16(p + 6 + 14 * i, mOutDt[f0 + i]); memcpy(p + 8 + 14 * i, mOut[f0 + i], 12); }
    len = 6 + 14 * n;
  }
  dataChar.writeValue(p, len); lastChunkUs = now;
  if (++motionChunk >= chunks) motionPending = false;
}

void sendClipChunk(uint32_t now) {
  if (clipChunk < 0 || now - lastChunkUs < CHUNK_US) return;
  uint8_t p[MAXV]; put_u16(p, clipId); put_u16(p + 2, clipChunk); p[4] = 0xFE; p[5] = 0;
  int len = 6;
  if (clipChunk == 0) { put_u32(p + 6, clipT); put_u16(p + 10, PRE); put_u16(p + 12, CLIP); put_u16(p + 14, SR); put_u16(p + 16, clipPeak); len = 18; }
  else { int s0 = (clipChunk - 1) * clipPer, n = min(clipPer, CLIP - s0); memcpy(p + 6, clipBuf + s0, 2 * n); len = 6 + 2 * n; }
  dataChar.writeValue(p, len);
  lastChunkUs = now;
  if (++clipChunk >= clipChunks) clipChunk = -1;
}

bool readArm(int16_t *v) {
  uint8_t b[12];
  if (!fast_read(BUS_ARM, 0x6A, 0x22, b, 12)) return false;
  for (int i = 0; i < 6; i++) v[i] = (int16_t)(b[2 * i] | (b[2 * i + 1] << 8));
  return true;
}

// Called at the end of setup(), after the library and motion_init() have configured the hand IMU.
// Two blocks, skipping 0x0C (reserved) and 0x0F (WHO_AM_I), so the restore never writes them.
void handSave() {
  handSaved = fast_read(BUS_HAND, 0x6A, 0x06, handRegA, 6) && fast_read(BUS_HAND, 0x6A, 0x10, handRegB, 10);
  handRegB[2] &= ~0x81;              // CTRL3_C: never write BOOT or SW_RESET back
}
bool handRegsOk() {                  // answers, and still holds its setup (a reset clears CTRL1_XL / CTRL2_G)
  uint8_t c[2];
  return fast_read(BUS_HAND, 0x6A, 0x10, c, 2) && c[0] == handRegB[0] && c[1] == handRegB[1];
}
void handRecover() {
  if (!handSaved || millis() - lastRecoverMs < 250) return;   // a dead IMU must not stall every sample
  lastRecoverMs = millis(); handRecovers++; step(S_HAND_FIX, handRecovers);
  fast_bus_clear(BUS_HAND);
  uint8_t c[2];
  if (!fast_read(BUS_HAND, 0x6A, 0x10, c, 2)) {   // still no answer: power-cycle it (~30 ms, counted as dropped)
    for (uint32_t p : { BUS_HAND.scl, BUS_HAND.sda }) NRF_P0->PIN_CNF[p] = GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos;
    digitalWrite(PIN_LSM6DS3TR_C_POWER, LOW); delay(10);   // lines floating, so the pull-ups don't feed it while off
    digitalWrite(PIN_LSM6DS3TR_C_POWER, HIGH); delay(20);  // LSM6DS3TR-C boot time is ~15 ms
    fast_pin(BUS_HAND.scl); fast_pin(BUS_HAND.sda);
    fast_bus_clear(BUS_HAND);
  }
  uint8_t b[11] = {0x10}, a[7] = {0x06};
  memcpy(b + 1, handRegB, 10); memcpy(a + 1, handRegA, 6);
  if (fast_write(BUS_HAND, 0x6A, b, 11) && fast_write(BUS_HAND, 0x6A, a, 7) && handRegsOk()) handFailRun = 0;
}

void armSave() {
  armSaved = fast_read(BUS_ARM, 0x6A, 0x07, armRegA, 5) && fast_read(BUS_ARM, 0x6A, 0x10, armRegB, 10);
  armRegB[2] &= ~0x81;               // CTRL3_C: never write BOOT or SW_RESET back
}
bool armRegsOk() {
  uint8_t c[2];
  return fast_read(BUS_ARM, 0x6A, 0x10, c, 2) && c[0] == armRegB[0] && c[1] == armRegB[1];
}
static void armPower(bool on);
void armRecover() {                  // called only while armLive is false, at most every ARM_RETRY_MS (~30 ms each)
  if (!armSaved || millis() - lastArmFixMs < ARM_RETRY_MS) return;
  lastArmFixMs = millis(); armRecovers++;
  fast_bus_clear(BUS_ARM);
  uint8_t c[2];
  if (!fast_read(BUS_ARM, 0x6A, 0x10, c, 2)) {   // no answer: power-cycle it, lines floating so pull-ups don't feed it
    for (uint32_t p : { BUS_ARM.scl, BUS_ARM.sda }) NRF_P0->PIN_CNF[p] = GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos;
    armPower(false); delay(10); armPower(true); delay(20);
    fast_pin(BUS_ARM.scl); fast_pin(BUS_ARM.sda);
    fast_bus_clear(BUS_ARM);
  }
  uint8_t b[11] = {0x10}, a[6] = {0x07};
  memcpy(b + 1, armRegB, 10); memcpy(a + 1, armRegA, 5);
  if (fast_write(BUS_ARM, 0x6A, b, 11) && fast_write(BUS_ARM, 0x6A, a, 6) && armRegsOk()) { armLive = true; armFailRun = 0; armZeroRun = 0; }
}

// Forearm IMU (4438 / LSM6DSOX) power from D10 = P1.15 instead of 3V3 (2026-11-06, the D10 LED fix): high drive
// (H0H1), on before Wire/arm init, off in deep sleep with D4/D5 released so its pull-ups aren't fed through SDA/SCL.
static void armPower(bool on) {
  NRF_P1->PIN_CNF[15] = (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) | (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos) |
                        (GPIO_PIN_CNF_PULL_Disabled << GPIO_PIN_CNF_PULL_Pos) | (GPIO_PIN_CNF_DRIVE_H0H1 << GPIO_PIN_CNF_DRIVE_Pos);
  if (on) NRF_P1->OUTSET = 1UL << 15; else NRF_P1->OUTCLR = 1UL << 15;
}

void goToSleep() {
  step(S_SLEEP); if (pdmRunning) { PDM.end(); pdmRunning = false; } BLE.disconnect(); BLE.stopAdvertise();
  if (armOk) { static const uint8_t off[3] = {0x10, 0, 0}; fast_write(BUS_ARM, 0x6A, off, 3); }   // CTRL1_XL = CTRL2_G = 0
  digitalWrite(PIN_LSM6DS3TR_C_POWER, LOW);
  FTW->ENABLE = 0;                                         // TWIM off, then D4/D5 as plain inputs without pull-ups
  for (uint32_t pin : {4u, 5u})
    NRF_P0->PIN_CNF[pin] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos) | (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos) |
                           (GPIO_PIN_CNF_PULL_Disabled << GPIO_PIN_CNF_PULL_Pos);
  armPower(false);
  // Wait for the button to be released before arming wake-on-LOW on D2 (P0.28): otherwise holding past the
  // 2 s mark leaves the button pressed as we enter System OFF, which immediately re-triggers wake (2026-11-08).
  // Auto-sleep and the "sleep" command reach here with D2 already HIGH, so this exits at once. Feed the watchdog
  // (it may be running on battery) so a long hold can't reset the board mid-wait.
  while (digitalRead(D2) == LOW) { if (wdtOn) NRF_WDT->RR[0] = WDT_RR_RR_Reload; delay(10); }
  delay(50);   // debounce the release so a bounce doesn't look like a fresh press
  system_off_wake_on(28);
}

void sendStatus() {  // n = 0 marks a status notification: vbat u16, charging u8, dropped u32, hz u16,
                     // then (breadcrumb build) RESETREAS at boot u32, previous boot's last step u16 + detail u32, boots u16,
                     // then BLE transmit credits: pending u8, max u8, credits released u16, dropped HCI rx packets u16,
                     // then (2026-10-28) failed hand IMU reads u32, hand IMU recoveries u16 (bytes 33..38)
  uint8_t p[6 + 9 + 12 + 6 + 6 + 16];
  put_u32(p, seq); p[4] = 0; p[5] = armLive;
  step(S_BATT); uint16_t mv = battery_mV(); step(S_STATUS);
  put_u16(p + 6, mv); p[8] = battery_charging(); put_u32(p + 9, dropped); put_u16(p + 13, imuHz);
  put_u32(p + 15, resetReason); put_u16(p + 19, prevStep); put_u32(p + 21, prevDetail); put_u16(p + 25, bootCount);
  p[27] = BLE_PEND(); p[28] = BLE_MAXP(); put_u16(p + 29, BLE_REL()); put_u16(p + 31, (uint16_t)BLE_RXD());
  put_u32(p + 33, handFails); put_u16(p + 37, handRecovers);
  put_u32(p + 39, fastErrAnack); put_u32(p + 43, fastErrDnack); put_u32(p + 47, fastErrTimeout); put_u32(p + 51, loopMaxUs); loopMaxUs = 0;   // development (bytes 39..54)
  dataChar.writeValue(p, sizeof(p));
}

void onCtrl(BLEDevice, BLECharacteristic c) {
  char s[33] = {0}; int n = min(c.valueLength(), 32); memcpy(s, c.value(), n);
  step(S_CTRL, (uint32_t)s[0] | (uint32_t)s[1] << 8 | (uint32_t)s[2] << 16 | (uint32_t)s[3] << 24);   // first 4 letters
  if (!strncmp(s, "probe", 5)) {
    step(S_PROBE);
    for (int i = 0; i < MAXV; i++) buf[i] = i; dataChar.writeValue(buf, MAXV);
  } else if (!strncmp(s, "start", 5)) {
    int hz = 200, b = 8, mic = 1; sscanf(s, "start %d %d %d", &hz, &b, &mic);
    step(S_MIC_STOP, hz); micStop(); micOn = mic != 0; step(S_MIC_START, mic); micStart(); clipChunk = -1; peakVal = 0; lastFastUs = 0; voiceOn = false; quietSinceUs = micros();
    imuHz = constrain(hz, 10, 800); periodUs = 1000000UL / imuHz;
    batch = constrain(b, 1, (MAXV - 6) / 28);
    seq = 0; dropped = 0; nInBatch = 0; nextUs = micros(); streaming = true; digitalWrite(LEDG, LOW);
    wdtStart();
    step(S_START_DONE, hz);
  } else if (!strncmp(s, "stop", 4)) {
    step(S_STOP); streaming = false; micStop(); digitalWrite(LEDG, HIGH);
  } else if (!strncmp(s, "status", 6)) {
    sendStatus();
  } else if (!strncmp(s, "hb", 2)) {      // heartbeat from the phone page (every 2 s): arms the stale-link guard
    lastHb = millis(); hbOn = true;
  } else if (!strncmp(s, "listen", 6)) {   // the PC can also start voice (e.g. from a key press)
    step(S_LISTEN); voiceBegin(micros());
  } else if (!strncmp(s, "dev arm ", 8)) {    // development: "dev arm 0" stops reading the forearm IMU, "dev arm 1" resumes
    devArmOff = s[8] == '0';
  } else if (!strncmp(s, "dev armcut", 10)) { // development: cut the 4438's power (D10), like its plug lifting; armRecover() must bring it back
    armPower(false);
  } else if (!strncmp(s, "dev khz ", 8)) {    // development: I2C clock 100 / 250 / 400 kHz
    int k = atoi(s + 8); FTW->FREQUENCY = k <= 100 ? TWIM_FREQUENCY_FREQUENCY_K100 : k <= 250 ? TWIM_FREQUENCY_FREQUENCY_K250 : TWIM_FREQUENCY_FREQUENCY_K400;
  } else if (!strncmp(s, "dev fifo ", 9)) {   // development: "dev fifo 0" stops the 833 Hz FIFO drain
    devFifoOff = s[9] == '0';
  } else if (!strncmp(s, "hangtest", 8)) {  // development: freeze the loop on purpose to check the watchdog path
    step(S_CTRL, 0x48414E47); if (wdtOn) while (true) {}
  } else if (!strncmp(s, "sleep", 5)) {
    goToSleep();
  }
}

// Watchdog (2026-10-27): starts on battery as before, and now also when streaming starts on USB power, because a
// real hang on USB (it ignored even the 1200-baud upload touch) otherwise needs a hand on RST. 4 s timeout. It keeps
// running into the bootloader, so after a session that streamed: press RST before uploading. Its interrupt (if
// interrupts still run) saves the interrupted instruction address in the breadcrumb: step |= 0x8000, detail = PC.
extern "C" void WDT_IRQHandler(void);
void wdtStart() {
  if (wdtOn) return;
  NRF_WDT->CONFIG = WDT_CONFIG_SLEEP_Msk; NRF_WDT->CRV = 4 * 32768; NRF_WDT->RREN = WDT_RREN_RR0_Msk;
  NRF_WDT->INTENSET = WDT_INTENSET_TIMEOUT_Msk;
  NVIC_SetVector(WDT_IRQn, (uint32_t)&WDT_IRQHandler);   // mbed runs from a RAM vector table: register it there
  NVIC_SetPriority(WDT_IRQn, 0); NVIC_ClearPendingIRQ(WDT_IRQn); NVIC_EnableIRQ(WDT_IRQn);
  NRF_WDT->TASKS_START = 1; wdtOn = true;
}
extern "C" void wdt_capture(uint32_t *frame) {      // frame = the stacked r0-r3, r12, lr, pc, xpsr
  crumb->detail = frame[6]; crumb->step |= 0x8000;
  while (true) {}                                   // reset follows in ~2 cycles of 32 kHz
}
extern "C" __attribute__((naked)) void WDT_IRQHandler(void) {
  __asm volatile("tst lr, #4\n ite eq\n mrseq r0, msp\n mrsne r0, psp\n b wdt_capture\n");
}

// Development: one status line per second over USB serial, never blocking (skipped when the host isn't reading), so a
// "stopped" glove on a PC shows whether its loop still runs and what it believes (connected, streaming, mic samples).
uint32_t lastAlive = 0;
void aliveLine(bool conn) {
  if (millis() - lastAlive < 1000) return;
  lastAlive = millis();
  char b[240];
  int n = snprintf(b, sizeof b, "alive ms=%lu conn=%d strm=%d seq=%lu ring=%lu hb=%d voice=%d clip=%d step=%lu pend=%u/%u rel=%u rxdrop=%lu hfail=%lu hfix=%u arm=%d afail=%lu afix=%u anack=%lu dnack=%lu ovr=%lu tmo=%lu\n",
                   (unsigned long)millis(), conn, streaming, (unsigned long)seq, (unsigned long)ringCount, hbOn, voiceOn, clipChunk, (unsigned long)crumb->step,
                   (unsigned)BLE_PEND(), (unsigned)BLE_MAXP(), (unsigned)BLE_REL(), (unsigned long)BLE_RXD(), (unsigned long)handFails, (unsigned)handRecovers,
                   armOk ? (int)armLive : -1, (unsigned long)armFails, (unsigned)armRecovers, (unsigned long)fastErrAnack, (unsigned long)fastErrDnack, (unsigned long)fastErrOverrun, (unsigned long)fastErrTimeout);
  if (Serial) Serial.write((const uint8_t *)b, n);   // only while a host has the port open (DTR); this core's availableForWrite() is always 0
}

void setup() {
  crumbBoot();
  Serial.begin(115200);
  pinMode(LEDR, OUTPUT); pinMode(LEDG, OUTPUT); pinMode(LEDB, OUTPUT);
  digitalWrite(LEDR, HIGH); digitalWrite(LEDG, HIGH); digitalWrite(LEDB, HIGH);
  pinMode(D2, INPUT_PULLUP);
  battery_init(true);

  hand.settings.accelRange = 16; hand.settings.accelSampleRate = 833; hand.settings.accelBandWidth = 400;
  hand.settings.gyroRange = 2000; hand.settings.gyroSampleRate = 833;
  if (hand.begin() != 0) digitalWrite(LEDR, LOW);
  armPower(true); delay(20);                               // 4438 on D10: boot time before the first I2C access
  Wire.begin(); Wire.setClock(400000);
  armOk = arm.begin_I2C(0x6A, &Wire);
  if (armOk) {
    arm.setAccelRange(LSM6DS_ACCEL_RANGE_16_G); arm.setGyroRange(LSM6DS_GYRO_RANGE_2000_DPS);
    arm.setAccelDataRate(LSM6DS_RATE_833_HZ); arm.setGyroDataRate(LSM6DS_RATE_833_HZ);
  }
  fast_i2c_init();   // from here on, IMU reads go through TWIM; Wire must not be used again
  motion_init(armOk);
  handSave();                         // the hand IMU's registers, for handRecover()
  if (armOk) { armSave(); armLive = true; }   // the forearm's, for armRecover()

  pdmBeginOnce();                     // before BLE.begin(): see the PDM note above
  step(S_SETUP_BLE);
  if (!BLE.begin()) { digitalWrite(LEDR, LOW); while (true) {} }
  BLE.setLocalName("SensorGlove"); BLE.setDeviceName("SensorGlove");
  BLE.setConnectionInterval(6, 12);  // 7.5-15 ms
  BLE.setAdvertisedService(svc);
  svc.addCharacteristic(dataChar); svc.addCharacteristic(ctrlChar);
  BLE.addService(svc);
  ctrlChar.setEventHandler(BLEWritten, onCtrl);
  BLE.advertise();
  lastConn = millis();
  step(S_SETUP_DONE);
}

void loop() {
  NRF_WDT->RR[0] = WDT_RR_RR_Reload;
  { uint32_t u = micros(); if (loopLastUs && u - loopLastUs > loopMaxUs) loopMaxUs = u - loopLastUs; loopLastUs = u; }
  step(S_LOOP);
  BLE.poll();
  step(S_POLLED);
  bool conn = BLE.connected();
  bool usb = NRF_POWER->USBREGSTATUS & POWER_USBREGSTATUS_VBUSDETECT_Msk;  // never sleep on USB power (sleep drops USB)
  // Watchdog, battery only: restarts the glove 3 s after the loop stops (one hang seen in hands-on clip tests,
  // 2026-10-22). Not on USB: it survives the soft reset into the bootloader, which does not feed it, so a serial
  // upload dies after 3 s. If it was started (unplugged once since boot), uploads fail once and the board lands in
  // the bootloader on a new port (/dev/ttyACM1): upload again to that port, or press RST before uploading.
  if (!usb) wdtStart();
  if (conn && hbOn && millis() - lastHb > 15000) {       // the host stopped sending heartbeats: drop the stale link
    step(S_STALE); hbOn = false; BLE.disconnect(); conn = false;
  }
  aliveLine(conn);
  if (conn || usb) lastConn = millis();
  if (conn && !voiceOn) digitalWrite(LEDB, HIGH);   // the advertising blink can leave blue on when a host connects
  if (!conn) {                       // also on USB power now: a lost host must not leave the glove "streaming"
    step(S_DISCONN);
    if (streaming) { streaming = false; micStop(); }
    hbOn = false; digitalWrite(LEDG, HIGH);
    digitalWrite(LEDB, (millis() / 500) % 4 ? HIGH : LOW);  // short blue blink while advertising
    if (!usb && millis() - lastConn > 20UL * 60 * 1000) goToSleep();
  }
  if (digitalRead(D2) == LOW) { if (!btnDown) btnDown = millis(); else if (millis() - btnDown > 2000) goToSleep(); }
  else btnDown = 0;
  if (!streaming) { step(S_IDLE); return; }

  uint32_t now = micros();
  if ((int32_t)(now - nextUs) >= 0) {
    nextUs += periodUs;
    if ((int32_t)(now - nextUs) > (int32_t)periodUs) { dropped += (now - nextUs) / periodUs; nextUs = now + periodUs; }
    if (nInBatch == 0) { put_u32(buf, seq); buf[5] = armLive; }
    uint8_t *f = buf + 6 + 28 * nInBatch;
    int16_t v[12] = {0}; uint8_t b[12];
    step(S_IMU_HAND, seq);
    if (fast_read(BUS_HAND, 0x6A, 0x22, b, 12)) {   // OUTX_L_G: gyro xyz then accel xyz
      for (int i = 0; i < 6; i++) v[i] = (int16_t)(b[2 * i] | (b[2 * i + 1] << 8));
      handFailRun = 0;
    } else {                                         // v stays 0: never send the unread buffer
      handFails++;
      if (++handFailRun >= 3) handRecover();
    }
    if (armOk && !devArmOff) {
      step(S_IMU_ARM, seq);
      if (!armLive) armRecover();
      else if (!readArm(v + 6)) { armFails++; if (++armFailRun >= 3) armLive = false; }
      else {
        armFailRun = 0;
        bool zero = true; for (int i = 6; i < 12; i++) if (v[i]) { zero = false; break; }
        armZeroRun = zero ? armZeroRun + 1 : 0;
        if (armZeroRun >= ARM_ZERO_N) armLive = false;
      }
      if (!armLive) for (int i = 6; i < 12; i++) v[i] = 0;   // never send half-read or stale forearm values
    }
    const int16_t *g = armLive ? v + 6 : v;        // forearm gyro, or the hand's if there is no live arm IMU
    if (abs(g[0]) > SWING_RAW || abs(g[1]) > SWING_RAW || abs(g[2]) > SWING_RAW) lastFastUs = now ? now : 1;
    if (micOn) checkTap(v, now);
    put_u32(f, now); memcpy(f + 4, v, 24);
    seq++;
    if (++nInBatch == batch) { step(S_IMU_SEND, seq); buf[4] = batch; dataChar.writeValue(buf, 6 + 28 * batch); nInBatch = 0; }
  }
  step(S_DRAIN); if (!devFifoOff) motion_drain(lastFastUs != 0 || swingActive);   // 833 Hz kept only around swings (I2C time)
  if (micOn) {
    step(S_SCAN, ringCount); scanSound(now);
    if (voiceOn) { step(S_VOICE, voiceChunk); sendVoiceChunk(micros()); }
    else if (clipChunk >= 0) { step(S_CLIP, clipChunk); sendClipChunk(micros()); }
    else { step(S_MOTION, motionChunk); sendMotionChunk(micros()); }
  }
  if (millis() - lastStatus > 1000) {
    lastStatus = millis();
    if (handSaved && !handRegsOk()) handRecover();   // a reset IMU still answers, but with its setup cleared
    if (armLive && armSaved && !devArmOff && !armRegsOk()) armLive = false;   // the same for the forearm
    sendStatus();
  }
}
