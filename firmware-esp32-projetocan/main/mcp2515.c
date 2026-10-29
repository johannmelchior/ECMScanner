#include "mcp2515.h"
#include "esp_log.h"
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "MCP2515";
static spi_device_handle_t spi_handle;
static int interrupt_pin = -1;

#define MCP_INSTRUCTION_RESET       0xC0
#define MCP_INSTRUCTION_READ        0x03
#define MCP_INSTRUCTION_WRITE       0x02
#define MCP_INSTRUCTION_BITMOD      0x05

#define MCP_CANINTE                 0x2B
#define MCP_RX0IE                   0x01
#define MCP_RX1IE                   0x02

esp_err_t mcp2515_read_reg(uint8_t reg, uint8_t *value) {
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    uint8_t tx_data[2] = {MCP_INSTRUCTION_READ, reg};
    uint8_t rx_data[2] = {0}; // Response comes in the byte after the address

    // Full-duplex: Send 3 bytes (CMD, REG, DUMMY), Receive 3 bytes (trash, trash, DATA)
    // Actually the read command is:
    // MOSI: [0x03] [ADDR] [0x00]
    // MISO: [xxxx] [xxxx] [DATA]
    
    // Using spi_device_transmit with tx_buffer and rx_buffer
    // We need a transaction length of 3 bytes (24 bits)
    
    // The SPI driver handles full duplex.
    // If we want to read 1 byte, we send 2 command bytes + 1 dummy byte.
    // The data returned corresponds to the dummy byte clock cycles.
    
    uint8_t tx_buf[3] = {MCP_INSTRUCTION_READ, reg, 0x00};
    uint8_t rx_buf[3] = {0, 0, 0};

    t.length = 24; 
    t.tx_buffer = tx_buf;
    t.rx_buffer = rx_buf;
    
    esp_err_t ret = spi_device_transmit(spi_handle, &t);
    if (ret == ESP_OK) {
        *value = rx_buf[2];
    }
    return ret;
}

esp_err_t mcp2515_modify_reg(uint8_t reg, uint8_t mask, uint8_t data) {
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    uint8_t tx_data[4] = {MCP_INSTRUCTION_BITMOD, reg, mask, data};
    
    t.length = 32;
    t.tx_buffer = tx_data;
    
    return spi_device_transmit(spi_handle, &t);
}

esp_err_t mcp2515_write_reg(uint8_t reg, uint8_t value) {
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    uint8_t tx_data[3] = {MCP_INSTRUCTION_WRITE, reg, value};
    
    t.length = 24; // 3 bytes * 8 bits
    t.tx_buffer = tx_data;
    
    return spi_device_transmit(spi_handle, &t);
}

esp_err_t mcp2515_init(spi_host_device_t host, int cs_pin, int int_pin) {
    if (spi_handle != NULL) {
        ESP_LOGW(TAG, "MCP2515 already initialized");
        return ESP_OK;
    }

    interrupt_pin = int_pin;
    if (interrupt_pin >= 0) {
        // Initialize INT pin
        gpio_config_t io_conf = {};
        io_conf.intr_type = GPIO_INTR_DISABLE;
        io_conf.mode = GPIO_MODE_INPUT;
        io_conf.pin_bit_mask = (1ULL << interrupt_pin);
        io_conf.pull_down_en = 0;
        io_conf.pull_up_en = 1; // Pull-up for active low
        gpio_config(&io_conf);
    }
    
    esp_err_t ret;
    
    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 10 * 1000 * 1000,           // Clock out at 10 MHz
        .mode = 0,                                  // SPI mode 0
        .spics_io_num = cs_pin,                     // CS pin
        .queue_size = 7,                            // Transaction queue size
    };
    
    ret = spi_bus_add_device(host, &devcfg, &spi_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add device to SPI bus");
        return ret;
    }

    // Send Reset Command
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    uint8_t reset_cmd = MCP_INSTRUCTION_RESET;
    t.length = 8;
    t.tx_buffer = &reset_cmd;
    
    ret = spi_device_transmit(spi_handle, &t);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to send reset command");
        return ret;
    }
    
    // Check if device is alive / wait for reset
    vTaskDelay(pdMS_TO_TICKS(10));

    // Initialize Masks and Filters to 0 to accept everything 
    // when using RX_STDEXT (Enable Filters) mode.
    // This mimics the behavior of standard libraries which might leave them cleared 
    // or rely on specific initialization.
    // Address 0x00 to 0x0B: RXF0SIDH to RXF2EID0
    // Address 0x10 to 0x1B: RXF3SIDH to RXF5EID0
    // Address 0x20 to 0x27: RXM0SIDH to RXM1EID0
    
    // We are in CONFIG mode after Reset, so we can write to these.
    const uint8_t registers_to_zero[] = {
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, // Filters 0-2
        0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, // Filters 3-5
        0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27                          // Masks 0-1
    };
    
    for (int i = 0; i < sizeof(registers_to_zero); i++) {
        ESP_ERROR_CHECK(mcp2515_write_reg(registers_to_zero[i], 0x00));
    }

    // Initialize RX Buffers
    // Use RX_STDEXT (0x00) -> Receive Valid Messages that meet Filter criteria.
    // Since Masks are 0, ALL messages meet criteria.
    // Enable Rollover (BUKT=1) -> 0x04
    ESP_ERROR_CHECK(mcp2515_write_reg(0x60, 0x04)); // RXB0CTRL (Addr 0x60)
    ESP_ERROR_CHECK(mcp2515_write_reg(0x70, 0x00)); // RXB1CTRL (Addr 0x70)

    // Enable Interrupts for RX0 and RX1
    // If we don't do this, the INT pin will never go Low.
    ESP_ERROR_CHECK(mcp2515_write_reg(MCP_CANINTE, MCP_RX0IE | MCP_RX1IE));
    
    ESP_LOGI(TAG, "MCP2515 initialized successfully (Filters Enabled / Cleared)");
    return ESP_OK;
}

