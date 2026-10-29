#include <avr/io.h>
#include <util/delay.h>

#include "board.h"
#include "usb_fifo.h"

#define USB_FIFO_BUFFER_SIZE 64U

typedef struct {
    uint8_t data[USB_FIFO_BUFFER_SIZE];
    uint8_t head;
    uint8_t tail;
    uint8_t count;
} usb_fifo_buffer_t;

static usb_fifo_buffer_t usb_rx_buffer;
static usb_fifo_buffer_t usb_tx_buffer;
static uint16_t usb_hw_rx_reads;
static uint16_t usb_hw_tx_writes;
static uint8_t usb_last_rx_samples[4];
static uint8_t usb_last_rx_sample_count;

static inline bool usb_fifo_buffer_push(usb_fifo_buffer_t *buffer, uint8_t value)
{
    if (buffer->count >= USB_FIFO_BUFFER_SIZE) {
        return false;
    }

    buffer->data[buffer->head] = value;
    buffer->head = (uint8_t)((buffer->head + 1U) % USB_FIFO_BUFFER_SIZE);
    ++buffer->count;
    return true;
}

static inline bool usb_fifo_buffer_pop(usb_fifo_buffer_t *buffer, uint8_t *value)
{
    if (buffer->count == 0U) {
        return false;
    }

    *value = buffer->data[buffer->tail];
    buffer->tail = (uint8_t)((buffer->tail + 1U) % USB_FIFO_BUFFER_SIZE);
    --buffer->count;
    return true;
}

static inline void usb_fifo_bus_input(void)
{
    FT245_DATA_OUT = 0x00U;
    FT245_DATA_DDR = 0x00U;
}

static inline void usb_fifo_bus_output(void)
{
    FT245_DATA_DDR = 0xFFU;
}

static inline bool usb_fifo_hw_can_read(void)
{
    return (FT245_RXF_PINR & _BV(FT245_RXF_PIN)) == 0U;
}

static inline bool usb_fifo_hw_can_write(void)
{
    return (FT245_TXE_PINR & _BV(FT245_TXE_PIN)) == 0U;
}

static inline void usb_fifo_hw_idle(void)
{
    FT245_RD_PORT |= _BV(FT245_RD_PIN);
    FT245_WR_PORT |= _BV(FT245_WR_PIN);
}

static inline void usb_fifo_hw_read_cycle(void)
{
    uint8_t value;

    if (!usb_fifo_hw_can_read()) {
        return;
    }

    usb_fifo_bus_input();
    FT245_RD_PORT &= (uint8_t)~_BV(FT245_RD_PIN);
    _delay_us(1);
    value = FT245_DATA_IN;
    FT245_RD_PORT |= _BV(FT245_RD_PIN);

    usb_last_rx_samples[usb_hw_rx_reads & 0x03U] = value;
    if (usb_last_rx_sample_count < 4U) {
        ++usb_last_rx_sample_count;
    }

    if (usb_fifo_buffer_push(&usb_rx_buffer, value)) {
        ++usb_hw_rx_reads;
    }
}

static inline void usb_fifo_hw_write_cycle(void)
{
    uint8_t value;

    if (!usb_fifo_hw_can_write()) {
        return;
    }

    if (!usb_fifo_buffer_pop(&usb_tx_buffer, &value)) {
        return;
    }

    usb_fifo_bus_output();
    FT245_DATA_OUT = value;
    FT245_WR_PORT &= (uint8_t)~_BV(FT245_WR_PIN);
    FT245_WR_PORT |= _BV(FT245_WR_PIN);
    usb_fifo_bus_input();
    ++usb_hw_tx_writes;
}

