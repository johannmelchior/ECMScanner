#ifndef USB_FIFO_H
#define USB_FIFO_H

#include <stdbool.h>
#include <stdint.h>

/*
 * Camada minima para o FT245RL.
 * A implementacao real depende da pinagem e da logica de handshake da placa.
 */

void usb_fifo_init(void);
void usb_fifo_poll(void);
bool usb_fifo_is_mapped(void);
bool usb_fifo_can_read(void);
bool usb_fifo_can_write(void);
uint8_t usb_fifo_write_available(void);
uint8_t usb_fifo_read_u8(void);
void usb_fifo_write_u8(uint8_t value);

typedef struct {
	uint8_t flags;
	uint8_t rx_buffered;
	uint8_t tx_buffered;
	uint16_t hw_rx_reads;
	uint16_t hw_tx_writes;
	uint8_t last_rx0;
	uint8_t last_rx1;
	uint8_t last_rx2;
	uint8_t last_rx3;
} usb_fifo_debug_info_t;

void usb_fifo_get_debug_info(usb_fifo_debug_info_t *info);

#endif