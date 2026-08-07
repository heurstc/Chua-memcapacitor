#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "hardware/spi.h"

// ── Commands ────────────────────────────────────────────────────────────────
#define ADS1262_CMD_NOP      0x00
#define ADS1262_CMD_RESET    0x06
#define ADS1262_CMD_START1   0x08
#define ADS1262_CMD_STOP1    0x0A
#define ADS1262_CMD_RDATA1   0x12
#define ADS1262_CMD_RREG     0x20  // | reg_addr
#define ADS1262_CMD_WREG     0x40  // | reg_addr

// ── Registers ───────────────────────────────────────────────────────────────
#define ADS1262_REG_POWER     0x00
#define ADS1262_REG_INTERFACE 0x01
#define ADS1262_REG_MODE0     0x02
#define ADS1262_REG_MODE1     0x03
#define ADS1262_REG_MODE2     0x04
#define ADS1262_REG_INPMUX    0x05
#define ADS1262_REG_REFMUX    0x0E

// ── MODE2 field values ───────────────────────────────────────────────────────
// Data rate bits [3:0]
#define ADS1262_DR_38400  0x0F
#define ADS1262_DR_19200  0x0E
#define ADS1262_DR_14400  0x0D
#define ADS1262_DR_7200   0x0C
#define ADS1262_DR_4800   0x0B

// PGA gain bits [6:4]  (set BYPASS_PGA when PGA not used)
#define ADS1262_GAIN_1    0x00
#define ADS1262_GAIN_2    0x10
#define ADS1262_GAIN_4    0x20
#define ADS1262_GAIN_8    0x30
#define ADS1262_BYPASS_PGA 0x80

// ── MODE1 filter bits [7:5] ─────────────────────────────────────────────────
// SINC1 settles in one conversion cycle — essential for fast mux scanning
#define ADS1262_FILTER_SINC1 0x00
#define ADS1262_FILTER_SINC2 0x20
#define ADS1262_FILTER_SINC3 0x40
#define ADS1262_FILTER_SINC4 0x60
#define ADS1262_FILTER_FIR   0x80

// ── INPMUX channel codes ────────────────────────────────────────────────────
#define ADS1262_AIN0    0x0
#define ADS1262_AIN1    0x1
#define ADS1262_AIN2    0x2
#define ADS1262_AIN3    0x3
#define ADS1262_AIN4    0x4
#define ADS1262_AINCOM  0xA  // use as negative input for single-ended

// ── Device handle ────────────────────────────────────────────────────────────
typedef struct {
    spi_inst_t *spi;
    uint cs_pin;
    uint drdy_pin;
    uint reset_pin;
    uint8_t  n_channels;
    uint8_t  channels[6];     // AIN numbers to scan in sequence
    uint8_t  cur_idx;         // index of the conversion currently in progress
    uint16_t seq[6];          // per-channel sequence counter
} ADS1262;

// ── API ──────────────────────────────────────────────────────────────────────

// Initialise GPIO; call before reset_and_configure.
void ads1262_init(ADS1262 *dev, spi_inst_t *spi,
                  uint cs, uint drdy, uint rst);

// Hardware + software reset, then write MODE/INTERFACE/REFMUX registers.
// Returns false if comms verify fails (POWER.RESET bit not set).
bool ads1262_reset_and_configure(ADS1262 *dev, uint8_t dr,
                                 uint8_t filter, uint8_t gain);

// Set the channel scan list (AIN numbers).
void ads1262_set_channels(ADS1262 *dev, const uint8_t *chs, uint8_t n);

// Update INPMUX and send START1 to begin the next conversion.
// Call after reading the previous result to advance the round-robin.
void ads1262_start_next(ADS1262 *dev);

// DRDY is active-low.
bool ads1262_drdy_active(const ADS1262 *dev);

// Read RDATA1 response: status(1) + data(4) + checksum(1).
// Returns false on checksum mismatch.
bool ads1262_read_result(ADS1262 *dev, int32_t *value, uint8_t *status_out);