void usb_fifo_init(void)
{
    usb_rx_buffer.head = 0U;
    usb_rx_buffer.tail = 0U;
    usb_rx_buffer.count = 0U;
    usb_tx_buffer.head = 0U;
    usb_tx_buffer.tail = 0U;
    usb_tx_buffer.count = 0U;
    usb_hw_rx_reads = 0U;
    usb_hw_tx_writes = 0U;
    usb_last_rx_samples[0] = 0U;
    usb_last_rx_samples[1] = 0U;
    usb_last_rx_samples[2] = 0U;
    usb_last_rx_samples[3] = 0U;
    usb_last_rx_sample_count = 0U;

    if (!usb_fifo_is_mapped()) {
        return;
    }

    usb_fifo_bus_input();
    FT245_RD_DDR |= _BV(FT245_RD_PIN);
    FT245_WR_DDR |= _BV(FT245_WR_PIN);
    FT245_RXF_DDR &= (uint8_t)~_BV(FT245_RXF_PIN);
    FT245_TXE_DDR &= (uint8_t)~_BV(FT245_TXE_PIN);

    FT245_RXF_PORT |= _BV(FT245_RXF_PIN);
    FT245_TXE_PORT |= _BV(FT245_TXE_PIN);
    usb_fifo_hw_idle();
}

void usb_fifo_poll(void)
{
    if (!usb_fifo_is_mapped()) {
        return;
    }

    if (usb_rx_buffer.count < USB_FIFO_BUFFER_SIZE) {
        usb_fifo_hw_read_cycle();
    }

    if (usb_tx_buffer.count != 0U) {
        usb_fifo_hw_write_cycle();
    }
}

bool usb_fifo_is_mapped(void)
{
#if BOARD_HAS_FT245
    return true;
#else
    return false;
#endif
}

bool usb_fifo_can_read(void)
{
    return usb_rx_buffer.count != 0U;
}

bool usb_fifo_can_write(void)
{
    return usb_tx_buffer.count < USB_FIFO_BUFFER_SIZE;
}

uint8_t usb_fifo_write_available(void)
{
    return (uint8_t)(USB_FIFO_BUFFER_SIZE - usb_tx_buffer.count);
}

uint8_t usb_fifo_read_u8(void)
{
    uint8_t value = 0U;

    (void)usb_fifo_buffer_pop(&usb_rx_buffer, &value);
    return value;
}

void usb_fifo_write_u8(uint8_t value)
{
    (void)usb_fifo_buffer_push(&usb_tx_buffer, value);
}

void usb_fifo_get_debug_info(usb_fifo_debug_info_t *info)
{
    uint8_t flags = 0U;
    uint8_t start = 0U;

    if (info == 0) {
        return;
    }

    if ((FT245_RXF_PINR & _BV(FT245_RXF_PIN)) == 0U) {
        flags |= 0x01U;
    }

    if ((FT245_TXE_PINR & _BV(FT245_TXE_PIN)) == 0U) {
        flags |= 0x02U;
    }

    if (usb_rx_buffer.count != 0U) {
        flags |= 0x04U;
    }

    if (usb_tx_buffer.count < USB_FIFO_BUFFER_SIZE) {
        flags |= 0x08U;
    }

    info->flags = flags;
    info->rx_buffered = usb_rx_buffer.count;
    info->tx_buffered = usb_tx_buffer.count;
    info->hw_rx_reads = usb_hw_rx_reads;
    info->hw_tx_writes = usb_hw_tx_writes;

    if (usb_last_rx_sample_count == 0U) {
        info->last_rx0 = 0U;
        info->last_rx1 = 0U;
        info->last_rx2 = 0U;
        info->last_rx3 = 0U;
        return;
    }

    if (usb_last_rx_sample_count < 4U) {
        info->last_rx0 = usb_last_rx_samples[0U];
        info->last_rx1 = (usb_last_rx_sample_count > 1U) ? usb_last_rx_samples[1U] : 0U;
        info->last_rx2 = (usb_last_rx_sample_count > 2U) ? usb_last_rx_samples[2U] : 0U;
        info->last_rx3 = (usb_last_rx_sample_count > 3U) ? usb_last_rx_samples[3U] : 0U;
        return;
    }

    start = (uint8_t)(usb_hw_rx_reads & 0x03U);
    info->last_rx0 = usb_last_rx_samples[start];
    info->last_rx1 = usb_last_rx_samples[(uint8_t)((start + 1U) & 0x03U)];
    info->last_rx2 = usb_last_rx_samples[(uint8_t)((start + 2U) & 0x03U)];
    info->last_rx3 = usb_last_rx_samples[(uint8_t)((start + 3U) & 0x03U)];
}