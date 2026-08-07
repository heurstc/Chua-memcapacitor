#include "sampler.h"
#include "ads1262.h"
#include "pico/time.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <string.h>

// ── XIAO RP2350 pin assignments ───────────────────────────────────────────────
// Both ADS1262s share the same SPI bus; CS pins isolate them.
//
//  SPI0: SCK=GP6  MOSI=GP7  MISO=GP4
//
//  ADC0 (channels 0,1,2 → global ch 0–2):
//    CS=GP5   DRDY=GP0   RST=GP1
//
//  ADC1 (channels 0,1   → global ch 3–4):
//    CS=GP3   DRDY=GP2   RST=GP28

#define SPI_PORT  spi0
#define PIN_SCK   6
#define PIN_MOSI  7
#define PIN_MISO  4

#define ADC0_CS   5
#define ADC0_DRDY 0
#define ADC0_RST  1

#define ADC1_CS   3
#define ADC1_DRDY 2
#define ADC1_RST  28

// At 38400 SPS with SINC1, multiplexing 3 channels gives ~12800 effective
// SPS per channel on ADC0, and ~19200 on ADC1 (2 channels).
// SINC1 is required here: it settles in exactly one conversion cycle,
// so a mux switch + one conversion yields valid data without extra delay.

static ADS1262 devs[2];

RingBuffer sample_ring;  // zero-initialised in BSS

static void spi_bus_init(void) {
    spi_init(SPI_PORT, 10 * 1000 * 1000);  // 10 MHz — well within ADS1262's 25 MHz max
    spi_set_format(SPI_PORT, 8, SPI_CPOL_0, SPI_CPHA_1, SPI_MSB_FIRST);
    gpio_set_function(PIN_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
}

// Service one ADS1262.  dev_base is the first global channel index for this device.
// Called in a tight polling loop — no blocking.
static void service(ADS1262 *dev, uint8_t dev_base) {
    if (!ads1262_drdy_active(dev)) return;

    int32_t value;
    uint8_t status;
    if (!ads1262_read_result(dev, &value, &status)) return;  // checksum fail — skip

    uint8_t sampled_idx = dev->cur_idx;  // channel that just converted

    // Advance mux and start the next conversion while we store this result.
    if (dev->n_channels > 1) ads1262_start_next(dev);

    Sample s = {
        .channel      = dev_base + sampled_idx,
        .status       = status,
        .seq          = dev->seq[sampled_idx]++,
        .timestamp_us = time_us_32(),
        .value        = value,
    };
    ring_push(&sample_ring, &s);
}

void sampler_core1_entry(void) {
    spi_bus_init();

    // ADC0: scan AIN0, AIN1, AIN2 (Chua state variables x, y, z)
    static const uint8_t adc0_chs[] = { ADS1262_AIN0, ADS1262_AIN1, ADS1262_AIN2 };
    // ADC1: scan AIN0, AIN1 (extended state w, v)
    static const uint8_t adc1_chs[] = { ADS1262_AIN0, ADS1262_AIN1 };

    ads1262_init(&devs[0], SPI_PORT, ADC0_CS, ADC0_DRDY, ADC0_RST);
    ads1262_init(&devs[1], SPI_PORT, ADC1_CS, ADC1_DRDY, ADC1_RST);

    ads1262_reset_and_configure(&devs[0], ADS1262_DR_38400,
                                ADS1262_FILTER_SINC1, ADS1262_BYPASS_PGA);
    ads1262_reset_and_configure(&devs[1], ADS1262_DR_38400,
                                ADS1262_FILTER_SINC1, ADS1262_BYPASS_PGA);

    ads1262_set_channels(&devs[0], adc0_chs, 3);
    ads1262_set_channels(&devs[1], adc1_chs, 2);

    // Prime the mux and fire the first conversion on each device
    ads1262_start_next(&devs[0]);
    // cur_idx advanced to 1 by start_next — reset to 0 so first DRDY yields ch0
    devs[0].cur_idx = 0;
    uint8_t mux0 = (adc0_chs[0] << 4) | ADS1262_AINCOM;
    uint8_t init0[3] = { ADS1262_CMD_WREG | ADS1262_REG_INPMUX, 0x00, mux0 };
    gpio_put(ADC0_CS, 0);
    spi_write_blocking(SPI_PORT, init0, 3);
    gpio_put(ADC0_CS, 1);

    ads1262_start_next(&devs[1]);
    devs[1].cur_idx = 0;
    uint8_t mux1 = (adc1_chs[0] << 4) | ADS1262_AINCOM;
    uint8_t init1[3] = { ADS1262_CMD_WREG | ADS1262_REG_INPMUX, 0x00, mux1 };
    gpio_put(ADC1_CS, 0);
    spi_write_blocking(SPI_PORT, init1, 3);
    gpio_put(ADC1_CS, 1);

    // Start both devices
    uint8_t start = ADS1262_CMD_START1;
    gpio_put(ADC0_CS, 0); spi_write_blocking(SPI_PORT, &start, 1); gpio_put(ADC0_CS, 1);
    gpio_put(ADC1_CS, 0); spi_write_blocking(SPI_PORT, &start, 1); gpio_put(ADC1_CS, 1);

    while (true) {
        service(&devs[0], 0);  // global channels 0,1,2
        service(&devs[1], 3);  // global channels 3,4
    }
}
