#pragma once

#include "ring_buffer.h"

// Shared between cores — Core 1 pushes, Core 0 pops.
extern RingBuffer sample_ring;

// Entry point for Core 1.  Launch with multicore_launch_core1().
void sampler_core1_entry(void);
