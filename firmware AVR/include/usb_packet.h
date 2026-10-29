#ifndef USB_PACKET_H
#define USB_PACKET_H

#include <stdbool.h>
#include <stdint.h>

#define USB_PACKET_SYNC 0x5AU
#define USB_PACKET_MAX_PAYLOAD 32U

typedef struct {
    uint8_t command;
    uint8_t length;
    uint8_t payload[USB_PACKET_MAX_PAYLOAD];
} usb_packet_t;

typedef struct {
    uint16_t sync_seen;
    uint16_t frames_ok;
    uint16_t checksum_fail;
} usb_packet_debug_info_t;

void usb_packet_reset(void);
bool usb_packet_receive(usb_packet_t *packet);
bool usb_packet_send(uint8_t command, const uint8_t *payload, uint8_t length);
void usb_packet_get_debug_info(usb_packet_debug_info_t *info);

#endif