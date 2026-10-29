/*
 * boot_main.c — Bootloader FT245 para ATmega162
 * =================================================
 * Grava na boot section (512 palavras = 1 KB) a partir do endereço 0x3C00.
 *
 * Protocolo: mesmo enquadramento do firmware principal.
 *   SYNC(0x5A) | LEN(1 byte) | CMD(1 byte) | PAYLOAD(0..31 bytes) | XOR_CHECKSUM
 *
 * Comandos:
 *   0x70 BL_GET_INFO    — retorna versão e tamanho de página
 *   0x71 BL_ERASE_APP   — apaga a seção de aplicação (todos os bytes → 0xFF)
 *   0x72 BL_WRITE_PAGE  — grava uma página de flash (256 bytes)
 *   0x73 BL_READ_PAGE   — lê uma página de flash
 *   0x74 BL_VERIFY_CRC  — verifica CRC16 de uma faixa da flash
 *   0x75 BL_JUMP_APP    — salta para a aplicação (vetor 0x0000)
 *
 * Respostas:
 *   RSP_OK  (0xA5) — operação bem-sucedida
 *   RSP_ERR (0x7F) — erro (endereço inválido, checksum ruim, etc.)
 *
 * Entrada no bootloader:
 *   - BOOTRST programado nos fuses → sempre inicia aqui após reset
 *   - Aguarda BL_GET_INFO por BL_TIMEOUT_MS. Se não chegar → salta para app
 *
 * ATmega162 flash: 16 KB = 64 páginas × 256 bytes
 *   Boot section 1024W (2KB): endereços de palavra 0x1C00..0x1FFF = bytes 0x3800..0x3FFF
 *   Aplicação: páginas 0x0000..0x37FF (56 páginas × 256 bytes)
 */

#include <avr/boot.h>
#include <avr/eeprom.h>
#include <avr/interrupt.h>
#include <avr/io.h>
#include <avr/pgmspace.h>
#include <avr/wdt.h>
#include <stdint.h>
#include <util/delay.h>

#include "boot_ft245.h"

/* ---- Constantes de protocolo ------------------------------------------- */
#define BL_SYNC          0x5AU
#define BL_MAX_PAYLOAD   31U

#define BL_CMD_GET_INFO   0x70U
#define BL_CMD_ERASE_APP  0x71U
#define BL_CMD_WRITE_PAGE 0x72U
#define BL_CMD_READ_PAGE  0x73U
#define BL_CMD_VERIFY_CRC 0x74U
#define BL_CMD_JUMP_APP   0x75U

#define BL_RSP_OK  0xA5U
#define BL_RSP_ERR 0x7FU

/* ---- Geometria da flash (ATmega162 @ 16 KB) ----------------------------- */
#define BL_FLASH_PAGE_BYTES  128U                   /* bytes por página SPM  */
#define BL_FLASH_PAGE_WORDS  (BL_FLASH_PAGE_BYTES / 2U)
#define BL_FLASH_TOTAL_PAGES 128U                   /* 16384 / 128           */
/* Boot section (2KB) começa na página 112 (byte addr 0x3800) */
#define BL_APP_MAX_PAGE      112U                   /* APP ocupa páginas 0–111 */

/* ---- Timeout de entrada ------------------------------------------------- */
/* Loop principal checa BL_TIMEOUT_LOOPS vezes antes de saltar para app     */
/* @ 16 MHz, cada iteração ≈ 10µs → 200000 × 10µs = 2 s                    */
#define BL_TIMEOUT_LOOPS 200000UL

/* ---- LED opcional (mesmo define do firmware principal) ------------------ */
#if BOARD_HAS_STATUS_LED
#define LED_INIT()    do { DDRB  |= _BV(PB0); } while (0)
#define LED_ON()      do { PORTB |= _BV(PB0); } while (0)
#define LED_OFF()     do { PORTB &= (uint8_t)~_BV(PB0); } while (0)
#define LED_TOGGLE()  do { PORTB ^= _BV(PB0); } while (0)
#else
#define LED_INIT()
#define LED_ON()
#define LED_OFF()
#define LED_TOGGLE()
#endif

/* ======================================================================== */
/* Protocolo                                                                 */
/* ======================================================================== */

static uint8_t bl_checksum(uint8_t len, uint8_t cmd, const uint8_t *payload)
{
    uint8_t cs = (uint8_t)(len ^ cmd);
    uint8_t i;
    for (i = 0U; i < len; i++) {
        cs ^= payload[i];
    }
    return cs;
}

