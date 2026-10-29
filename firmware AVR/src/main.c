#include <avr/interrupt.h>
#include <avr/io.h>
#include <avr/wdt.h>
#include <util/delay.h>

#include "board.h"
#include "can_sja1000.h"
#include "kline.h"
#include "usb_fifo.h"
#include "usb_packet.h"

#define CMD_GET_INFO        0x01U
#define CMD_SET_MODE        0x02U
#define CMD_KLINE_WAKEUP    0x03U
#define CMD_GET_MODE        0x04U
#define CMD_REBOOT          0x05U  /* reset via WDT — reinicia no bootloader (BOOTRST=0) */
#define CMD_KLINE_SET_BAUD  0x10U
#define CMD_KLINE_TX_BYTE   0x11U
#define CMD_KLINE_RX_BYTE   0x12U
#define CMD_KLINE_TX_FRAME  0x13U  /* envia frame inteiro atomicamente com deteccao de bus-idle */
#define CMD_KLINE_RX_BULK   0x14U  /* le multiplos bytes K-Line em uma unica transacao USB */
#define CMD_KLINE_WAIT_HIGH 0x15U  /* aguarda a linha K permanecer alta por uma janela estavel */
#define CMD_KLINE_GET_STATUS 0x16U /* classifica a linha K em baixo, alto ou comunicando */
#define CMD_KLINE_RX_BULK_RAW 0x17U /* como 0x14 mas inclui bytes com FE — para diagnostico de baud */
#define CMD_KLINE_KEEPALIVE  0x18U /* keepalive autonomo no firmware: envia TesterPresent periodicamente */
#define CMD_KLINE_SNIFF      0x19U /* modo sniffer cego: stream bruto RX sem handshake/protocolo */
#define CMD_DEBUG_TICK       0xF0U /* tick debug enviado a cada 1 s com g_ms_ticks p/ verificar Timer0 */
#define CMD_CAN_SET_BITRATE 0x20U
#define CMD_CAN_TX_STD      0x21U
#define CMD_CAN_RX_POLL     0x22U
#define CMD_CAN_GET_STATUS  0x23U
#define CMD_CAN_RX_AUTO     0x24U  /* push autonomo de frames RX CAN sem requisicao */
#define CMD_KLINE_SNIFF_AUTO 0x25U /* push autonomo de bytes K-Line crus */

#define FW_PROTO_VERSION    0x1CU

#define RSP_OK              0xA5U
#define RSP_ERR             0x7FU
#define RSP_NO_DATA         0xA6U

#define DEBUG_HEARTBEAT_ENABLE      0U
#define DEBUG_HEARTBEAT_INTERVAL_MS 500U

/*
 * Boot padrao:
 * - 0: protocolo enquadrado por comandos (necessario para o scanner PC)
 * - 1: interface sobe em passthrough bruto USB <-> K-Line (sem framing 0x5A)
 *
 * ATENCAO: em passthrough o firmware NAO processa comandos enquadrados, logo
 * o CMD_REBOOT deixa de funcionar e a entrada no bootloader exige reset fisico.
 */
#define YAMAHA_PASSTHROUGH_BOOT 0U

typedef enum {
    MODE_IDLE = 0x00U,
    MODE_KLINE = 0x01U,
    MODE_CAN = 0x02U,
    MODE_YAMAHA_PASSTHRU = 0x03U
} interface_mode_t;

static interface_mode_t active_mode = MODE_KLINE;
static uint16_t kline_baud = 10400U;
static uint16_t can_bitrate_kbps = 500U;

/* Watchdog USB: se sem comando por CAN_USB_TIMEOUT_MS, desliga CAN do bus. */
#define CAN_USB_TIMEOUT_MS 5000U
static volatile uint16_t last_cmd_ms = 0U;

/* --- K-Line firmware keepalive (CMD 0x18) --- */
static bool     kl_ka_active        = false;
static uint8_t  kl_ka_frame[12];
static uint8_t  kl_ka_frame_len     = 0U;
static uint16_t kl_ka_interval_ms   = 1500U;
static uint16_t kl_ka_next_fire_ms  = 0U;
static bool     kl_sniff_active     = false;

