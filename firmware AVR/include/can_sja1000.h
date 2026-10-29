#ifndef CAN_SJA1000_H
#define CAN_SJA1000_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
    bool extended;
    bool rtr;
} can_frame_t;

typedef struct {
    uint8_t status;
    uint8_t rx_error_counter;
    uint8_t tx_error_counter;
    uint8_t error_code_capture;
    uint8_t arbitration_lost_capture;
    uint8_t error_warning_limit;
    uint8_t rx_message_count;
} can_status_t;

bool sja1000_init(uint16_t bitrate_kbps);
bool sja1000_read_frame(can_frame_t *frame);
bool sja1000_write_frame(const can_frame_t *frame);
bool sja1000_get_status(can_status_t *status);
void sja1000_set_listen_only(bool enable);
void sja1000_shutdown(void);

#endif