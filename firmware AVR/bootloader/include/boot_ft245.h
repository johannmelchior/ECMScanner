/*
 * boot_ft245.h — FT245RL direct I/O para o bootloader (sem FIFO, sem buffer)
 *
 * O bootloader é minimalista: lê e escreve bytes diretamente no barramento
 * FT245RL usando as mesmas definições de pinos do board.h principal.
 * Não usa interrupções nem buffers de software — cada byte é bloqueante.
 */
#ifndef BOOT_FT245_H
#define BOOT_FT245_H

#include <avr/io.h>
#include <util/delay.h>

/* ---- Pinagem FT245RL (mantida igual ao board.h do firmware principal) ---- */
#define BL_DATA_IN   PINB
#define BL_DATA_OUT  PORTB
#define BL_DATA_DDR  DDRB

#define BL_RD_PORT   PORTD
#define BL_RD_DDR    DDRD
#define BL_RD_PIN    PD3

#define BL_WR_PORT   PORTD
#define BL_WR_DDR    DDRD
#define BL_WR_PIN    PD4

#define BL_TXE_PINR  PIND
#define BL_TXE_PIN   PD5   /* TXE# = 0 quando FT245 pode receber (PC pode escrever para AVR TX) */

#define BL_RXF_PINR  PINE
#define BL_RXF_DDR   DDRE
#define BL_RXF_PIN   PE0   /* RXF# = 0 quando FT245 tem dado disponível para leitura */

/* ---- Inicialização ---- */
static inline void bl_ft245_init(void)
{
    /* RD# e WR# como saída, inativos (high) */
    BL_RD_DDR  |= _BV(BL_RD_PIN);
    BL_RD_PORT |= _BV(BL_RD_PIN);
    BL_WR_DDR  |= _BV(BL_WR_PIN);
    BL_WR_PORT |= _BV(BL_WR_PIN);

    /* RXF# como entrada */
    BL_RXF_DDR &= (uint8_t)~_BV(BL_RXF_PIN);

    /* TXE# como entrada (já é por padrão, mas explicita a intenção) */

    /* Barramento de dados como entrada inicialmente */
    BL_DATA_DDR = 0x00U;
    BL_DATA_OUT = 0x00U;
}

/* ---- Leitura bloqueante (aguarda RXF# = 0) ---- */
static inline uint8_t bl_ft245_read(void)
{
    /* Aguarda dado disponível */
    while ((BL_RXF_PINR & _BV(BL_RXF_PIN)) != 0U) { }

    BL_DATA_DDR = 0x00U;   /* barramento como entrada */
    BL_RD_PORT &= (uint8_t)~_BV(BL_RD_PIN);  /* RD# low → FT245 coloca dado no bus */
    _delay_us(1);
    uint8_t value = BL_DATA_IN;
    BL_RD_PORT |= _BV(BL_RD_PIN);             /* RD# high */
    return value;
}

/* ---- Escrita bloqueante (aguarda TXE# = 0) ---- */
static inline void bl_ft245_write(uint8_t value)
{
    /* Aguarda FT245 pronto para receber */
    while ((BL_TXE_PINR & _BV(BL_TXE_PIN)) != 0U) { }

    BL_DATA_DDR = 0xFFU;   /* barramento como saída */
    BL_DATA_OUT = value;
    BL_WR_PORT &= (uint8_t)~_BV(BL_WR_PIN);  /* WR# low → FT245 latcha o byte */
    _delay_us(1);
    BL_WR_PORT |= _BV(BL_WR_PIN);             /* WR# high */
    BL_DATA_DDR = 0x00U;   /* libera barramento */
}

/* ---- Verifica se há dado disponível (não bloqueante) ---- */
static inline uint8_t bl_ft245_can_read(void)
{
    return (BL_RXF_PINR & _BV(BL_RXF_PIN)) == 0U ? 1U : 0U;
}

#endif /* BOOT_FT245_H */