/* --- Tick de 1ms gerado pelo Timer0 CTC (16 MHz / 64 / 250 = 1 kHz) --- */
static volatile uint16_t g_ms_ticks = 0U;

ISR(TIMER0_COMP_vect)
{
    ++g_ms_ticks;
}

static bool usb_send_response(uint8_t command, const uint8_t *payload, uint8_t length)
{
    return usb_packet_send(command, payload, length);
}

static void process_yamaha_passthrough(void)
{
    uint8_t byte_value;
    uint8_t error_flags;
    uint8_t budget;

    usb_fifo_poll();

    /* PC -> K-Line */
    budget = 0U;
    while (budget < 8U && usb_fifo_can_read()) {
        byte_value = usb_fifo_read_u8();
        kline_send_byte(byte_value);
        ++budget;
    }

    /* K-Line -> PC (cego: inclui bytes mesmo com FE/DOR/UPE) */
    budget = 0U;
    while (budget < 16U && kline_poll_raw(&byte_value, &error_flags)) {
        (void)error_flags;
        if (!usb_fifo_can_write()) {
            break;
        }
        usb_fifo_write_u8(byte_value);
        ++budget;
    }
}

static bool set_mode(interface_mode_t mode)
{
    switch (mode) {
    case MODE_IDLE:
        kl_sniff_active = false;
        active_mode = MODE_IDLE;
        return true;

    case MODE_KLINE:
        kline_init();
        kline_set_baud(kline_baud);
        active_mode = MODE_KLINE;
        return true;

    case MODE_CAN:
        kl_ka_active = false;  /* desativa keepalive K-Line ao sair do modo KLINE */
        kl_sniff_active = false;
        if (!sja1000_init(can_bitrate_kbps)) {
            return false;
        }
        active_mode = MODE_CAN;
        return true;

    case MODE_YAMAHA_PASSTHRU:
        kl_ka_active = false;
        kl_sniff_active = false;
        kline_init();
        kline_set_baud(kline_baud);
        active_mode = MODE_YAMAHA_PASSTHRU;
        return true;

    default:
        return false;
    }
}

static void heartbeat_tick(void)
{
    board_led_toggle();
}

static void debug_heartbeat_tick(void)
{
#if DEBUG_HEARTBEAT_ENABLE
    static uint16_t heartbeat_seq = 0U;
    usb_fifo_debug_info_t dbg;
    usb_packet_debug_info_t pkt_dbg;

    if (!usb_fifo_is_mapped()) {
        return;
    }

    if (usb_fifo_write_available() < 21U) {
        return;
    }

    usb_fifo_get_debug_info(&dbg);
    usb_packet_get_debug_info(&pkt_dbg);

    usb_fifo_write_u8(0x55U);
    usb_fifo_write_u8((uint8_t)active_mode);
    usb_fifo_write_u8((uint8_t)(heartbeat_seq & 0xFFU));
    usb_fifo_write_u8((uint8_t)((heartbeat_seq >> 8) & 0xFFU));
    usb_fifo_write_u8(dbg.flags);
    usb_fifo_write_u8(dbg.rx_buffered);
    usb_fifo_write_u8(dbg.tx_buffered);
    usb_fifo_write_u8((uint8_t)(dbg.hw_rx_reads & 0xFFU));
    usb_fifo_write_u8((uint8_t)((dbg.hw_rx_reads >> 8) & 0xFFU));
    usb_fifo_write_u8((uint8_t)(dbg.hw_tx_writes & 0xFFU));
    usb_fifo_write_u8((uint8_t)((dbg.hw_tx_writes >> 8) & 0xFFU));
    usb_fifo_write_u8((uint8_t)(pkt_dbg.sync_seen & 0xFFU));
    usb_fifo_write_u8((uint8_t)((pkt_dbg.sync_seen >> 8) & 0xFFU));
    usb_fifo_write_u8((uint8_t)(pkt_dbg.frames_ok & 0xFFU));
    usb_fifo_write_u8((uint8_t)((pkt_dbg.frames_ok >> 8) & 0xFFU));
    usb_fifo_write_u8((uint8_t)(pkt_dbg.checksum_fail & 0xFFU));
    usb_fifo_write_u8((uint8_t)((pkt_dbg.checksum_fail >> 8) & 0xFFU));
    usb_fifo_write_u8(dbg.last_rx0);
    usb_fifo_write_u8(dbg.last_rx1);
    usb_fifo_write_u8(dbg.last_rx2);
    usb_fifo_write_u8(dbg.last_rx3);
    ++heartbeat_seq;
#endif
}

