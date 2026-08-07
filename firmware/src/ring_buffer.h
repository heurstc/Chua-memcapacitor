#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "pico/sync.h"

// Lock-free SPSC ring buffer — Core 1 produces, Core 0 consumes.
// Size must be a power of 2.
#define RING_BUFFER_SIZE 4096

typedef struct {
    uint8_t  channel;       // global channel index 0–4
    uint8_t  status;        // ADS1262 status byte
    uint16_t seq;           // per-channel sequence counter (wraps)
    uint32_t timestamp_us;  // µs since boot (from time_us_32)
    int32_t  value;         // 32-bit signed ADC result
} __attribute__((packed)) Sample;

typedef struct {
    Sample   buf[RING_BUFFER_SIZE];
    volatile uint32_t head;  // written by Core 1 only
    volatile uint32_t tail;  // written by Core 0 only
} RingBuffer;

static inline bool ring_push(RingBuffer *rb, const Sample *s) {
    uint32_t head = rb->head;
    uint32_t next = (head + 1) & (RING_BUFFER_SIZE - 1);
    if (next == rb->tail) return false;  // full — drop sample
    rb->buf[head] = *s;
    __dmb();                // ensure write visible before head update
    rb->head = next;
    return true;
}

static inline bool ring_pop(RingBuffer *rb, Sample *s) {
    uint32_t tail = rb->tail;
    if (tail == rb->head) return false;  // empty
    *s = rb->buf[tail];
    __dmb();
    rb->tail = (tail + 1) & (RING_BUFFER_SIZE - 1);
    return true;
}

static inline uint32_t ring_count(const RingBuffer *rb) {
    return (rb->head - rb->tail) & (RING_BUFFER_SIZE - 1);
}
