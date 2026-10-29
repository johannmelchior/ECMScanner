#include <avr/io.h>
#include <stdbool.h>
#include <util/delay.h>

#include "board.h"
#include "can_sja1000.h"

#define SJA_REG_MOD        0x00U
#define SJA_REG_CMR        0x01U
#define SJA_REG_SR         0x02U
#define SJA_REG_IR         0x03U
#define SJA_REG_IER        0x04U
#define SJA_REG_BTR0       0x06U
#define SJA_REG_BTR1       0x07U
#define SJA_REG_OCR        0x08U
#define SJA_REG_ALC        0x0BU
#define SJA_REG_ECC        0x0CU
#define SJA_REG_EWL        0x0DU
#define SJA_REG_RXERR      0x0EU
#define SJA_REG_TXERR      0x0FU
#define SJA_REG_FRAMEINFO  0x10U
#define SJA_REG_ID1        0x11U
#define SJA_REG_ID2        0x12U
#define SJA_REG_DATA1      0x13U
#define SJA_REG_ACR0       0x10U
#define SJA_REG_AMR0       0x14U
#define SJA_REG_RMC        0x1DU
#define SJA_REG_CDR        0x1FU

#define SJA_MOD_RM         0x01U
#define SJA_MOD_LOM        0x02U  /* Listen Only: sem ACK, sem error frames */

#define SJA_CMR_TR         0x01U
#define SJA_CMR_RRB        0x04U

#define SJA_SR_RBS         0x01U
#define SJA_SR_TBS         0x04U

#define SJA_FRAME_FF       0x80U
#define SJA_FRAME_RTR      0x40U

static void sja_bus_input(void)
{
    SJA_DATA_DDR = 0x00U;
}

static void sja_bus_output(void)
{
    SJA_DATA_DDR = 0xFFU;
}

static void sja_latch_address(uint8_t reg)
{
    sja_bus_output();
    SJA_DATA_OUT = reg;
    SJA_ALE_PORT |= _BV(SJA_ALE_PIN);
    _delay_us(1);
    SJA_ALE_PORT &= (uint8_t)~_BV(SJA_ALE_PIN);
}

static uint8_t sja1000_read_reg(uint8_t reg)
{
    uint8_t value;

    sja_latch_address(reg);
    sja_bus_input();

    SJA_CS_PORT &= (uint8_t)~_BV(SJA_CS_PIN);
    SJA_RD_PORT &= (uint8_t)~_BV(SJA_RD_PIN);
    _delay_us(1);
    value = SJA_DATA_IN;
    SJA_RD_PORT |= _BV(SJA_RD_PIN);
    SJA_CS_PORT |= _BV(SJA_CS_PIN);

    return value;
}

static void sja1000_write_reg(uint8_t reg, uint8_t value)
{
    sja_latch_address(reg);
    sja_bus_output();
    SJA_DATA_OUT = value;

    SJA_CS_PORT &= (uint8_t)~_BV(SJA_CS_PIN);
    SJA_WR_PORT &= (uint8_t)~_BV(SJA_WR_PIN);
    _delay_us(1);
    SJA_WR_PORT |= _BV(SJA_WR_PIN);
    SJA_CS_PORT |= _BV(SJA_CS_PIN);

    sja_bus_input();
}

static bool sja1000_select_bitrate(uint16_t bitrate_kbps, uint8_t *btr0, uint8_t *btr1)
{
    switch (bitrate_kbps) {
    case 1000U:
        *btr0 = 0x00U;
        *btr1 = 0x14U;
        return true;

    case 500U:
        *btr0 = 0x00U;
        *btr1 = 0x1CU;
        return true;

    case 250U:
        *btr0 = 0x01U;
        *btr1 = 0x1CU;
        return true;

    case 125U:
        *btr0 = 0x03U;
        *btr1 = 0x1CU;
        return true;

    case 100U:
        *btr0 = 0x04U;
        *btr1 = 0x1CU;
        return true;

    case 50U:
        *btr0 = 0x09U;
        *btr1 = 0x1CU;
        return true;

    default:
        return false;
    }
}

