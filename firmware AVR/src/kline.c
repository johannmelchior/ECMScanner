#include <avr/io.h>
#include <util/delay.h>

#include "board.h"
#include "kline.h"

static uint16_t kline_current_baud = 10400U;
static bool kline_uart_active = false;

static uint16_t kline_bit_time_us(void)
{
    if (kline_current_baud == 0U) {
        return 96U;
    }

    return (uint16_t)((1000000UL + ((uint32_t)kline_current_baud / 2UL)) /
                      (uint32_t)kline_current_baud);
}

static uint32_t kline_abs_diff_u32(uint32_t left, uint32_t right)
{
    if (left >= right) {
        return left - right;
    }

    return right - left;
}

static uint16_t kline_compute_ubrr(uint16_t baud, uint8_t divisor, uint32_t *error)
{
    uint32_t ubrr_value;
    uint32_t actual_baud;
    uint32_t denominator;

    if (baud == 0U) {
        baud = 10400U;
    }

    denominator = (uint32_t)divisor * (uint32_t)baud;
    ubrr_value = (BOARD_CPU_FREQ_HZ + (denominator / 2UL)) / denominator;
    if (ubrr_value != 0UL) {
        ubrr_value -= 1UL;
    }
    if (ubrr_value > 0x0FFFUL) {
        ubrr_value = 0x0FFFUL;
    }

    actual_baud = BOARD_CPU_FREQ_HZ / ((uint32_t)divisor * (ubrr_value + 1UL));
    *error = kline_abs_diff_u32(actual_baud, (uint32_t)baud);
    return (uint16_t)ubrr_value;
}

static void kline_flush_rx(void)
{
    while ((UCSR0A & _BV(RXC0)) != 0U) {
        (void)UDR0;
    }
}

static void kline_prepare_rx_input(void)
{
    KLINE_RX_DDR &= (uint8_t)~_BV(KLINE_RX_PIN);
    KLINE_RX_PORT &= (uint8_t)~_BV(KLINE_RX_PIN);
}

static bool kline_line_is_high(void)
{
    kline_prepare_rx_input();
    return (KLINE_RX_PINR & _BV(KLINE_RX_PIN)) != 0U;
}

static void kline_enter_manual_mode(void)
{
    UCSR0B = 0U;
    kline_uart_active = false;

    KLINE_TX_DDR |= _BV(KLINE_TX_PIN);
    KLINE_TX_PORT |= _BV(KLINE_TX_PIN);
    kline_prepare_rx_input();
}

static void kline_configure_uart(void)
{
    uint32_t normal_error;
    uint32_t double_error;
    uint16_t normal_ubrr;
    uint16_t double_ubrr;
    uint16_t selected_ubrr;
    uint8_t ucsra_value = 0U;

    normal_ubrr = kline_compute_ubrr(kline_current_baud, 16U, &normal_error);
    double_ubrr = kline_compute_ubrr(kline_current_baud, 8U, &double_error);

    selected_ubrr = normal_ubrr;
    if (double_error < normal_error) {
        selected_ubrr = double_ubrr;
        ucsra_value = _BV(U2X0);
    }

    KLINE_TX_DDR |= _BV(KLINE_TX_PIN);
    KLINE_TX_PORT |= _BV(KLINE_TX_PIN);
    kline_prepare_rx_input();

    UCSR0B = 0U;
    UCSR0A = ucsra_value;
    UBRR0H = (uint8_t)((selected_ubrr >> 8) & 0x0FU);
    UBRR0L = (uint8_t)(selected_ubrr & 0x00FFU);
    UCSR0C = (uint8_t)(_BV(URSEL0) | _BV(UCSZ01) | _BV(UCSZ00));
    UCSR0B = (uint8_t)(_BV(RXEN0) | _BV(TXEN0));
    UCSR0A |= _BV(TXC0);

    kline_flush_rx();
    kline_uart_active = true;
}

static void kline_ensure_uart_mode(void)
{
    if (!kline_uart_active) {
        kline_configure_uart();
    }
}

void kline_init(void)
{
    kline_enter_manual_mode();
    kline_configure_uart();
}

void kline_set_baud(uint16_t baud)
{
    if (baud != 0U) {
        kline_current_baud = baud;
    }

    if (kline_uart_active) {
        kline_configure_uart();
    }
}

void kline_drive_low_ms(uint16_t duration_ms)
{
    kline_enter_manual_mode();
    KLINE_TX_PORT &= (uint8_t)~_BV(KLINE_TX_PIN);
    while (duration_ms-- != 0U) {
        _delay_ms(1);
    }
}

void kline_release_high_ms(uint16_t duration_ms)
{
    kline_enter_manual_mode();
    KLINE_TX_PORT |= _BV(KLINE_TX_PIN);
    while (duration_ms-- != 0U) {
        _delay_ms(1);
    }
}

void kline_send_byte(uint8_t value)
{
    kline_ensure_uart_mode();

    while ((UCSR0A & _BV(UDRE0)) == 0U) {
    }

    UCSR0A |= _BV(TXC0);
    UDR0 = value;

    while ((UCSR0A & _BV(TXC0)) == 0U) {
    }
}

