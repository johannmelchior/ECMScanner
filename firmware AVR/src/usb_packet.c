#include "usb_fifo.h"
#include "usb_packet.h"

typedef enum {
    USB_PACKET_WAIT_SYNC = 0,
    USB_PACKET_WAIT_LEN,
    USB_PACKET_WAIT_CMD,
    USB_PACKET_WAIT_PAYLOAD,
    USB_PACKET_WAIT_CHECKSUM
} usb_packet_state_t;

static usb_packet_state_t packet_state = USB_PACKET_WAIT_SYNC;
static usb_packet_t packet_buffer;
static uint8_t packet_index = 0U;
static uint8_t packet_checksum = 0U;
static uint16_t dbg_sync_seen = 0U;
static uint16_t dbg_frames_ok = 0U;
static uint16_t dbg_checksum_fail = 0U;

static void usb_packet_reset_state(void)
{
    packet_state = USB_PACKET_WAIT_SYNC;
    packet_buffer.command = 0U;
    packet_buffer.length = 0U;
    packet_index = 0U;
    packet_checksum = 0U;
}

void usb_packet_reset(void)
{
    usb_packet_reset_state();
}

bool usb_packet_receive(usb_packet_t *packet)
{
    uint8_t value;

    while (usb_fifo_can_read()) {
        value = usb_fifo_read_u8();

        switch (packet_state) {
        case USB_PACKET_WAIT_SYNC:
            if (value == USB_PACKET_SYNC) {
                ++dbg_sync_seen;
                usb_packet_reset_state();
                packet_state = USB_PACKET_WAIT_LEN;
            }
            break;

        case USB_PACKET_WAIT_LEN:
            if (value > USB_PACKET_MAX_PAYLOAD) {
                usb_packet_reset_state();
                break;
            }

            packet_buffer.length = value;
            packet_checksum = value;
            packet_state = USB_PACKET_WAIT_CMD;
            break;

        case USB_PACKET_WAIT_CMD:
            packet_buffer.command = value;
            packet_checksum ^= value;
            packet_index = 0U;
            packet_state = (packet_buffer.length == 0U) ? USB_PACKET_WAIT_CHECKSUM : USB_PACKET_WAIT_PAYLOAD;
            break;

        case USB_PACKET_WAIT_PAYLOAD:
            packet_buffer.payload[packet_index++] = value;
            packet_checksum ^= value;
            if (packet_index >= packet_buffer.length) {
                packet_state = USB_PACKET_WAIT_CHECKSUM;
            }
            break;

        case USB_PACKET_WAIT_CHECKSUM:
            if (value == packet_checksum) {
                *packet = packet_buffer;
                ++dbg_frames_ok;
                usb_packet_reset_state();
                return true;
            }

            ++dbg_checksum_fail;
            usb_packet_reset_state();
            break;

        default:
            usb_packet_reset_state();
            break;
        }
    }

    return false;
}

bool usb_packet_send(uint8_t command, const uint8_t *payload, uint8_t length)
{
    uint8_t checksum = length ^ command;
    uint8_t i;

    if (length > USB_PACKET_MAX_PAYLOAD) {
        return false;
    }

    if (usb_fifo_write_available() < (uint8_t)(length + 4U)) {
        return false;
    }

    for (i = 0U; i < length; ++i) {
        checksum ^= payload[i];
    }

    usb_fifo_write_u8(USB_PACKET_SYNC);
    usb_fifo_write_u8(length);
    usb_fifo_write_u8(command);
    for (i = 0U; i < length; ++i) {
        usb_fifo_write_u8(payload[i]);
    }
    usb_fifo_write_u8(checksum);
    return true;
}

void usb_packet_get_debug_info(usb_packet_debug_info_t *info)
{
    if (info == 0) {
        return;
    }

    info->sync_seen = dbg_sync_seen;
    info->frames_ok = dbg_frames_ok;
    info->checksum_fail = dbg_checksum_fail;
}