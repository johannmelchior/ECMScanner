#ifndef BOARD_H
#define BOARD_H

#include <avr/io.h>

/*
 * Ajustar este arquivo assim que a pinagem da interface for confirmada.
 * Os defines abaixo sao placeholders seguros para a fase de bring-up.
 */

#define BOARD_CPU_FREQ_HZ 16000000UL

/* LED de status opcional. Desabilitado para nao conflitar com o barramento FT245RL em PB0. */
#define BOARD_HAS_STATUS_LED 0
#define BOARD_HAS_FT245 1

#define BOARD_LED_DDR  DDRB
#define BOARD_LED_PORT PORTB
#define BOARD_LED_PIN  PB0

/* FT245RL - mapeamento confirmado na placa */
#define FT245_DATA_IN   PINB
#define FT245_DATA_OUT  PORTB
#define FT245_DATA_DDR  DDRB

#define FT245_RD_PORT   PORTD
#define FT245_RD_DDR    DDRD
#define FT245_RD_PIN    PD3

#define FT245_WR_PORT   PORTD
#define FT245_WR_DDR    DDRD
#define FT245_WR_PIN    PD4

#define FT245_TXE_PINR  PIND
#define FT245_TXE_PORT  PORTD
#define FT245_TXE_DDR   DDRD
#define FT245_TXE_PIN   PD5

#define FT245_RXF_PINR  PINE
#define FT245_RXF_PORT  PORTE
#define FT245_RXF_DDR   DDRE
#define FT245_RXF_PIN   PE0

/* K-Line / L9637D - mapeamento confirmado na placa */
#define KLINE_TX_DDR   DDRD
#define KLINE_TX_PORT  PORTD
#define KLINE_TX_PIN   PD1

#define KLINE_RX_PORT  PORTD
#define KLINE_RX_DDR   DDRD
#define KLINE_RX_PINR  PIND
#define KLINE_RX_PIN   PD0

/* SJA1000T - mapeamento confirmado na placa */
#define SJA_DATA_IN    PINA
#define SJA_DATA_OUT   PORTA
#define SJA_DATA_DDR   DDRA

#define SJA_ALE_PORT   PORTE
#define SJA_ALE_DDR    DDRE
#define SJA_ALE_PIN    PE1

#define SJA_CS_PORT    PORTC
#define SJA_CS_DDR     DDRC
#define SJA_CS_PIN     PC7

#define SJA_RD_PORT    PORTD
#define SJA_RD_DDR     DDRD
#define SJA_RD_PIN     PD7

#define SJA_WR_PORT    PORTD
#define SJA_WR_DDR     DDRD
#define SJA_WR_PIN     PD6

#define SJA_INT_PINR   PIND
#define SJA_INT_PORT   PORTD
#define SJA_INT_DDR    DDRD
#define SJA_INT_PIN    PD2

#define SJA_RESET_PORT PORTE
#define SJA_RESET_DDR  DDRE
#define SJA_RESET_PIN  PE2

static inline void board_init(void)
{
#if BOARD_HAS_STATUS_LED
    BOARD_LED_DDR |= _BV(BOARD_LED_PIN);
    BOARD_LED_PORT &= (uint8_t)~_BV(BOARD_LED_PIN);
#endif
}

static inline void board_led_toggle(void)
{
#if BOARD_HAS_STATUS_LED
    BOARD_LED_PORT ^= _BV(BOARD_LED_PIN);
#endif
}

#endif