static void process_framed_packet(const usb_packet_t *packet)
{
    uint8_t response[USB_PACKET_MAX_PAYLOAD];
    can_frame_t frame;
    can_status_t can_status;
    kline_signal_status_t kline_status;
    uint8_t i;

    /* Atualiza watchdog: app ainda esta conectada. */
    cli(); last_cmd_ms = g_ms_ticks; sei();

    switch (packet->command) {
    case CMD_GET_INFO:
        response[0] = RSP_OK;
        response[1] = FW_PROTO_VERSION;
        response[2] = (uint8_t)active_mode;
        (void)usb_send_response(CMD_GET_INFO, response, 3U);
        break;

    case CMD_SET_MODE:
        if (packet->length != 1U || !set_mode((interface_mode_t)packet->payload[0])) {
            response[0] = RSP_ERR;
        } else {
            response[0] = RSP_OK;
        }
        (void)usb_send_response(CMD_SET_MODE, response, 1U);
        break;

    case CMD_GET_MODE:
        response[0] = RSP_OK;
        response[1] = (uint8_t)active_mode;
        (void)usb_send_response(CMD_GET_MODE, response, 2U);
        break;

    case CMD_KLINE_WAKEUP:
        if (active_mode != MODE_KLINE || packet->length != 0U) {
            response[0] = RSP_ERR;
        } else {
            kline_yamaha_wakeup();
            response[0] = RSP_OK;
        }
        (void)usb_send_response(CMD_KLINE_WAKEUP, response, 1U);
        break;

    case CMD_KLINE_SET_BAUD:
        if (active_mode != MODE_KLINE || packet->length != 2U) {
            response[0] = RSP_ERR;
        } else {
            kline_baud = (uint16_t)packet->payload[0] | ((uint16_t)packet->payload[1] << 8);
            kline_set_baud(kline_baud);
            response[0] = RSP_OK;
        }
        (void)usb_send_response(CMD_KLINE_SET_BAUD, response, 1U);
        break;

    case CMD_KLINE_TX_BYTE:
        if (active_mode != MODE_KLINE || packet->length != 1U) {
            response[0] = RSP_ERR;
        } else {
            kline_send_byte(packet->payload[0]);
            response[0] = RSP_OK;
        }
        (void)usb_send_response(CMD_KLINE_TX_BYTE, response, 1U);
        break;

    case CMD_KLINE_RX_BYTE:
        if (active_mode != MODE_KLINE || packet->length != 2U) {
            response[0] = RSP_ERR;
            response[1] = 0x00U;
        } else if (kline_read_byte(&response[1], (uint16_t)packet->payload[0] | ((uint16_t)packet->payload[1] << 8))) {
            response[0] = RSP_OK;
        } else {
            response[0] = RSP_ERR;
            response[1] = 0x00U;
        }
        (void)usb_send_response(CMD_KLINE_RX_BYTE, response, 2U);
        break;

    case CMD_KLINE_RX_BULK: {
        /*
         * payload[0..1] = first_timeout_ms (LE) — aguarda primeiro byte
         * payload[2..3] = inter_timeout_ms (LE) — timeout entre bytes
         * payload[4]    = max_bytes (1–28; 0 usa padrão 28)
         *
         * Resposta: RSP_OK | count | byte0 | byte1 | ... | byteN
         */
        uint16_t first_to = 30U;
        uint16_t inter_to = 3U;
        uint8_t  max_b    = 28U;
        if (packet->length >= 2U) {
            first_to = (uint16_t)packet->payload[0] | ((uint16_t)packet->payload[1] << 8);
        }
        if (packet->length >= 4U) {
            inter_to = (uint16_t)packet->payload[2] | ((uint16_t)packet->payload[3] << 8);
        }
        if (packet->length >= 5U && packet->payload[4] != 0U) {
            max_b = packet->payload[4];
            if (max_b > 28U) { max_b = 28U; }
        }
        if (active_mode != MODE_KLINE) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_KLINE_RX_BULK, response, 1U);
        } else {
            uint8_t n = kline_read_bulk(&response[2], max_b, first_to, inter_to);
            response[0] = RSP_OK;
            response[1] = n;
            (void)usb_send_response(CMD_KLINE_RX_BULK, response, (uint8_t)(2U + n));
        }
        break;
    }

    case CMD_KLINE_WAIT_HIGH: {
        uint16_t timeout_ms;
        uint16_t stable_ms;

        if (active_mode != MODE_KLINE || packet->length != 4U) {
            response[0] = RSP_ERR;
        } else {
            timeout_ms = (uint16_t)packet->payload[0] | ((uint16_t)packet->payload[1] << 8);
            stable_ms = (uint16_t)packet->payload[2] | ((uint16_t)packet->payload[3] << 8);
            response[0] = kline_wait_high(timeout_ms, stable_ms) ? RSP_OK : RSP_ERR;
        }
        (void)usb_send_response(CMD_KLINE_WAIT_HIGH, response, 1U);
        break;
    }

    case CMD_KLINE_GET_STATUS: {
        uint16_t observe_ms;

        if (active_mode != MODE_KLINE || packet->length != 2U) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_KLINE_GET_STATUS, response, 1U);
            break;
        }

        observe_ms = (uint16_t)packet->payload[0] | ((uint16_t)packet->payload[1] << 8);
        if (!kline_get_signal_status(observe_ms, &kline_status)) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_KLINE_GET_STATUS, response, 1U);
            break;
        }

        response[0] = RSP_OK;
        response[1] = (uint8_t)kline_status.state;
        response[2] = (uint8_t)(kline_status.high_ms & 0xFFU);
        response[3] = (uint8_t)((kline_status.high_ms >> 8) & 0xFFU);
        response[4] = (uint8_t)(kline_status.low_ms & 0xFFU);
        response[5] = (uint8_t)((kline_status.low_ms >> 8) & 0xFFU);
        response[6] = kline_status.edge_count;
        response[7] = kline_status.rx_byte_count;
        (void)usb_send_response(CMD_KLINE_GET_STATUS, response, 8U);
        break;
    }

    case CMD_KLINE_RX_BULK_RAW: {
        /*
         * Igual a CMD_KLINE_RX_BULK mas passa TODOS os bytes incluindo os com FE.
         * payload[0..1] = first_timeout_ms (LE)
         * payload[2..3] = inter_timeout_ms (LE)
         * payload[4]    = max_bytes (0 = usa padrao 26)
         *
         * Resposta: RSP_OK | total | err_count | byte0 | byte1 | ...
         */
        uint16_t first_to = 30U;
        uint16_t inter_to = 3U;
        uint8_t  max_b    = 26U;
        uint8_t  err_cnt  = 0U;
        if (packet->length >= 2U) {
            first_to = (uint16_t)packet->payload[0] | ((uint16_t)packet->payload[1] << 8);
        }
        if (packet->length >= 4U) {
            inter_to = (uint16_t)packet->payload[2] | ((uint16_t)packet->payload[3] << 8);
        }
        if (packet->length >= 5U && packet->payload[4] != 0U) {
            max_b = packet->payload[4];
            if (max_b > 26U) { max_b = 26U; }
        }
        if (active_mode != MODE_KLINE) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_KLINE_RX_BULK_RAW, response, 1U);
        } else {
            uint8_t n = kline_read_bulk_raw(&response[3], max_b, first_to, inter_to, &err_cnt);
            response[0] = RSP_OK;
            response[1] = n;
            response[2] = err_cnt;
            (void)usb_send_response(CMD_KLINE_RX_BULK_RAW, response, (uint8_t)(3U + n));
        }
        break;
    }

    case CMD_KLINE_TX_FRAME:
        /*
         * payload[0]      : idle_timeout_ms — tempo máximo (ms) para aguardar bus livre.
         *                   0 = transmite imediatamente sem esperar.
         * payload[1..N]   : bytes do frame K-Line a enviar atomicamente.
         *
         * Retorna RSP_ERR se o bus não ficou livre dentro do timeout.
         */
        if (active_mode != MODE_KLINE || packet->length < 2U) {
            response[0] = RSP_ERR;
        } else {
            uint16_t idle_tmo = (uint16_t)packet->payload[0];
            uint8_t  frame_len = (uint8_t)(packet->length - 1U);
            if (idle_tmo == 0U || kline_wait_bus_idle(idle_tmo)) {
                kline_send_frame(&packet->payload[1], frame_len);
                response[0] = RSP_OK;
            } else {
                response[0] = RSP_ERR; /* bus ocupado: timeout de idle esgotado */
            }
        }
        (void)usb_send_response(CMD_KLINE_TX_FRAME, response, 1U);
        break;

    case CMD_KLINE_KEEPALIVE: {
        /*
         * payload[0]      : 0 = disable, 1 = enable
         * if enable:
         *   payload[1..2]  : interval_ms (LE) — 0 usa padrao 1500 ms
         *   payload[3..N]  : bytes do frame TesterPresent a enviar
         */
        if (active_mode != MODE_KLINE || packet->length < 1U) {
            response[0] = RSP_ERR;
        } else if (packet->payload[0] == 0U) {
            kl_ka_active = false;
            response[0] = RSP_OK;
        } else {
            if (packet->length < 4U) {
                response[0] = RSP_ERR;
            } else {
                uint8_t fi;
                kl_ka_interval_ms = (uint16_t)packet->payload[1] | ((uint16_t)packet->payload[2] << 8);
                if (kl_ka_interval_ms == 0U) { kl_ka_interval_ms = 1500U; }
                kl_ka_frame_len = (uint8_t)(packet->length - 3U);
                if (kl_ka_frame_len > 12U) { kl_ka_frame_len = 12U; }
                for (fi = 0U; fi < kl_ka_frame_len; fi++) {
                    kl_ka_frame[fi] = packet->payload[3U + fi];
                }
                /* Arma o proximo disparo a partir de agora */
                cli();
                kl_ka_next_fire_ms = g_ms_ticks + kl_ka_interval_ms;
                sei();
                kl_ka_active = true;
                response[0] = RSP_OK;
            }
        }
        (void)usb_send_response(CMD_KLINE_KEEPALIVE, response, 1U);
        break;
    }

    case CMD_KLINE_SNIFF:
        /* payload[0]: 0=disable, 1=enable (somente em MODE_KLINE) */
        if (active_mode != MODE_KLINE || packet->length != 1U) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_KLINE_SNIFF, response, 1U);
            break;
        }

        if (packet->payload[0] == 0U) {
            kl_sniff_active = false;
            response[0] = RSP_OK;
            response[1] = 0U;
        } else {
            kl_ka_active = false;   /* sniff cego nao deve injetar TX */
            kl_sniff_active = true;
            response[0] = RSP_OK;
            response[1] = 1U;
        }
        (void)usb_send_response(CMD_KLINE_SNIFF, response, 2U);
        break;

    case CMD_CAN_SET_BITRATE:
        if (active_mode != MODE_CAN || packet->length != 2U) {
            response[0] = RSP_ERR;
        } else {
            uint16_t requested_bitrate = (uint16_t)packet->payload[0] | ((uint16_t)packet->payload[1] << 8);

            if (sja1000_init(requested_bitrate)) {
                can_bitrate_kbps = requested_bitrate;
                response[0] = RSP_OK;
            } else {
                response[0] = RSP_ERR;
            }
        }
        (void)usb_send_response(CMD_CAN_SET_BITRATE, response, 1U);
        break;

    case CMD_CAN_TX_STD:
        if (active_mode != MODE_CAN || packet->length < 3U) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_CAN_TX_STD, response, 1U);
            break;
        }

        frame.id = (uint32_t)packet->payload[0] | (((uint32_t)packet->payload[1] & 0x07U) << 8);
        frame.dlc = packet->payload[2];
        frame.extended = false;
        frame.rtr = false;
        if (frame.dlc > 8U || packet->length != (uint8_t)(3U + frame.dlc)) {
            response[0] = RSP_ERR;
        } else {
            for (i = 0U; i < frame.dlc; ++i) {
                frame.data[i] = packet->payload[3U + i];
            }
            /* Sai do LOM automaticamente ao transmitir. */
            sja1000_set_listen_only(false);
            response[0] = sja1000_write_frame(&frame) ? RSP_OK : RSP_ERR;
        }
        (void)usb_send_response(CMD_CAN_TX_STD, response, 1U);
        break;

    case CMD_CAN_RX_POLL:
        if (active_mode != MODE_CAN || packet->length != 0U) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_CAN_RX_POLL, response, 1U);
            break;
        }

        if (!sja1000_read_frame(&frame)) {
            response[0] = RSP_NO_DATA;
            (void)usb_send_response(CMD_CAN_RX_POLL, response, 1U);
            break;
        }

        response[0] = RSP_OK;
        response[1] = (uint8_t)(frame.id & 0xFFU);
        response[2] = (uint8_t)((frame.id >> 8) & 0x07U);
        response[3] = frame.dlc;
        for (i = 0U; i < frame.dlc; ++i) {
            response[4U + i] = frame.data[i];
        }
        (void)usb_send_response(CMD_CAN_RX_POLL, response, (uint8_t)(4U + frame.dlc));
        break;

    case CMD_CAN_GET_STATUS:
        if (active_mode != MODE_CAN || packet->length != 0U || !sja1000_get_status(&can_status)) {
            response[0] = RSP_ERR;
            (void)usb_send_response(CMD_CAN_GET_STATUS, response, 1U);
            break;
        }

        response[0] = RSP_OK;
        response[1] = can_status.status;
        response[2] = can_status.rx_error_counter;
        response[3] = can_status.tx_error_counter;
        response[4] = can_status.error_code_capture;
        response[5] = can_status.arbitration_lost_capture;
        response[6] = can_status.error_warning_limit;
        response[7] = can_status.rx_message_count;
        response[8] = (uint8_t)(can_bitrate_kbps & 0xFFU);
        response[9] = (uint8_t)((can_bitrate_kbps >> 8) & 0xFFU);
        (void)usb_send_response(CMD_CAN_GET_STATUS, response, 10U);
        break;

    case CMD_REBOOT:
        /* Responde RSP_OK, aguarda bytes saírem pelo FT245, depois dispara WDT */
        response[0] = RSP_OK;
        (void)usb_send_response(CMD_REBOOT, response, 1U);
        _delay_ms(10);  /* tempo para o byte sair pela USB */
        cli();
        wdt_enable(WDTO_15MS);
        for (;;) { }  /* aguarda WDT resetar — não retorna */
        break;

    default:
        response[0] = RSP_ERR;
        (void)usb_send_response(packet->command, response, 1U);
        break;
    }
}

