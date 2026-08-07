#pragma once

// TinyUSB configuration for RP2350 CDC streaming device

#define CFG_TUSB_MCU          OPT_MCU_RP2040  // RP2350 uses the same TinyUSB target
#define CFG_TUSB_OS           OPT_OS_NONE      // bare-metal, no RTOS
#define CFG_TUSB_DEBUG        0

// CDC only — one interface
#define CFG_TUD_CDC           1
#define CFG_TUD_MSC           0
#define CFG_TUD_HID           0
#define CFG_TUD_MIDI          0
#define CFG_TUD_VENDOR        0

// CDC TX buffer: large enough to hold ~70 packets before a flush
// 14 bytes/pkt × 70 = 980 bytes; round up to 1024
#define CFG_TUD_CDC_RX_BUFSIZE  64
#define CFG_TUD_CDC_TX_BUFSIZE  1024

#define CFG_TUD_ENDPOINT0_SIZE  64