bool sja1000_init(uint16_t bitrate_kbps)
{
    uint8_t btr0;
    uint8_t btr1;

    if (!sja1000_select_bitrate(bitrate_kbps, &btr0, &btr1)) {
        return false;
    }

    /* Barramento de dados multiplexado AD0..AD7 em PA0..PA7. */
    sja_bus_input();

    /* Linhas de controle do SJA1000T vindas do ATmega162. */
    SJA_ALE_DDR |= _BV(SJA_ALE_PIN);
    SJA_CS_DDR |= _BV(SJA_CS_PIN);
    SJA_RD_DDR |= _BV(SJA_RD_PIN);
    SJA_WR_DDR |= _BV(SJA_WR_PIN);
    SJA_RESET_DDR |= _BV(SJA_RESET_PIN);

    SJA_ALE_PORT &= (uint8_t)~_BV(SJA_ALE_PIN);
    SJA_CS_PORT |= _BV(SJA_CS_PIN);
    SJA_RD_PORT |= _BV(SJA_RD_PIN);
    SJA_WR_PORT |= _BV(SJA_WR_PIN);
    SJA_RESET_PORT |= _BV(SJA_RESET_PIN);

    /* INT# em PD2 como entrada com pull-up interno. */
    SJA_INT_DDR &= (uint8_t)~_BV(SJA_INT_PIN);
    SJA_INT_PORT |= _BV(SJA_INT_PIN);

    /* Reset curto para colocar o controlador em estado conhecido. */
    SJA_RESET_PORT &= (uint8_t)~_BV(SJA_RESET_PIN);
    _delay_ms(1);
    SJA_RESET_PORT |= _BV(SJA_RESET_PIN);

    /* Entrar em reset mode e configurar PeliCAN. */
    sja1000_write_reg(SJA_REG_MOD, SJA_MOD_RM);
    sja1000_write_reg(SJA_REG_CDR, 0x80U);

    /* Filtro aberto para aceitar qualquer frame. */
    sja1000_write_reg(SJA_REG_ACR0 + 0U, 0x00U);
    sja1000_write_reg(SJA_REG_ACR0 + 1U, 0x00U);
    sja1000_write_reg(SJA_REG_ACR0 + 2U, 0x00U);
    sja1000_write_reg(SJA_REG_ACR0 + 3U, 0x00U);
    sja1000_write_reg(SJA_REG_AMR0 + 0U, 0xFFU);
    sja1000_write_reg(SJA_REG_AMR0 + 1U, 0xFFU);
    sja1000_write_reg(SJA_REG_AMR0 + 2U, 0xFFU);
    sja1000_write_reg(SJA_REG_AMR0 + 3U, 0xFFU);

    sja1000_write_reg(SJA_REG_BTR0, btr0);
    sja1000_write_reg(SJA_REG_BTR1, btr1);
    sja1000_write_reg(SJA_REG_OCR, 0x1AU);
    sja1000_write_reg(SJA_REG_IER, 0x00U);
    sja1000_write_reg(SJA_REG_RXERR, 0x00U);
    sja1000_write_reg(SJA_REG_TXERR, 0x00U);

    /* Sair do reset para Listen Only Mode: nao transmite ACK nem error frames.  */
    /* Chamar sja1000_set_listen_only(false) para habilitar TX quando necessario. */
    sja1000_write_reg(SJA_REG_MOD, SJA_MOD_RM | SJA_MOD_LOM);
    sja1000_write_reg(SJA_REG_MOD, SJA_MOD_LOM);
    (void)sja1000_read_reg(SJA_REG_IR);
    (void)sja1000_read_reg(SJA_REG_ECC);
    (void)sja1000_read_reg(SJA_REG_ALC);
    return true;
}

