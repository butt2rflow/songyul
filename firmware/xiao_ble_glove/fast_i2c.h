// Fast IMU reads through the nRF52840 TWIM peripheral (I2C with EasyDMA), bypassing the core's Wire.
// Why: on Seeeduino:mbed 2.9.3, Wire is the old byte-by-byte TWI driver and one 12-byte read took ~2.5 ms,
// which capped the glove at ~185 Hz for two IMUs (2026-10-22). A TWIM transfer of the same 13 bytes at 400 kHz
// is ~0.35 ms of bus time. One TWIM instance serves both buses by switching its pins between transfers.
// Use it only after setup(): the libraries' begin() calls still go through Wire, then fast_i2c_init() takes over
// the TWI peripherals, so Wire must not be used afterwards.
#pragma once
#include <Arduino.h>
#include "nrf.h"

struct FastBus { uint32_t scl, sda; };            // nRF GPIO numbers (port 0)
static const FastBus BUS_HAND = { 27, 7 };        // Wire1: on-board LSM6DS3TR-C (P0.27 SCL, P0.07 SDA)
static const FastBus BUS_ARM  = { 5, 4 };         // Wire: D5 = P0.05 SCL, D4 = P0.04 SDA (STEMMA cable)
static const FastBus *fastCur = nullptr;
static NRF_TWIM_Type *const FTW = NRF_TWIM0;
static uint32_t fastErrAnack = 0, fastErrDnack = 0, fastErrOverrun = 0, fastErrTimeout = 0;   // why transfers failed (development)

static inline void fast_pin(uint32_t pin) {       // input + output, pull-up, standard-0 / disconnect-1 (open drain)
  NRF_P0->PIN_CNF[pin] = (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos) | (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos) |
                         (GPIO_PIN_CNF_PULL_Pullup << GPIO_PIN_CNF_PULL_Pos) | (GPIO_PIN_CNF_DRIVE_S0D1 << GPIO_PIN_CNF_DRIVE_Pos);
}

static inline void fast_i2c_init() {
  // take both TWI instances away from the core's driver (Wire / Wire1)
  NVIC_DisableIRQ(SPIM0_SPIS0_TWIM0_TWIS0_SPI0_TWI0_IRQn); NVIC_DisableIRQ(SPIM1_SPIS1_TWIM1_TWIS1_SPI1_TWI1_IRQn);
  NRF_TWI0->ENABLE = 0; NRF_TWI1->ENABLE = 0;
  for (uint32_t p : { BUS_HAND.scl, BUS_HAND.sda, BUS_ARM.scl, BUS_ARM.sda }) fast_pin(p);
  FTW->INTENCLR = 0xFFFFFFFF;
  FTW->FREQUENCY = TWIM_FREQUENCY_FREQUENCY_K400;
  fastCur = nullptr;
}

static inline void fast_select(const FastBus &b) {
  if (fastCur == &b) return;
  FTW->ENABLE = TWIM_ENABLE_ENABLE_Disabled;
  FTW->PSEL.SCL = b.scl; FTW->PSEL.SDA = b.sda;
  FTW->ENABLE = TWIM_ENABLE_ENABLE_Enabled;
  fastCur = &b;
}

