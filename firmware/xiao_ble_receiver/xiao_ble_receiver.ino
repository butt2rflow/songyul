// Second XIAO (any nRF52840 XIAO) on the PC's USB: connects to "SensorGlove" and turns its BLE
// notifications into the same USB packets as xiao_usb_stream, so host/stream.py works unchanged.
// Host commands: "start <imu_hz> <mic 0|1>" (probes the usable packet size first), "stop", "info", "sleep".
// With mic 1 the glove also sends a 0.5 s impact sound clip after each swing (packet type 5).
#include <ArduinoBLE.h>
#include "proto.h"

#define SVC_UUID  "7e5a0001-2f3b-4c1d-9a8e-0b1c2d3e4f50"
#define DATA_UUID "7e5a0002-2f3b-4c1d-9a8e-0b1c2d3e4f50"
#define CTRL_UUID "7e5a0003-2f3b-4c1d-9a8e-0b1c2d3e4f50"

BLEDevice glove;
BLECharacteristic dataChar, ctrlChar;
int usable = 0;  // bytes that actually arrive per notification (found by the probe)
bool probing = false;
uint16_t lastHz = 200;

void text(const char *s) { pkt_text(Serial, s); }
void handleNotify();
void onData(BLEDevice, BLECharacteristic) { handleNotify(); }  // every notification; valueUpdated() polling kept only the latest

bool connectGlove() {
  BLE.scanForUuid(SVC_UUID);
  uint32_t t0 = millis();
  while (millis() - t0 < 5000) {
    BLEDevice d = BLE.available();
    if (d) {
      BLE.stopScan();
      if (!d.connect()) { text("connect failed"); return false; }
      if (!d.discoverAttributes()) { text("discover failed"); d.disconnect(); return false; }  // also exchanges MTU
      dataChar = d.characteristic(DATA_UUID); ctrlChar = d.characteristic(CTRL_UUID);
      if (!dataChar || !ctrlChar || !dataChar.subscribe()) { text("glove service incomplete"); d.disconnect(); return false; }
      dataChar.setEventHandler(BLEUpdated, onData);
      glove = d; text("glove connected"); return true;
    }
  }
  BLE.stopScan(); text("glove not found (is it awake? press its button)"); return false;
}

void ctrl(const char *s) { if (glove && glove.connected()) ctrlChar.writeValue((const uint8_t *)s, strlen(s), false); }

void handleNotify() {
  int len = dataChar.valueLength(); const uint8_t *v = dataChar.value();
  if (probing) { usable = len; probing = false; return; }
  if (len < 6) return;
  if (v[4] == 0xFE) { pkt_send(Serial, PKT_CLIP, v, len); return; }  // impact sound chunk: pass through
  uint32_t seq0 = v[0] | (v[1] << 8) | ((uint32_t)v[2] << 16) | ((uint32_t)v[3] << 24);
  uint8_t n = v[4], armOk = v[5];
  if (n == 0 && len >= 15) {  // status
    uint8_t p[15]; put_u32(p, micros()); memcpy(p + 4, v + 6, 3);  // vbat u16, charging u8
    memcpy(p + 7, v + 13, 2); memcpy(p + 9, v + 9, 4); put_u16(p + 13, usable + 3);
    pkt_send(Serial, PKT_STATUS, p, sizeof(p)); return;
  }
  for (int i = 0; i < n && 6 + 28 * (i + 1) <= len; i++) {
    const uint8_t *f = v + 6 + 28 * i; uint8_t p[33];
    put_u32(p, seq0 + i); memcpy(p + 4, f, 4); p[8] = (armOk ? 1 : 0) | 2; memcpy(p + 9, f + 4, 24);
    pkt_send(Serial, PKT_IMU, p, sizeof(p));
  }
}

void start(int hz, int mic) {
  if (!(glove && glove.connected()) && !connectGlove()) return;
  probing = true; usable = 0; ctrl("probe");
  uint32_t t0 = millis(); while (probing && millis() - t0 < 2000) BLE.poll();
  int batch = (usable - 6) / 28;
  char s[64]; snprintf(s, sizeof(s), "probe: %d bytes per notification -> %d frames", usable, batch); text(s);
  if (batch < 1) { text("packets too small (MTU not raised); lower expectations: try start 50"); batch = 0; }
  snprintf(s, sizeof(s), "start %d %d %d", hz, batch < 1 ? 1 : batch, mic); ctrl(s);
}

void setup() {
  Serial.begin(115200);
  pinMode(LEDB, OUTPUT); digitalWrite(LEDB, HIGH);
  if (!BLE.begin()) { while (true) { text("BLE init failed"); delay(1000); } }
}

String line;
void loop() {
  BLE.poll();
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch != '\n') { if (line.length() < 40) line += ch; continue; }
    line.trim();
    if (line.startsWith("start")) { int hz = 200, mic = 1; sscanf(line.c_str(), "start %d %d", &hz, &mic); lastHz = hz; start(hz, mic); }
    else if (line == "stop") ctrl("stop");
    else if (line == "info") { text(glove && glove.connected() ? "receiver v1, glove connected" : "receiver v1, no glove"); ctrl("status"); }
    else if (line == "sleep") ctrl("sleep");
    line = "";
  }
  digitalWrite(LEDB, glove && glove.connected() ? LOW : HIGH);
}