void sja1000_set_listen_only(bool enable)
{
    if (enable) {
        sja1000_write_reg(SJA_REG_MOD, SJA_MOD_RM | SJA_MOD_LOM);
        sja1000_write_reg(SJA_REG_MOD, SJA_MOD_LOM);
    } else {
        sja1000_write_reg(SJA_REG_MOD, SJA_MOD_RM);
        sja1000_write_reg(SJA_REG_MOD, 0x00U);
    }
}

void sja1000_shutdown(void)
{
    /* Coloca o SJA1000 em reset mode: bus-silent, nao transmite nada. */
    sja1000_write_reg(SJA_REG_MOD, SJA_MOD_RM);
}

bool sja1000_read_frame(can_frame_t *frame)
{
    uint8_t frame_info;
    uint8_t id1;
    uint8_t id2;
    uint8_t i;

    if (frame == 0) {
        return false;
    }

    if ((sja1000_read_reg(SJA_REG_SR) & SJA_SR_RBS) == 0U) {
        return false;
    }

    frame_info = sja1000_read_reg(SJA_REG_FRAMEINFO);
    if ((frame_info & SJA_FRAME_FF) != 0U) {
        sja1000_write_reg(SJA_REG_CMR, SJA_CMR_RRB);
        return false;
    }

    frame->extended = false;
    frame->rtr = (frame_info & SJA_FRAME_RTR) != 0U;
    frame->dlc = (uint8_t)(frame_info & 0x0FU);
    if (frame->dlc > 8U) {
        frame->dlc = 8U;
    }

    id1 = sja1000_read_reg(SJA_REG_ID1);
    id2 = sja1000_read_reg(SJA_REG_ID2);
    frame->id = ((uint32_t)id1 << 3) | ((uint32_t)id2 >> 5);

    for (i = 0U; i < frame->dlc; ++i) {
        frame->data[i] = sja1000_read_reg((uint8_t)(SJA_REG_DATA1 + i));
    }

    sja1000_write_reg(SJA_REG_CMR, SJA_CMR_RRB);
    return true;
}

bool sja1000_write_frame(const can_frame_t *frame)
{
    uint8_t frame_info;
    uint8_t i;

    if (frame == 0 || frame->extended || frame->dlc > 8U || frame->id > 0x7FFU) {
        return false;
    }

    if ((sja1000_read_reg(SJA_REG_SR) & SJA_SR_TBS) == 0U) {
        return false;
    }

    frame_info = (uint8_t)(frame->dlc & 0x0FU);
    if (frame->rtr) {
        frame_info |= SJA_FRAME_RTR;
    }

    sja1000_write_reg(SJA_REG_FRAMEINFO, frame_info);
    sja1000_write_reg(SJA_REG_ID1, (uint8_t)(frame->id >> 3));
    sja1000_write_reg(SJA_REG_ID2, (uint8_t)((frame->id & 0x07U) << 5));

    for (i = 0U; i < frame->dlc; ++i) {
        sja1000_write_reg((uint8_t)(SJA_REG_DATA1 + i), frame->data[i]);
    }

    sja1000_write_reg(SJA_REG_CMR, SJA_CMR_TR);
    return true;
}

bool sja1000_get_status(can_status_t *status)
{
    if (status == 0) {
        return false;
    }

    status->status = sja1000_read_reg(SJA_REG_SR);
    status->rx_error_counter = sja1000_read_reg(SJA_REG_RXERR);
    status->tx_error_counter = sja1000_read_reg(SJA_REG_TXERR);
    status->error_code_capture = sja1000_read_reg(SJA_REG_ECC);
    status->arbitration_lost_capture = sja1000_read_reg(SJA_REG_ALC);
    status->error_warning_limit = sja1000_read_reg(SJA_REG_EWL);
    status->rx_message_count = sja1000_read_reg(SJA_REG_RMC);
    return true;
}