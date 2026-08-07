#include "tusb.h"
#include <string.h>

// TinyUSB CDC descriptor — appears on Linux as /dev/ttyACM0.
// VID/PID chosen to avoid conflicts; change if you have registered IDs.

#define USB_VID  0x2E8A   // Raspberry Pi VID (permissible for RP2xxx projects)
#define USB_PID  0xC0AB   // arbitrary; not in conflict with Pi standard PIDs
#define USB_BCD  0x0200

tusb_desc_device_t const desc_device = {
    .bLength            = sizeof(tusb_desc_device_t),
    .bDescriptorType    = TUSB_DESC_DEVICE,
    .bcdUSB             = USB_BCD,
    .bDeviceClass       = TUSB_CLASS_MISC,
    .bDeviceSubClass    = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol    = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor           = USB_VID,
    .idProduct          = USB_PID,
    .bcdDevice          = 0x0100,
    .iManufacturer      = 0x01,
    .iProduct           = 0x02,
    .iSerialNumber      = 0x03,
    .bNumConfigurations = 0x01,
};

uint8_t const *tud_descriptor_device_cb(void) {
    return (uint8_t const *)&desc_device;
}

#define CONFIG_TOTAL_LEN  (TUD_CONFIG_DESC_LEN + TUD_CDC_DESC_LEN)
#define EPNUM_CDC_NOTIF   0x81
#define EPNUM_CDC_OUT     0x02
#define EPNUM_CDC_IN      0x82

static uint8_t const desc_fs_config[] = {
    TUD_CONFIG_DESCRIPTOR(1, 2, 0, CONFIG_TOTAL_LEN, 0x00, 100),
    TUD_CDC_DESCRIPTOR(0, 4, EPNUM_CDC_NOTIF, 8, EPNUM_CDC_OUT, EPNUM_CDC_IN, 64),
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
    (void)index;
    return desc_fs_config;
}

static char const *string_descs[] = {
    (const char[]){ 0x09, 0x04 },  // 0: LANGID = English
    "ChaosLab",                     // 1: Manufacturer
    "5D Chaos Monitor",             // 2: Product
    "CH50001",                      // 3: Serial number
    "CDC Data",                     // 4: CDC interface name
};

static uint16_t str_buf[32];

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    (void)langid;
    uint8_t len;

    if (index == 0) {
        memcpy(&str_buf[1], string_descs[0], 2);
        len = 1;
    } else {
        if (index >= (uint8_t)(sizeof(string_descs) / sizeof(*string_descs)))
            return NULL;
        const char *s = string_descs[index];
        len = (uint8_t)strlen(s);
        if (len > 31) len = 31;
        for (uint8_t i = 0; i < len; i++)
            str_buf[1 + i] = s[i];
    }

    str_buf[0] = (TUSB_DESC_STRING << 8) | (2 * len + 2);
    return str_buf;
}