bool kline_read_byte(uint8_t *value, uint16_t timeout_ms)
{
    uint32_t timeout_polls = ((uint32_t)timeout_ms * 100UL) + 1UL;

    if (value == 0) {
        return false;
    }

    kline_ensure_uart_mode();

    do {
        if ((UCSR0A & _BV(RXC0)) != 0U) {
            uint8_t status = UCSR0A;
            uint8_t data = UDR0;

            if ((status & (_BV(FE0) | _BV(DOR0) | _BV(UPE0))) != 0U) {
                return false;
            }

            *value = data;
            return true;
        }

        _delay_us(10U);
        --timeout_polls;
    } while (timeout_polls != 0UL);

    return false;
}

bool kline_poll_raw(uint8_t *value, uint8_t *error_flags)
{
    uint8_t status;
    uint8_t data;
    uint8_t flags = 0U;

    if (value == 0) {
        return false;
    }

    kline_ensure_uart_mode();

    if ((UCSR0A & _BV(RXC0)) == 0U) {
        return false;
    }

    status = UCSR0A;
    data = UDR0;

    if ((status & _BV(FE0)) != 0U) { flags |= 0x01U; }
    if ((status & _BV(DOR0)) != 0U) { flags |= 0x02U; }
    if ((status & _BV(UPE0)) != 0U) { flags |= 0x04U; }

    *value = data;
    if (error_flags != 0) {
        *error_flags = flags;
    }

    return true;
}

bool kline_wait_high(uint16_t timeout_ms, uint16_t stable_ms)
{
    uint16_t low_elapsed_ms = 0U;
    uint16_t high_elapsed_ms = 0U;
    bool saw_low = false;

    if (stable_ms == 0U) {
        stable_ms = 1U;
    }

    kline_enter_manual_mode();

    while (timeout_ms != 0U) {
        if (kline_line_is_high()) {
            low_elapsed_ms = 0U;

            if (saw_low) {
                high_elapsed_ms++;
                if (high_elapsed_ms >= stable_ms) {
                    kline_configure_uart();
                    return true;
                }
            }
        } else {
            high_elapsed_ms = 0U;
            if (low_elapsed_ms < stable_ms) {
                low_elapsed_ms++;
            }
            if (low_elapsed_ms >= stable_ms) {
                saw_low = true;
            }
        }

        _delay_ms(1U);
        --timeout_ms;
    }

    kline_configure_uart();
    return false;
}

bool kline_get_signal_status(uint16_t observe_ms, kline_signal_status_t *status)
{
    uint32_t total_ticks;
    uint32_t tick;
    uint16_t high_ticks = 0U;
    uint16_t low_ticks = 0U;
    bool last_high;

    if (status == 0) {
        return false;
    }

    if (observe_ms == 0U) {
        observe_ms = 50U;
    }

    status->state = KLINE_SIGNAL_LOW;
    status->high_ms = 0U;
    status->low_ms = 0U;
    status->edge_count = 0U;
    status->rx_byte_count = 0U;

    kline_ensure_uart_mode();
    kline_flush_rx();

    total_ticks = (uint32_t)observe_ms * 4UL;
    if (total_ticks == 0UL) {
        total_ticks = 1UL;
    }

    last_high = kline_line_is_high();

    for (tick = 0UL; tick < total_ticks; ++tick) {
        while ((UCSR0A & _BV(RXC0)) != 0U) {
            (void)UDR0;
            if (status->rx_byte_count != 0xFFU) {
                ++status->rx_byte_count;
            }
        }

        if (kline_line_is_high()) {
            if (high_ticks != 0xFFFFU) {
                ++high_ticks;
            }
            if (!last_high) {
                last_high = true;
                if (status->edge_count != 0xFFU) {
                    ++status->edge_count;
                }
            }
        } else {
            if (low_ticks != 0xFFFFU) {
                ++low_ticks;
            }
            if (last_high) {
                last_high = false;
                if (status->edge_count != 0xFFU) {
                    ++status->edge_count;
                }
            }
        }

        _delay_us(250U);
    }

    status->high_ms = (uint16_t)((high_ticks + 2U) / 4U);
    status->low_ms = (uint16_t)((low_ticks + 2U) / 4U);

    if (status->rx_byte_count != 0U || status->edge_count >= 2U) {
        status->state = KLINE_SIGNAL_COMMUNICATING;
    } else if ((uint32_t)high_ticks * 100UL >= total_ticks * 85UL) {
        status->state = KLINE_SIGNAL_HIGH;
    } else if ((uint32_t)low_ticks * 100UL >= total_ticks * 85UL) {
        status->state = KLINE_SIGNAL_LOW;
    } else {
        status->state = KLINE_SIGNAL_COMMUNICATING;
    }

    return true;
}

void kline_yamaha_wakeup(void)
{
    kline_release_high_ms(47U);
    kline_drive_low_ms(95U);
    kline_release_high_ms(95U);
    kline_drive_low_ms(95U);
    kline_release_high_ms(8U);
    kline_configure_uart();
}

