#include "ads1262.h"
#include "hardware/gpio.h"
#include "pico/time.h"
#include <string.h>

// ── SPI helpers ──────────────────────────────────────────────────────────────

static inline void cs_lo(const ADS1262 *d) { gpio_put(d->cs_pin, 0); }
static inline void cs_hi(const ADS1262 *d) { gpio_put(d->cs_pin, 1); }

static void wreg(const ADS1262 *d, uint8_t reg, uint8_t val) {
    uint8_t cmd[3] = { ADS1262_CMD_WREG | reg, 0x00, val };
    cs_lo(d);
    spi_write_blocking(d->spi, cmd, 3);
    cs_hi(d);
    busy_wait_us(2);
}

static uint8_t rreg(const ADS1262 *d, uint8_t reg) {
    uint8_t cmd[2] = { ADS1262_CMD_RREG | reg, 0x00 };
    uint8_t result;
    cs_lo(d);
    spi_write_blocking(d->spi, cmd, 2);
    spi_read_blocking(d->spi, 0x00, &result, 1);
    cs_hi(d);
    return result;
}

// ── Public API ───────────────────────────────────────────────────────────────

void ads1262_init(ADS1262 *dev, spi_inst_t *spi,
                  uint cs, uint drdy, uint rst) {
    dev->spi       = spi;
    dev->cs_pin    = cs;
    dev->drdy_pin  = drdy;
    dev->reset_pin = rst;
    dev->cur_idx   = 0;
    dev->n_channels = 0;
    memset(dev->seq, 0, sizeof(dev->seq));

    gpio_init(cs);   gpio_set_dir(cs,   GPIO_OUT); gpio_put(cs,  1);
    gpio_init(drdy); gpio_set_dir(drdy, GPIO_IN);  gpio_pull_up(drdy);
    gpio_init(rst);  gpio_set_dir(rst,  GPIO_OUT); gpio_put(rst, 1);
}

bool ads1262_reset_and_configure(ADS1262 *dev, uint8_t dr,
                                 uint8_t filter, uint8_t gain) {
    gpio_put(dev->reset_pin, 0);
    busy_wait_us(200);
    gpio_put(dev->reset_pin, 1);
    busy_wait_ms(5);

    uint8_t sw_rst = ADS1262_CMD_RESET;
    cs_lo(dev);
    spi_write_blocking(dev->spi, &sw_rst, 1);
    cs_hi(dev);
    busy_wait_ms(2);

    // POWER.RESET is set after reset, cleared on first read
    if (!(rreg(dev, ADS1262_REG_POWER) & 0x10)) return false;

    // STATUS byte prepended + checksum appended to every RDATA1 response
    wreg(dev, ADS1262_REG_INTERFACE, 0x05);

    // Continuous conversion, no chop, DRDY only from ADC1, no extra delay
    wreg(dev, ADS1262_REG_MODE0, 0x00);

    wreg(dev, ADS1262_REG_MODE1, filter);
    wreg(dev, ADS1262_REG_MODE2, gain | dr);

    // Internal 2.5 V reference (REFP0/REFN0 = internal)
    wreg(dev, ADS1262_REG_REFMUX, 0x00);

    return true;
}

void ads1262_set_channels(ADS1262 *dev, const uint8_t *chs, uint8_t n) {
    dev->n_channels = n;
    memcpy(dev->channels, chs, n);
}

void ads1262_start_next(ADS1262 *dev) {
    // Advance round-robin index before issuing conversion
    dev->cur_idx = (dev->cur_idx + 1) % dev->n_channels;
    uint8_t ain = dev->channels[dev->cur_idx];

    // INPMUX: positive = ain, negative = AINCOM (single-ended)
    uint8_t mux = (uint8_t)((ain << 4) | ADS1262_AINCOM);
    cs_lo(dev);
    uint8_t cmds[3] = { ADS1262_CMD_WREG | ADS1262_REG_INPMUX, 0x00, mux };
    spi_write_blocking(dev->spi, cmds, 3);
    cs_hi(dev);
    busy_wait_us(1);

    uint8_t start = ADS1262_CMD_START1;
    cs_lo(dev);
    spi_write_blocking(dev->spi, &start, 1);
    cs_hi(dev);
}

bool ads1262_drdy_active(const ADS1262 *dev) {
    return !gpio_get(dev->drdy_pin);  // active low
}

bool ads1262_read_result(ADS1262 *dev, int32_t *value, uint8_t *status_out) {
    uint8_t cmd = ADS1262_CMD_RDATA1;
    uint8_t rx[6];  // status(1) + data(4) + checksum(1)

    cs_lo(dev);
    spi_write_blocking(dev->spi, &cmd, 1);
    spi_read_blocking(dev->spi, 0x00, rx, 6);
    cs_hi(dev);

    // ADS1262 checksum: sum of [status + 4 data bytes] + 0x9B == rx[5]
    uint8_t sum = rx[0] + rx[1] + rx[2] + rx[3] + rx[4] + 0x9B;
    if (sum != rx[5]) return false;

    *status_out = rx[0];
    *value = (int32_t)(((uint32_t)rx[1] << 24) |
                       ((uint32_t)rx[2] << 16) |
                       ((uint32_t)rx[3] <<  8) |
                        (uint32_t)rx[4]);
    return true;
}
