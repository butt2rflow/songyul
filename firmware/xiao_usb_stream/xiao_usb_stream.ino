// XIAO nRF52840 Sense -> USB serial stream: on-board IMU (hand), optional LSM6DSOX on D4/D5 (arm), PDM mic.
// Board: Seeeduino:mbed:xiaonRF52840Sense. Libraries: Seeed Arduino LSM6DS3, Adafruit LSM6DS.
// Host: python host/stream.py PORT --seconds 10 --out take.npz
// Commands (text lines from the host): "start <imu_hz> <mic 0|1>", "stop", "info", "sleep".
// Button D2 -> GND (optional): hold 2 s = deep sleep; press again to wake.
#include <Wire.h>
#include <PDM.h>
#include <LSM6DS3.h>
#include <Adafruit_LSM6DSOX.h>
#include "proto.h"

LSM6DS3 hand(I2C_MODE, 0x6A);  // on-board, on Wire1 (the library switches the bus for XIAO Sense)
Adafruit_LSM6DSOX arm;          // STEMMA QT board on Wire (D4 SDA, D5 SCL), address 0x6A
bool armOk = false, streaming = false, micOn = false;
uint16_t imuHz = 400;
uint32_t periodUs = 2500, nextUs = 0, seq = 0, dropped = 0, lastStatus = 0;

const int AUDIO_N = 256;           // samples per PDM callback block at 16 kHz = 16 ms
volatile int16_t audioBuf[2][AUDIO_N];
volatile uint8_t audioReady = 0xFF, audioWrite = 0;
volatile uint32_t audioCount = 0, audioOverrun = 0;
uint32_t audioFirst = 0;

void onPDM() {
  int n = PDM.available();
  if (n > (int)sizeof(audioBuf[0])) n = sizeof(audioBuf[0]);
  if (audioReady != 0xFF) audioOverrun++;  // the loop has not sent the previous block yet
  PDM.read((void *)audioBuf[audioWrite], n);
  audioReady = audioWrite; audioWrite ^= 1;
  audioCount += n / 2;
}

bool readArm(int16_t *v) {  // gyro xyz then accel xyz, one 12-byte burst from OUTX_L_G (0x22)
  Wire.beginTransmission(0x6A); Wire.write(0x22);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(0x6A, 12) != 12) return false;
  uint8_t b[12]; for (int i = 0; i < 12; i++) b[i] = Wire.read();
  for (int i = 0; i < 6; i++) v[i] = (int16_t)(b[2 * i] | (b[2 * i + 1] << 8));
  return true;
}

void sendStatus() {
  uint8_t p[15];
  put_u32(p, micros()); put_u16(p + 4, battery_mV()); p[6] = battery_charging();
  put_u16(p + 7, imuHz); put_u32(p + 9, dropped + audioOverrun); put_u16(p + 13, 0);
  pkt_send(Serial, PKT_STATUS, p, sizeof(p));
}

void handleCommand(String c) {
  c.trim();
  if (c.startsWith("start")) {
    int hz = 400, mic = 1;
    sscanf(c.c_str(), "start %d %d", &hz, &mic);
    imuHz = constrain(hz, 10, 800); periodUs = 1000000UL / imuHz;
    micOn = mic != 0;
    if (micOn) { audioFirst = audioCount; PDM.onReceive(onPDM); PDM.setBufferSize(sizeof(audioBuf[0])); PDM.begin(1, 16000); }
    seq = 0; dropped = 0; audioOverrun = 0; nextUs = micros(); streaming = true;
    digitalWrite(LEDG, LOW);
  } else if (c == "stop") {
    streaming = false; if (micOn) PDM.end(); micOn = false; digitalWrite(LEDG, HIGH);
  } else if (c == "info") {
    char s[96]; snprintf(s, sizeof(s), "xiao_usb_stream v1 arm=%d vbat=%umV chg=%d", armOk, battery_mV(), battery_charging());
    pkt_text(Serial, s); sendStatus();
  } else if (c == "sleep") {
    goToSleep();
  }
}

void goToSleep() {
  streaming = false; if (micOn) PDM.end();
  if (armOk) { Wire.beginTransmission(0x6A); Wire.write(0x10); Wire.write(0); Wire.write(0); Wire.endTransmission(); }  // CTRL1_XL, CTRL2_G off
  digitalWrite(PIN_LSM6DS3TR_C_POWER, LOW);
  system_off_wake_on(28);  // D2 = P0_28
}

void setup() {
  pinMode(LEDR, OUTPUT); pinMode(LEDG, OUTPUT); pinMode(LEDB, OUTPUT);
  digitalWrite(LEDR, HIGH); digitalWrite(LEDG, HIGH); digitalWrite(LEDB, LOW);  // blue = booting
  pinMode(D2, INPUT_PULLUP);
  battery_init(true);  // 100 mA charge: fine for a 350 mAh cell (about 0.3 C)
  Serial.begin(115200);  // USB CDC; the baud rate is ignored

  hand.settings.accelRange = 16; hand.settings.accelSampleRate = 833; hand.settings.accelBandWidth = 400;
  hand.settings.gyroRange = 2000; hand.settings.gyroSampleRate = 833;
  bool handOk = hand.begin() == 0;

  Wire.begin(); Wire.setClock(400000);
  armOk = arm.begin_I2C(0x6A, &Wire);
  if (armOk) {
    arm.setAccelRange(LSM6DS_ACCEL_RANGE_16_G); arm.setGyroRange(LSM6DS_GYRO_RANGE_2000_DPS);
    arm.setAccelDataRate(LSM6DS_RATE_833_HZ); arm.setGyroDataRate(LSM6DS_RATE_833_HZ);
  }
  digitalWrite(LEDB, HIGH);
  if (!handOk) digitalWrite(LEDR, LOW);  // red = on-board IMU missing
}

String line;
uint32_t btnDown = 0;

void loop() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n') { handleCommand(line); line = ""; } else if (line.length() < 40) line += ch;
  }
  if (digitalRead(D2) == LOW) { if (!btnDown) btnDown = millis(); else if (millis() - btnDown > 2000) goToSleep(); }
  else btnDown = 0;
  if (!streaming) return;

  uint32_t now = micros();
  if ((int32_t)(now - nextUs) >= 0) {
    nextUs += periodUs;
    if ((int32_t)(now - nextUs) > (int32_t)periodUs) { dropped += (now - nextUs) / periodUs; nextUs = now + periodUs; }
    uint8_t p[33]; int16_t v[12] = {0};
    uint8_t b[12];
    hand.readRegisterRegion(b, LSM6DS3_ACC_GYRO_OUTX_L_G, 12);
    for (int i = 0; i < 6; i++) v[i] = (int16_t)(b[2 * i] | (b[2 * i + 1] << 8));
    bool a = armOk && readArm(v + 6);
    put_u32(p, seq++); put_u32(p + 4, now); p[8] = a ? 1 : 0;
    memcpy(p + 9, v, 24);
    pkt_send(Serial, PKT_IMU, p, sizeof(p));
  }
  if (micOn && audioReady != 0xFF) {
    uint8_t idx = audioReady; audioReady = 0xFF;
    static uint8_t p[8 + 2 * AUDIO_N];
    put_u32(p, audioCount - AUDIO_N - audioFirst); put_u32(p + 4, now);
    memcpy(p + 8, (const void *)audioBuf[idx], 2 * AUDIO_N);
    pkt_send(Serial, PKT_AUDIO, p, sizeof(p));
  }
  if (millis() - lastStatus > 1000) { lastStatus = millis(); sendStatus(); }
}