bool kline_wait_bus_idle(uint16_t timeout_ms)
{
    /*
     * Aguarda o barramento K ficar em repouso (RX_PIN high) por pelo menos
     * 11 períodos de bit (= um byte completo + start + stop a 10400 baud ≈ 1.06 ms).
     * Retorna true se ficou livre, false se esgotou o timeout.
     */
    uint16_t bit_us = kline_bit_time_us();
    /* 11 bits × bit_time_us — satura em 65535µs no tipo uint16_t */
    uint16_t idle_needed_us = (uint16_t)(11U * (uint32_t)bit_us);
    uint16_t idle_elapsed_us = 0U;
    uint32_t timeout_us = (uint32_t)timeout_ms * 1000UL;

    while (timeout_us != 0UL) {
        if (kline_line_is_high()) {
            idle_elapsed_us++;
            if (idle_elapsed_us >= idle_needed_us) {
                return true; /* barramento livre por >= 11 bits */
            }
        } else {
            idle_elapsed_us = 0U; /* barramento ocupado — reinicia contagem */
        }
        _delay_us(1U);
        --timeout_us;
    }
    return false; /* timeout */
}

void kline_send_frame(const uint8_t *data, uint8_t len)
{
    uint8_t i;
    for (i = 0U; i < len; i++) {
        kline_send_byte(data[i]);
    }
}

uint8_t kline_read_bulk(uint8_t *buf, uint8_t max_bytes,
                        uint16_t first_timeout_ms, uint16_t inter_timeout_ms)
{
    uint8_t  count     = 0U;  /* valid (non-FE) bytes stored */
    uint8_t  total     = 0U;  /* total bytes received including FE */
    uint8_t  max_total;       /* hard cap to prevent infinite loop at wrong baud */
    uint32_t timeout_polls;
    uint16_t timeout;
    uint8_t  ucsr_status;

    if (max_bytes == 0U || max_bytes > 28U) {
        max_bytes = 28U;
    }
    /* Allow seeing up to 4 FE bytes per expected valid byte before giving up.
     * This bounds worst-case latency at wrong baud to max_bytes*4 byte-periods. */
    max_total = (max_bytes <= 63U) ? (uint8_t)(max_bytes * 4U) : 255U;
    timeout   = first_timeout_ms;

    kline_ensure_uart_mode();

    while (count < max_bytes && total < max_total) {
        timeout_polls = ((uint32_t)timeout * 100UL) + 1UL;

        /* Wait for next byte (valid or FE) within timeout window */
        while (timeout_polls != 0UL) {
            if ((UCSR0A & _BV(RXC0)) != 0U) {
                ucsr_status  = UCSR0A;           /* must read before UDR0 */
                uint8_t data = UDR0;
                total++;
                if ((ucsr_status & (_BV(FE0) | _BV(DOR0) | _BV(UPE0))) == 0U) {
                    buf[count++] = data;          /* valid byte */
                }
                /* FE byte: consumed but not stored; continue accumulating */
                timeout = inter_timeout_ms;       /* any byte activity = shorten gap */
                break;                            /* restart outer loop for next byte */
            }
            _delay_us(10U);
            --timeout_polls;
        }

        if (timeout_polls == 0UL) {
            break; /* genuine inter-byte silence — done */
        }
    }
    return count;
}

/* kline_read_bulk_raw: like kline_read_bulk but stores ALL bytes including those
 * with framing errors.  Returns total bytes received in buf[0..ret-1].
 * Byte count at wrong baud will be large but patterns reveal true baud.
 * response layout expected by CMD_KLINE_RX_BULK_RAW:
 *   payload[0] = RSP_OK
 *   payload[1] = total bytes (raw)
 *   payload[2] = error bytes count
 *   payload[3..] = raw bytes
 */
uint8_t kline_read_bulk_raw(uint8_t *buf, uint8_t max_bytes,
                             uint16_t first_timeout_ms, uint16_t inter_timeout_ms,
                             uint8_t *out_err_count)
{
    uint8_t  count     = 0U;
    uint8_t  err_count = 0U;
    uint32_t timeout_polls;
    uint16_t timeout;
    uint8_t  ucsr_status;

    if (max_bytes == 0U || max_bytes > 26U) { /* 26: leave room for RSP+count+err header */
        max_bytes = 26U;
    }
    timeout = first_timeout_ms;

    kline_ensure_uart_mode();

    while (count < max_bytes) {
        timeout_polls = ((uint32_t)timeout * 100UL) + 1UL;

        while (timeout_polls != 0UL) {
            if ((UCSR0A & _BV(RXC0)) != 0U) {
                ucsr_status  = UCSR0A;
                buf[count++] = UDR0;              /* store regardless of FE */
                if ((ucsr_status & (_BV(FE0) | _BV(DOR0) | _BV(UPE0))) != 0U) {
                    if (err_count != 0xFFU) {
                        err_count++;
                    }
                }
                timeout = inter_timeout_ms;
                break;
            }
            _delay_us(10U);
            --timeout_polls;
        }

        if (timeout_polls == 0UL) {
            break;
        }
    }

    if (out_err_count != 0) {
        *out_err_count = err_count;
    }
    return count;
}