esp_err_t mcp2515_set_bitrate(can_speed_t speed) {
    uint8_t cnf1, cnf2, cnf3;

    switch (speed) {
        case CAN_1000KBPS:
            cnf1 = 0x00;
            cnf2 = 0x90;
            cnf3 = 0x02;
            break;
        case CAN_500KBPS:
            cnf1 = 0x00;
            // cnf2 = 0xF1: BTLMODE=1, SAM=1 (3x sampling), PHSEG1=6, PRSEG=1
            // This is more robust against noise compared to 0xB1 (SAM=0)
            cnf2 = 0xF1;
            cnf3 = 0x05;
            break;
        case CAN_250KBPS:
            cnf1 = 0x01;
            cnf2 = 0xB1;
            cnf3 = 0x05;
            break;
        case CAN_125KBPS:
            cnf1 = 0x03;
            cnf2 = 0xB1;
            cnf3 = 0x05;
            break;
        case CAN_100KBPS:
            cnf1 = 0x04;
            cnf2 = 0xB1;
            cnf3 = 0x05;
            break;
        case CAN_50KBPS:
            cnf1 = 0x09;
            cnf2 = 0xB1;
            cnf3 = 0x05;
            break;
        case CAN_20KBPS:
            cnf1 = 0x18;
            cnf2 = 0xB1;
            cnf3 = 0x05;
            break;
        case CAN_10KBPS:
            cnf1 = 0x31;
            cnf2 = 0xB1;
            cnf3 = 0x05;
            break;
        default:
            ESP_LOGE(TAG, "Invalid bitrate requested: %d", speed);
            return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Setting bitrate: %d kbps (CNF: %02X %02X %02X)", speed, cnf1, cnf2, cnf3);
    
    // Ensure we are in Configuration Mode before changing bitrate
    // Note: The caller should ideally handle mode switching, but we can enforce it here safely.
    // However, if we just modify registers, we need Config Mode.
    // Let's assume the caller will put it in Config mode, or we do it here.
    // To be safe, let's just write the registers (calls spi_transmit).
    
    ESP_ERROR_CHECK(mcp2515_write_reg(MCP_CNF1, cnf1));
    ESP_ERROR_CHECK(mcp2515_write_reg(MCP_CNF2, cnf2));
    ESP_ERROR_CHECK(mcp2515_write_reg(MCP_CNF3, cnf3));
    
    return ESP_OK;
}

esp_err_t mcp2515_set_mode(uint8_t mode) {
    // Mask for mode bits is 0xE0
    // But direct write to CANCTRL is fine too
    uint8_t current_mode = mode & 0xE0;
    
    esp_err_t ret = mcp2515_write_reg(MCP_CANCTRL, current_mode);
    if(ret == ESP_OK) {
         ESP_LOGI(TAG, "Mode set to 0x%02X", current_mode);
    }
    return ret;
}

esp_err_t mcp2515_check_message(void) {
    // If interrupt pin is configured, check it first.
    // INT is Active Low. If High (1), no message is pending.
    if (interrupt_pin >= 0) {
        if (gpio_get_level(interrupt_pin) == 1) {
            return ESP_FAIL;
        }
    }

    uint8_t status;
    // Read status of Interrupt Flag Register
    esp_err_t ret = mcp2515_read_reg(MCP_CANINTF, &status);
    if (ret != ESP_OK) return ret;
    
    if (status & (MCP_INTF_RX0IF | MCP_INTF_RX1IF)) {
        return ESP_OK;
    }
    return ESP_FAIL;
}

esp_err_t mcp2515_receive(can_frame_t *frame) {
    uint8_t status;
    ESP_ERROR_CHECK(mcp2515_read_reg(MCP_CANINTF, &status));

    uint8_t cmd_byte = 0;
    uint8_t int_mask = 0;
    
    if (status & MCP_INTF_RX0IF) {
        cmd_byte = 0x90; // Read from RXB0SIDH
        int_mask = MCP_INTF_RX0IF;
    } else if (status & MCP_INTF_RX1IF) {
        cmd_byte = 0x94; // Read from RXB1SIDH
        int_mask = MCP_INTF_RX1IF;
    } else {
        return ESP_FAIL; // No message
    }

    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    
    uint8_t tx_buf[14] = {0};
    tx_buf[0] = cmd_byte;
    
    uint8_t rx_buf[14] = {0};
    
    t.length = 8 * 14; 
    t.tx_buffer = tx_buf;
    t.rx_buffer = rx_buf;
    
    ESP_ERROR_CHECK(spi_device_transmit(spi_handle, &t));
    
    // Parse Received Data
    uint8_t sidh = rx_buf[1];
    uint8_t sidl = rx_buf[2];
    uint8_t eid8 = rx_buf[3];
    uint8_t eid0 = rx_buf[4];
    uint8_t dlc_reg = rx_buf[5];
    uint8_t dlc = dlc_reg & 0x0F;
    
    frame->ext = (sidl & 0x08) ? true : false;
    frame->id = 0;
    
    if (frame->ext) {
        frame->id = ((uint32_t)sidh << 21);
        frame->id |= ((uint32_t)(sidl & 0xE0) << 13);
        frame->id |= ((uint32_t)(sidl & 0x03) << 16);
        frame->id |= ((uint32_t)eid8 << 8);
        frame->id |= eid0;
        
        frame->rtr = (dlc_reg & 0x40) ? true : false; 
    } else {
        frame->id = ((uint32_t)sidh << 3) | (sidl >> 5);
        frame->rtr = (sidl & 0x10) ? true : false; 
    }
    
    frame->dlc = dlc;
    if (dlc > 8) dlc = 8; // Cap at 8
    
    memcpy(frame->data, &rx_buf[6], dlc);
    
    // Clear interrupt flag
    mcp2515_modify_reg(MCP_CANINTF, int_mask, 0);
    
    return ESP_OK;
}

esp_err_t mcp2515_send(const can_frame_t *frame) {
    if (frame == NULL) return ESP_FAIL;
    
    uint8_t tx_buf[14] = {0};

    // Instruction: Load TX Buffer 0 (Start at TXB0SIDH)
    tx_buf[0] = 0x40; 
    
    uint32_t id = frame->id;
    
    if (frame->ext) {
        tx_buf[1] = (uint8_t)(id >> 21);
        tx_buf[2] = (uint8_t)(((id >> 13) & 0xE0) | 0x08 | ((id >> 16) & 0x03)); // EXIDE=1
        tx_buf[3] = (uint8_t)(id >> 8);
        tx_buf[4] = (uint8_t)(id);
    } else {
        tx_buf[1] = (uint8_t)(id >> 3);
        tx_buf[2] = (uint8_t)((id << 5) & 0xE0); // EXIDE=0
        tx_buf[3] = 0;
        tx_buf[4] = 0;
    }
    
    uint8_t dlc = (frame->dlc > 8) ? 8 : frame->dlc;
    tx_buf[5] = dlc;
    if (frame->rtr) tx_buf[5] |= 0x40; // RTR bit
    
    memcpy(&tx_buf[6], frame->data, dlc);
    
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    t.length = (6 + dlc) * 8; // Instruction + 5 ID/DLC + Data
    t.tx_buffer = tx_buf;
    
    esp_err_t ret = spi_device_transmit(spi_handle, &t);
    if (ret != ESP_OK) return ret;
    
    // Request To Send TXB0
    uint8_t rts_cmd = 0x81;
    memset(&t, 0, sizeof(t));
    t.length = 8;
    t.tx_buffer = &rts_cmd;
    
    return spi_device_transmit(spi_handle, &t);
}

