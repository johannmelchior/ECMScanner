#ifndef KLINE_H
#define KLINE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    KLINE_SIGNAL_LOW = 0x00U,
    KLINE_SIGNAL_HIGH = 0x01U,
    KLINE_SIGNAL_COMMUNICATING = 0x02U,
} kline_signal_state_t;

typedef struct {
    kline_signal_state_t state;
    uint16_t high_ms;
    uint16_t low_ms;
    uint8_t edge_count;
    uint8_t rx_byte_count;
} kline_signal_status_t;

void kline_init(void);
void kline_set_baud(uint16_t baud);
void kline_drive_low_ms(uint16_t duration_ms);
void kline_release_high_ms(uint16_t duration_ms);
void kline_send_byte(uint8_t value);
bool kline_read_byte(uint8_t *value, uint16_t timeout_ms);

/* Poll nao-bloqueante do UART K-Line bruto (inclui bytes com erro). */
bool kline_poll_raw(uint8_t *value, uint8_t *error_flags);

/* Aguarda a K-Line ficar baixa e depois subir, permanecendo alta por stable_ms. */
bool kline_wait_high(uint16_t timeout_ms, uint16_t stable_ms);

/* Classifica a linha K em LOW, HIGH ou COMMUNICATING ao longo de observe_ms. */
bool kline_get_signal_status(uint16_t observe_ms, kline_signal_status_t *status);

/* Aguarda o barramento ficar ocioso por >= 11 bit-periods antes de transmitir. */
bool kline_wait_bus_idle(uint16_t timeout_ms);

/* Envia um frame inteiro atomicamente (sem pausa USB entre bytes). */
void kline_send_frame(const uint8_t *data, uint8_t len);

/*
 * Lê até max_bytes bytes do barramento K-Line de forma contínua.
 * Espera até first_timeout_ms pelo primeiro byte, depois usa inter_timeout_ms
 * entre bytes consecutivos. Retorna a quantidade de bytes lidos.
 * Máximo útil: 28 bytes (cabe em um pacote USB com RSP_OK + count header).
 * Bytes com FE/DOR são descartados (não contados). Termina em silêncio real.
 */
uint8_t kline_read_bulk(uint8_t *buf, uint8_t max_bytes,
                        uint16_t first_timeout_ms, uint16_t inter_timeout_ms);

/*
 * Como kline_read_bulk mas armazena TODOS os bytes incluindo os com FE.
 * out_err_count recebe a contagem de bytes com erro de enquadramento.
 * Útil apenas para diagnóstico de baud rate — máx 26 bytes (26+3=29 <= 32).
 */
uint8_t kline_read_bulk_raw(uint8_t *buf, uint8_t max_bytes,
                             uint16_t first_timeout_ms, uint16_t inter_timeout_ms,
                             uint8_t *out_err_count);

/* Sequencia especifica observada nos logs Yamaha. */
void kline_yamaha_wakeup(void);

#endif