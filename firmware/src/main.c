#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "tusb.h"
#include "sampler.h"
#include "ring_buffer.h"

// ── USB packet layout (14 bytes) ─────────────────────────────────────────────
//  [0]   0xAD  sync0
//  [1]   0xC0  sync1
//  [2]         channel (0–4)
//  [3–4]       seq (LE uint16)
//  [5–8]       timestamp_us (LE uint32)
//  [9–12]      ADC value (LE int32, two's complement)
//  [13]        XOR checksum of bytes [2..12]

#define SYNC0 0xAD
#define SYNC1 0xC0

// Flush to USB when this many bytes are buffered, or whenever the ring drains.
#define FLUSH_THRESHOLD 896  // ~64 packets; stays under CDC 1 KB tx buffer

static void emit_sample(const Sample *s) {
    uint8_t pkt[14];
    pkt[0] = SYNC0;
    pkt[1] = SYNC1;
    pkt[2] = s->channel;
    pkt[3] = (uint8_t)(s->seq);
    pkt[4] = (uint8_t)(s->seq >> 8);
    pkt[5] = (uint8_t)(s->timestamp_us);
    pkt[6] = (uint8_t)(s->timestamp_us >>  8);
    pkt[7] = (uint8_t)(s->timestamp_us >> 16);
    pkt[8] = (uint8_t)(s->timestamp_us >> 24);
    pkt[9]  = (uint8_t)(s->value);
    pkt[10] = (uint8_t)(s->value >>  8);
    pkt[11] = (uint8_t)(s->value >> 16);
    pkt[12] = (uint8_t)(s->value >> 24);

    uint8_t csum = 0;
    for (int i = 2; i <= 12; i++) csum ^= pkt[i];
    pkt[13] = csum;

    tud_cdc_write(pkt, sizeof(pkt));
}

int main(void) {
    stdio_init_all();
    tusb_init();

    multicore_launch_core1(sampler_core1_entry);

    uint32_t buffered = 0;

    while (true) {
        tud_task();

        if (!tud_cdc_connected()) {
            // Drain the ring so Core 1 never stalls on a full buffer
            Sample s;
            while (ring_pop(&sample_ring, &s)) {}
            continue;
        }

        Sample s;
        while (ring_pop(&sample_ring, &s)) {
            emit_sample(&s);
            buffered += 14;
            if (buffered >= FLUSH_THRESHOLD) {
                tud_cdc_write_flush();
                tud_task();
                buffered = 0;
            }
        }

        if (buffered > 0) {
            tud_cdc_write_flush();
            buffered = 0;
        }
    }
}
