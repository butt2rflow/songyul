// Packet framing shared by the XIAO sketches and host/stream.py. Keep all copies identical
// (host/check_proto.py compares them).
//
//   0xA5 0x5A | type u8 | len u16 | payload (len bytes) | sum u16
//   sum = 16-bit sum of the type, both len bytes and all payload bytes. All values little-endian.
//
// type 1 IMU    : seq u32, t_us u32, flags u8, hand gx gy gz ax ay az (6 x i16), arm (6 x i16)  = 33 bytes
//                 flags bit0 = arm IMU present, bit1 = came over BLE (t_us is the glove's clock)
// type 2 AUDIO  : first_sample u32, t_us u32, n x i16 samples (16 kHz mono)
// type 3 STATUS : t_us u32, vbat_mV u16, charging u8, imu_hz u16, dropped u32, mtu u16
// type 4 TEXT   : UTF-8 text (boot banner, errors)
// type 5 CLIP   : one BLE chunk of an impact sound clip, forwarded unchanged by the receiver:
//                 clip_id u16, chunk u16, 0xFE, 0, then chunk 0 = impact_t_us u32, pre u16, total u16, rate u16, peak u16
//                 and chunks 1.. = int16 samples in order (the glove's clock, like BLE IMU frames)
// Raw units: accel +-16 g -> 0.488 mg/LSB, gyro +-2000 dps -> 70 mdps/LSB (same for LSM6DS3TR-C and LSM6DSOX).
#pragma once
#include <Arduino.h>

enum : uint8_t { PKT_IMU = 1, PKT_AUDIO = 2, PKT_STATUS = 3, PKT_TEXT = 4, PKT_CLIP = 5 };

static inline void pkt_send(Stream &out, uint8_t type, const uint8_t *payload, uint16_t len) {
  uint8_t head[5] = {0xA5, 0x5A, type, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
  uint16_t sum = type + head[3] + head[4];
  for (uint16_t i = 0; i < len; i++) sum += payload[i];
  out.write(head, 5);
  out.write(payload, len);
  uint8_t tail[2] = {(uint8_t)(sum & 0xFF), (uint8_t)(sum >> 8)};
  out.write(tail, 2);
}

static inline void pkt_text(Stream &out, const char *s) { pkt_send(out, PKT_TEXT, (const uint8_t *)s, strlen(s)); }

static inline void put_u16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static inline void put_u32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

// ---- XIAO nRF52840 Sense board helpers (pin indices from the Seeeduino:mbed variant) ----
// Index 22 = P0_13 HICHG (LOW = 100 mA charge, input/hi-Z = 50 mA), 23 = P0_17 ~CHG (LOW while charging),
// 32 = P0_14 VBAT_ENABLE (keep LOW: HIGH can put up to VBAT on the 3.6 V-max P0_31 ADC pin), PIN_VBAT = P0_31 ADC.
#define XIAO_PIN_HICHG 22
#define XIAO_PIN_CHG_N 23
#define XIAO_PIN_VBAT_EN PIN_VBAT_ENABLE

static inline void battery_init(bool fast_charge) {
  pinMode(XIAO_PIN_VBAT_EN, OUTPUT);
  digitalWrite(XIAO_PIN_VBAT_EN, LOW);  // never HIGH
  if (fast_charge) { pinMode(XIAO_PIN_HICHG, OUTPUT); digitalWrite(XIAO_PIN_HICHG, LOW); }
  else pinMode(XIAO_PIN_HICHG, INPUT);
  pinMode(XIAO_PIN_CHG_N, INPUT);
}

// Reads the SAADC directly with its internal 0.6 V reference (gain 1/6 -> 3.6 V full scale), so the result does not
// depend on the core's analogRead() settings. The old raw*3300UL*1510UL overflowed 32 bits and reported ~2.0 V (2026-10-22).
// P0_31 = AIN7, divider 1 M / 510 k, 40 us acquisition for the ~340 k source.
static inline uint16_t battery_mV() {
  volatile int16_t raw = 0;
  NVIC_DisableIRQ(SAADC_IRQn); NRF_SAADC->INTENCLR = 0xFFFFFFFF;  // polled; keep the core's ADC handler out
  NRF_SAADC->ENABLE = 1;
  NRF_SAADC->RESOLUTION = SAADC_RESOLUTION_VAL_12bit;
  NRF_SAADC->OVERSAMPLE = SAADC_OVERSAMPLE_OVERSAMPLE_Bypass;
  for (int i = 1; i < 8; i++) { NRF_SAADC->CH[i].PSELP = 0; NRF_SAADC->CH[i].PSELN = 0; }
  NRF_SAADC->CH[0].CONFIG = (SAADC_CH_CONFIG_GAIN_Gain1_6 << SAADC_CH_CONFIG_GAIN_Pos) |
                            (SAADC_CH_CONFIG_REFSEL_Internal << SAADC_CH_CONFIG_REFSEL_Pos) |
                            (SAADC_CH_CONFIG_TACQ_40us << SAADC_CH_CONFIG_TACQ_Pos) |
                            (SAADC_CH_CONFIG_MODE_SE << SAADC_CH_CONFIG_MODE_Pos);
  NRF_SAADC->CH[0].PSELP = SAADC_CH_PSELP_PSELP_AnalogInput7;
  NRF_SAADC->CH[0].PSELN = 0;
  NRF_SAADC->RESULT.PTR = (uint32_t)&raw;
  NRF_SAADC->RESULT.MAXCNT = 1;
  NRF_SAADC->EVENTS_STARTED = 0; NRF_SAADC->TASKS_START = 1; while (!NRF_SAADC->EVENTS_STARTED) {}
  NRF_SAADC->EVENTS_END = 0; NRF_SAADC->TASKS_SAMPLE = 1; while (!NRF_SAADC->EVENTS_END) {}
  NRF_SAADC->EVENTS_STOPPED = 0; NRF_SAADC->TASKS_STOP = 1; while (!NRF_SAADC->EVENTS_STOPPED) {}
  NRF_SAADC->CH[0].PSELP = 0;
  NRF_SAADC->ENABLE = 0;
  int32_t r = raw < 0 ? 0 : raw;
  return (uint16_t)((int64_t)r * 3600 * 1510 / (4096 * 510));  // 64-bit: r * 3600 * 1510 overflows 32 bits
}

static inline bool battery_charging() { return digitalRead(XIAO_PIN_CHG_N) == LOW; }

// ---- Deep sleep (System OFF, a few uA) with wake on a button from a pin to GND ----
// Wake restarts the sketch from setup(). nrf_pin = nRF GPIO number (D2 = P0_28 -> 28).
#include "nrf_gpio.h"
static inline void system_off_wake_on(uint32_t nrf_pin) {
  digitalWrite(LEDR, HIGH); digitalWrite(LEDG, HIGH); digitalWrite(LEDB, HIGH);  // LEDs are active LOW
  nrf_gpio_cfg_sense_input(nrf_pin, NRF_GPIO_PIN_PULLUP, NRF_GPIO_PIN_SENSE_LOW);
  delay(50);
  NRF_POWER->SYSTEMOFF = 1;
  while (true) {}
}