static void firmware_init(void)
{
    cli();
    board_init();
    usb_fifo_init();
    kline_init();
    if (!sja1000_init(can_bitrate_kbps)) {
        can_bitrate_kbps = 500U;
        (void)sja1000_init(can_bitrate_kbps);
    }
    #if YAMAHA_PASSTHROUGH_BOOT
    (void)set_mode(MODE_YAMAHA_PASSTHRU);
    #else
    (void)set_mode(MODE_KLINE);
    #endif

    /* Timer0 CTC: 16 MHz / 64 / 250 = 1 kHz (tick de 1 ms) */
    OCR0  = 249U;  /* 16 MHz / 64 / 250 = 1 kHz */
    TCCR0 = (1U << WGM01) | (1U << CS01) | (1U << CS00);  /* CTC, prescaler 64 */
    TIMSK |= (1U << OCIE0);  /* habilita interrupcao por comparacao */

    sei();
}

static void process_usb_commands(void)
{
    usb_packet_t packet;

    usb_fifo_poll();

    if (usb_packet_receive(&packet)) {
        process_framed_packet(&packet);
    }
}

int main(void)
{
    /* Todos os temporizadores sao baseados em g_ms_ticks (Timer0 ISR, 1 kHz).
     * O loop roda em velocidade maxima; sem _delay_ms() para evitar distorcao. */
    uint16_t next_heartbeat_ms = 30000U;
    uint16_t next_debug_ms     = (uint16_t)DEBUG_HEARTBEAT_INTERVAL_MS;

    firmware_init();

    for (;;) {
        uint16_t now;
        cli(); now = g_ms_ticks; sei();  /* leitura atomica do uint16 */

        if (active_mode == MODE_YAMAHA_PASSTHRU) {
            process_yamaha_passthrough();
            continue;
        }

        process_usb_commands();

        /* Heartbeat LED (a cada ~30 s) */
        if ((int16_t)(now - next_heartbeat_ms) >= 0) {
            heartbeat_tick();
            next_heartbeat_ms = now + 30000U;
        }

        /* Debug heartbeat USB (a cada DEBUG_HEARTBEAT_INTERVAL_MS) */
        if ((int16_t)(now - next_debug_ms) >= 0) {
            debug_heartbeat_tick();
            next_debug_ms = now + (uint16_t)DEBUG_HEARTBEAT_INTERVAL_MS;
        }


        /* K-Line firmware keepalive: dispara a cada kl_ka_interval_ms reais */
        if (kl_ka_active && !kl_sniff_active && active_mode == MODE_KLINE && kl_ka_frame_len > 0U) {
            if ((int16_t)(now - kl_ka_next_fire_ms) >= 0) {
                kl_ka_next_fire_ms = now + kl_ka_interval_ms;
                if (kline_wait_bus_idle(80U)) {
                    kline_send_frame(kl_ka_frame, kl_ka_frame_len);
                }
            }
        }

        /* K-Line sniff cego: drena UART RX e envia bytes crus por push USB. */
        if (active_mode == MODE_KLINE && kl_sniff_active) {
            uint8_t raw_byte;
            uint8_t raw_flags;
            uint8_t sniff_resp[3];
            uint8_t burst_guard = 0U;

            while (burst_guard < 16U && kline_poll_raw(&raw_byte, &raw_flags)) {
                sniff_resp[0] = RSP_OK;
                sniff_resp[1] = raw_byte;
                sniff_resp[2] = raw_flags; /* bit0=FE, bit1=DOR, bit2=UPE */
                (void)usb_packet_send(CMD_KLINE_SNIFF_AUTO, sniff_resp, 3U);
                ++burst_guard;
            }
        }

        /* CAN RX autonomo: drena todos os frames disponiveis e envia via USB */
        if (active_mode == MODE_CAN) {
            uint16_t last_cmd;
            cli(); last_cmd = last_cmd_ms; sei();

            /* Watchdog: sem comando do app por CAN_USB_TIMEOUT_MS -> silencia bus */
            if ((int16_t)(now - last_cmd) > (int16_t)CAN_USB_TIMEOUT_MS) {
                sja1000_shutdown();
                active_mode = MODE_IDLE;
            } else {
                can_frame_t rxf;
                uint8_t can_resp[12];
                uint8_t ci;
                while (sja1000_read_frame(&rxf)) {
                    can_resp[0] = RSP_OK;
                    can_resp[1] = (uint8_t)(rxf.id & 0xFFU);
                    can_resp[2] = (uint8_t)((rxf.id >> 8) & 0x07U);
                    can_resp[3] = rxf.dlc;
                    for (ci = 0U; ci < rxf.dlc; ++ci) {
                        can_resp[4U + ci] = rxf.data[ci];
                    }
                    (void)usb_packet_send(CMD_CAN_RX_AUTO, can_resp, (uint8_t)(4U + rxf.dlc));
                }
            }
        }
    }
}