// Runs a prepared transfer; true when it ended without an error (NACK) or timeout.
static inline bool fast_run(uint32_t shorts) {
  FTW->SHORTS = shorts;
  FTW->EVENTS_STOPPED = 0; FTW->EVENTS_ERROR = 0; FTW->ERRORSRC = FTW->ERRORSRC;
  // Time limit from the transfer's length: ~25 us per byte at 400 kHz (9 clocks), 4x that at 100 kHz, plus 1 ms.
  // A fixed 3 ms cut off the FIFO drains (up to 24 x 7 = 168 bytes = ~3.8 ms at 400 kHz) half-way (2026-10-28).
  uint32_t bytes = FTW->TXD.MAXCNT + ((shorts & TWIM_SHORTS_LASTTX_STARTRX_Msk) ? FTW->RXD.MAXCNT : 0);
  uint32_t perByte = FTW->FREQUENCY == TWIM_FREQUENCY_FREQUENCY_K100 ? 100 : FTW->FREQUENCY == TWIM_FREQUENCY_FREQUENCY_K250 ? 40 : 25;
  uint32_t limit = 1000 + bytes * perByte;
  FTW->TASKS_STARTTX = 1;
  uint32_t t0 = micros();
  while (!FTW->EVENTS_STOPPED) {
    if (FTW->EVENTS_ERROR) { FTW->EVENTS_ERROR = 0; FTW->TASKS_STOP = 1; }
    // Look at STOPPED again before calling it a timeout: Bluetooth / USB interrupts can hold the CPU for > 3 ms
    // between the loop's check and this one while the DMA transfer finishes fine. Without the recheck ~1 read/s
    // at rest (and bursts at USB plug/unplug) was thrown away as "failed" and zeroed (glove, 2026-10-28: all
    // hand failures were timeouts, no NACK).
    if (micros() - t0 > limit) {
      if (FTW->EVENTS_STOPPED) break;
      fastErrTimeout++;
      // Really stuck: stop, and WAIT for it to stop before the next transfer. Returning right after TASKS_STOP let
      // the next transfer start on a TWIM still stopping, which hung too: a chain of "timeouts" for up to 17 s with
      // garbage forearm values (phone + USB at rest, 2026-10-28). If it won't stop, disable it (reselected next time).
      FTW->TASKS_STOP = 1;
      uint32_t t1 = micros();
      while (!FTW->EVENTS_STOPPED && micros() - t1 < 500) {}
      if (!FTW->EVENTS_STOPPED) { FTW->ENABLE = TWIM_ENABLE_ENABLE_Disabled; fastCur = nullptr; }
      FTW->EVENTS_STOPPED = 0;
      __asm__ volatile("" ::: "memory"); return false;
    }
  }
  // EasyDMA wrote the RX buffer behind the compiler's back: without this barrier the optimizer may keep stale
  // values (the glove streamed zeros / a constant 700 while a debug build with prints read fine, 2026-10-25).
  __asm__ volatile("" ::: "memory");
  uint32_t e = FTW->ERRORSRC;
  if (e & TWIM_ERRORSRC_ANACK_Msk) fastErrAnack++;
  if (e & TWIM_ERRORSRC_DNACK_Msk) fastErrDnack++;
  if (e & TWIM_ERRORSRC_OVERRUN_Msk) fastErrOverrun++;
  return e == 0;
}

// Read n bytes starting at register reg (auto-increment; both LSM6 parts have IF_INC on by default).
static inline bool fast_read(const FastBus &b, uint8_t addr, uint8_t reg, uint8_t *buf, uint8_t n) {
  static uint8_t r; r = reg;
  fast_select(b);
  FTW->ADDRESS = addr;
  FTW->TXD.PTR = (uint32_t)&r; FTW->TXD.MAXCNT = 1;
  FTW->RXD.PTR = (uint32_t)buf; FTW->RXD.MAXCNT = n;
  return fast_run(TWIM_SHORTS_LASTTX_STARTRX_Msk | TWIM_SHORTS_LASTRX_STOP_Msk);
}

static inline bool fast_write(const FastBus &b, uint8_t addr, const uint8_t *data, uint8_t n) {
  fast_select(b);
  FTW->ADDRESS = addr;
  FTW->TXD.PTR = (uint32_t)data; FTW->TXD.MAXCNT = n;
  return fast_run(TWIM_SHORTS_LASTTX_STOP_Msk);
}

// Frees a bus that a device is holding. Pulling USB while streaming (2026-10-28) left the on-board IMU failing every
// read until RST; a device that loses its place mid-read can keep SDA low. Up to 9 SCL pulses let it finish its byte,
// then START + STOP resets every device's bus logic. The pins go back to TWIM use afterwards.
static inline void fast_bus_clear(const FastBus &b) {
  FTW->ENABLE = TWIM_ENABLE_ENABLE_Disabled; fastCur = nullptr;   // pins back under GPIO control
  const uint32_t scl = 1UL << b.scl, sda = 1UL << b.sda;
  NRF_P0->OUTSET = scl | sda; NRF_P0->DIRSET = scl | sda;           // open drain (S0D1): 1 = released to the pull-up
  delayMicroseconds(5);
  for (int i = 0; i < 9 && !(NRF_P0->IN & sda); i++) {
    NRF_P0->OUTCLR = scl; delayMicroseconds(5); NRF_P0->OUTSET = scl; delayMicroseconds(5);
  }
  NRF_P0->OUTCLR = sda; delayMicroseconds(5);                       // START (SDA falls with SCL high) ...
  NRF_P0->OUTSET = sda; delayMicroseconds(5);                       // ... then STOP (SDA rises with SCL high)
  fast_pin(b.scl); fast_pin(b.sda);
}