/* Envia um pacote de resposta completo */
static void bl_send(uint8_t cmd, const uint8_t *payload, uint8_t len)
{
    uint8_t i;
    bl_ft245_write(BL_SYNC);
    bl_ft245_write(len);
    bl_ft245_write(cmd);
    for (i = 0U; i < len; i++) {
        bl_ft245_write(payload[i]);
    }
    bl_ft245_write(bl_checksum(len, cmd, payload));
}

static void bl_send_ok(uint8_t cmd)
{
    uint8_t payload = BL_RSP_OK;
    bl_send(cmd, &payload, 1U);
}

static void bl_send_err(uint8_t cmd)
{
    uint8_t payload = BL_RSP_ERR;
    bl_send(cmd, &payload, 1U);
}

/* ======================================================================== */
/* SPM helpers                                                               */
/* ======================================================================== */

/* Apaga uma página (byte_addr deve ser alinhado a 256 bytes) */
static void bl_page_erase(uint32_t byte_addr)
{
    boot_page_erase(byte_addr);
    boot_spm_busy_wait();
}

/* Preenche o buffer temporário SPM (word a word) e depois grava */
static void bl_page_write(uint32_t byte_addr, const uint8_t *data)
{
    uint16_t i;
    uint16_t word;

    /* Apaga a página antes de gravar */
    bl_page_erase(byte_addr);

    /* Preenche buffer temporário word a word */
    for (i = 0U; i < BL_FLASH_PAGE_BYTES; i += 2U) {
        word = (uint16_t)data[i] | ((uint16_t)data[i + 1U] << 8);
        boot_page_fill(byte_addr + i, word);
    }

    /* Grava página */
    boot_page_write(byte_addr);
    boot_spm_busy_wait();

    /* Re-habilita RWW para leitura normal da app */
    boot_rww_enable();
}

