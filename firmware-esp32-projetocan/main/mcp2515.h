#pragma once
#include <stdint.h>
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_err.h"

// MCP2515 Register Definitions
#define MCP_CNF1 0x2A
#define MCP_CNF2 0x29
#define MCP_CNF3 0x28
#define MCP_CANCTRL 0x0F
#define MCP_CANSTAT 0x0E
#define MCP_CANINTF 0x2C
#define MCP_INTF_RX0IF 0x01
#define MCP_INTF_RX1IF 0x02
#define MCP_TXB0CTRL 0x30
#define MCP_TXB0SIDH 0x31

// CANCTRL Modes
#define MODE_NORMAL     0x00
#define MODE_SLEEP      0x20
#define MODE_LOOPBACK   0x40
#define MODE_LISTENONLY 0x60
#define MODE_CONFIG     0x80

typedef struct {
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
    bool ext;
    bool rtr;
} can_frame_t;

/**
 * @brief Initialize the MCP2515 driver
 * 
 * @param host SPI host device (e.g. SPI2_HOST)
 * @param cs_pin GPIO pin for Chip Select
 * @param int_pin GPIO pin for Interrupt (Active Low). Pass -1 to disable.
 * @return esp_err_t ESP_OK on success
 */
esp_err_t mcp2515_init(spi_host_device_t host, int cs_pin, int int_pin);

/**
 * @brief Send a CAN frame
 * 
 * @param frame Pointer to the frame to send
 * @return esp_err_t ESP_OK on success
 */
esp_err_t mcp2515_send(const can_frame_t *frame);

typedef enum {
    CAN_1000KBPS = 1000,
    CAN_500KBPS = 500,
    CAN_250KBPS = 250,
    CAN_125KBPS = 125,
    CAN_100KBPS = 100,
    CAN_50KBPS = 50,
    CAN_20KBPS = 20,
    CAN_10KBPS = 10
} can_speed_t;

/**
 * @brief Configure CAN bit timing for 16MHz Crystal
 * 
 * @param speed CAN Bus Speed
 * @return esp_err_t 
 */
esp_err_t mcp2515_set_bitrate(can_speed_t speed);

/**
 * @brief Set the operation mode of the MCP2515
 * 
 * @param mode One of MODE_NORMAL, MODE_LOOPBACK, MODE_CONFIG, etc.
 * @return esp_err_t 
 */
esp_err_t mcp2515_set_mode(uint8_t mode);

/**
 * @brief Check if a message is available
 * 
 * @return esp_err_t ESP_OK if message available, ESP_FAIL otherwise
 */
esp_err_t mcp2515_check_message(void);

/**
 * @brief Receive a CAN message
 * 
 * @param frame Pointer to can_frame_t to store the message
 * @return esp_err_t SEP_OK on success
 */
esp_err_t mcp2515_receive(can_frame_t *frame);