/* CRC16-CCITT (poly 0x1021, init 0xFFFF) sobre uma faixa da flash */
static uint16_t bl_crc16(uint32_t byte_addr, uint16_t length)
{
    uint16_t crc = 0xFFFFU;
    uint16_t i;
    uint8_t b;

    for (i = 0U; i < length; i++) {
        b = pgm_read_byte(byte_addr + i);
        crc ^= (uint16_t)((uint16_t)b << 8);
        uint8_t bit;
        for (bit = 0U; bit < 8U; bit++) {
            if ((crc & 0x8000U) != 0U) {
                crc = (uint16_t)((crc << 1) ^ 0x1021U);
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

/* ======================================================================== */
/* Recepção de pacote                                                        */
/* ======================================================================== */

typedef struct {
    uint8_t cmd;
    uint8_t len;
    uint8_t payload[BL_MAX_PAYLOAD];
} bl_packet_t;

typedef enum {
    BL_RECV_SYNC = 0,
    BL_RECV_LEN,
    BL_RECV_CMD,
    BL_RECV_PAYLOAD,
    BL_RECV_CHECKSUM
} bl_recv_state_t;

static uint8_t s_recv_cs;
static uint8_t s_recv_idx;
static bl_recv_state_t s_recv_state = BL_RECV_SYNC;
static bl_packet_t s_pkt;

/* Retorna 1 se um pacote completo e válido foi recebido */
static uint8_t bl_recv_poll(void)
{
    if (!bl_ft245_can_read()) {
        return 0U;
    }
    uint8_t b = bl_ft245_read();

    switch (s_recv_state) {
    case BL_RECV_SYNC:
        if (b == BL_SYNC) {
            s_recv_state = BL_RECV_LEN;
        }
        break;
    case BL_RECV_LEN:
        if (b > BL_MAX_PAYLOAD) {
            s_recv_state = BL_RECV_SYNC;
            break;
        }
        s_pkt.len   = b;
        s_recv_cs   = b;
        s_recv_idx  = 0U;
        s_recv_state = BL_RECV_CMD;
        break;
    case BL_RECV_CMD:
        s_pkt.cmd  = b;
        s_recv_cs ^= b;
        s_recv_state = (s_pkt.len == 0U) ? BL_RECV_CHECKSUM : BL_RECV_PAYLOAD;
        break;
    case BL_RECV_PAYLOAD:
        s_pkt.payload[s_recv_idx++] = b;
        s_recv_cs ^= b;
        if (s_recv_idx >= s_pkt.len) {
            s_recv_state = BL_RECV_CHECKSUM;
        }
        break;
    case BL_RECV_CHECKSUM:
        s_recv_state = BL_RECV_SYNC;
        if (b == s_recv_cs) {
            return 1U; /* pacote válido */
        }
        /* checksum ruim — descarta */
        break;
    }
    return 0U;
}

/* ======================================================================== */
/* Handlers de comando                                                       */
/* ======================================================================== */

static void handle_get_info(void)
{
    /*
     * Resposta: RSP_OK | BL_VERSION | PAGE_SIZE_L | PAGE_SIZE_H |
     *           APP_PAGES | BOOT_START_L | BOOT_START_H
     */
    uint8_t rsp[7];
    rsp[0] = BL_RSP_OK;
    rsp[1] = 0x01U;                                  /* versão 1              */
    rsp[2] = (uint8_t)(BL_FLASH_PAGE_BYTES & 0xFFU); /* página = 256          */
    rsp[3] = (uint8_t)(BL_FLASH_PAGE_BYTES >> 8);
    rsp[4] = BL_APP_MAX_PAGE;                         /* 112 páginas de app    */
    rsp[5] = (uint8_t)(0x3800U & 0xFFU);             /* byte addr boot start  */
    rsp[6] = (uint8_t)(0x3800U >> 8);
    bl_send(s_pkt.cmd, rsp, 7U);
}

static void handle_erase_app(void)
{
    uint8_t page;
    for (page = 0U; page < BL_APP_MAX_PAGE; page++) {
        bl_page_erase((uint32_t)page * BL_FLASH_PAGE_BYTES);
        LED_TOGGLE();
    }
    bl_send_ok(s_pkt.cmd);
}

static void handle_write_page(void)
{
    /*
    * payload[0]       : número da página (0–111)
    * payload[1..128]  : 128 bytes de dados
    * Payload total = 129 bytes → não cabe no MAX_PAYLOAD de 31!
     *
     * Solução: o HOST fragmenta em sub-pacotes de 64 bytes pelo comando
     * BL_CMD_WRITE_PAGE usando o campo de controle:
     *   payload[0] = número da página
    *   payload[1] = offset do chunk (0..127)
     *   payload[2] = tamanho do chunk (1–30)  → máx 29 bytes de dados por pacote
     *   payload[3..] = dados
     *
    * Na última chegada (offset+size == 128), executa a gravação SPM.
     */
    static uint8_t page_buf[BL_FLASH_PAGE_BYTES];
    static uint8_t last_page = 0xFFU;

    if (s_pkt.len < 4U) {
        bl_send_err(s_pkt.cmd);
        return;
    }

    uint8_t  page_num    = s_pkt.payload[0];
    uint8_t  chunk_off   = s_pkt.payload[1];
    uint8_t  chunk_size  = s_pkt.payload[2];

    /* Valida página da aplicação */
    if (page_num >= BL_APP_MAX_PAGE) {
        bl_send_err(s_pkt.cmd);
        return;
    }

    /* Valida limites do chunk */
    if ((uint16_t)chunk_off + chunk_size > BL_FLASH_PAGE_BYTES) {
        bl_send_err(s_pkt.cmd);
        return;
    }

    /* Se mudou de página, limpa buffer */
    if (page_num != last_page) {
        uint16_t i;
        for (i = 0U; i < BL_FLASH_PAGE_BYTES; i++) {
            page_buf[i] = 0xFFU;
        }
        last_page = page_num;
    }

    /* Copia chunk no buffer */
    uint8_t i;
    for (i = 0U; i < chunk_size; i++) {
        page_buf[chunk_off + i] = s_pkt.payload[3U + i];
    }

    /* Se buffer completo → grava */
    if ((uint16_t)chunk_off + chunk_size == BL_FLASH_PAGE_BYTES) {
        uint32_t byte_addr = (uint32_t)page_num * BL_FLASH_PAGE_BYTES;
        bl_page_write(byte_addr, page_buf);
        last_page = 0xFFU;
        LED_TOGGLE();
        bl_send_ok(s_pkt.cmd);
    } else {
        /* Chunk parcial aceito — confirma mas não grava ainda */
        bl_send_ok(s_pkt.cmd);
    }
}

static void handle_read_page(void)
{
    /*
     * payload[0] = número da página
     * payload[1] = offset dentro da página (0–255)
     * payload[2] = tamanho a ler (1–28, para caber em BL_MAX_PAYLOAD - 3)
     */
    if (s_pkt.len < 3U) {
        bl_send_err(s_pkt.cmd);
        return;
    }

    uint8_t page_num = s_pkt.payload[0];
    uint8_t off      = s_pkt.payload[1];
    uint8_t size     = s_pkt.payload[2];

    if (page_num >= BL_FLASH_TOTAL_PAGES || (uint16_t)off + size > BL_FLASH_PAGE_BYTES || size > 28U) {
        bl_send_err(s_pkt.cmd);
        return;
    }

    uint32_t byte_addr = (uint32_t)page_num * BL_FLASH_PAGE_BYTES + off;
    uint8_t rsp[31U];
    rsp[0] = BL_RSP_OK;
    rsp[1] = size;
    uint8_t i;
    for (i = 0U; i < size; i++) {
        rsp[2U + i] = pgm_read_byte(byte_addr + i);
    }
    bl_send(s_pkt.cmd, rsp, (uint8_t)(2U + size));
}

static void handle_verify_crc(void)
{
    /*
     * payload[0..1] = byte start address (LE)
     * payload[2..3] = length (LE)
     * payload[4..5] = expected CRC16 (LE)
     */
    if (s_pkt.len < 6U) {
        bl_send_err(s_pkt.cmd);
        return;
    }

    uint32_t addr   = (uint32_t)s_pkt.payload[0] | ((uint32_t)s_pkt.payload[1] << 8);
    uint16_t length = (uint16_t)s_pkt.payload[2]  | ((uint16_t)s_pkt.payload[3] << 8);
    uint16_t expect = (uint16_t)s_pkt.payload[4]  | ((uint16_t)s_pkt.payload[5] << 8);
    uint16_t actual = bl_crc16(addr, length);

    uint8_t rsp[5];
    rsp[0] = (actual == expect) ? BL_RSP_OK : BL_RSP_ERR;
    rsp[1] = (uint8_t)(actual & 0xFFU);
    rsp[2] = (uint8_t)(actual >> 8);
    rsp[3] = (uint8_t)(expect & 0xFFU);
    rsp[4] = (uint8_t)(expect >> 8);
    bl_send(s_pkt.cmd, rsp, 5U);
}

static void handle_jump_app(void)
{
    bl_send_ok(s_pkt.cmd);
    _delay_ms(10);  /* tempo para o byte sair pelo FT245 */

    /* Re-habilita RWW e desabilita watchdog antes de saltar */
    boot_rww_enable();
    wdt_disable();

    /* Salta para o vetor de reset da aplicação (endereço 0x0000) */
    void (*app_start)(void) = (void (*)(void))0x0000;
    app_start();
}

/* ======================================================================== */
/* main                                                                      */
/* ======================================================================== */

int main(void)
{
    /*
     * Desabilita imediatamente o watchdog — pode ter sido ativado pela app
     * para entrar no bootloader via reset controlado.
     */
    MCUCSR = 0U;
    wdt_disable();

    /* Inicializa FT245 */
    bl_ft245_init();
    LED_INIT();
    LED_ON();

    /*
     * Janela de entrada: aguarda BL_GET_INFO por ~2 s.
     * Se não chegar, salta direto para a aplicação.
     */
    uint32_t timeout = BL_TIMEOUT_LOOPS;
    uint8_t got_first_cmd = 0U;

    while (timeout != 0UL) {
        if (bl_recv_poll()) {
            if (s_pkt.cmd == BL_CMD_GET_INFO) {
                got_first_cmd = 1U;
                handle_get_info();
                break;
            }
        }
        --timeout;
    }

    if (!got_first_cmd) {
        /* Timeout — nenhum host conectado, salta para aplicação */
        LED_OFF();
        handle_jump_app();
        /* Não retorna */
        for (;;) { }
    }

    /* ---- Loop principal do bootloader ---- */
    LED_OFF();
    for (;;) {
        /* Pisca LED enquanto aguarda (heartbeat visual) */
        static uint16_t blink_count = 0U;
        blink_count++;
        if (blink_count == 0U) {
            LED_TOGGLE();
        }

        if (!bl_recv_poll()) {
            continue;
        }

        switch (s_pkt.cmd) {
        case BL_CMD_GET_INFO:
            handle_get_info();
            break;
        case BL_CMD_ERASE_APP:
            handle_erase_app();
            break;
        case BL_CMD_WRITE_PAGE:
            handle_write_page();
            break;
        case BL_CMD_READ_PAGE:
            handle_read_page();
            break;
        case BL_CMD_VERIFY_CRC:
            handle_verify_crc();
            break;
        case BL_CMD_JUMP_APP:
            handle_jump_app();
            /* não retorna */
            break;
        default:
            bl_send_err(s_pkt.cmd);
            break;
        }
    }
}
