/* CAN MCP2515 Example with Wi-Fi & Serial Support */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <fcntl.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "sdkconfig.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "lwip/err.h"

#include "lwip/sys.h"
#include "lwip/sockets.h"

#include "mcp2515.h"

#define MCP_CS_PIN  5
#define MCP_MOSI    23
#define MCP_MISO    19
#define MCP_CLK     18
#define MCP_INT     21

#define WIFI_SSID      "ESP32-CAN-TOOL"
#define WIFI_PASS      "password"
#define WIFI_CHANNEL   1
#define MAX_STA_CONN   1
#define PORT           8080

static const char *TAG = "main";
static volatile int sock_client = -1;

// --- Function Prototypes ---
void process_command(char *cmd_buf);
void send_to_pc(const char *msg);

// --- hardware Self-Test ---
can_speed_t perform_autobaud(void) {
    ESP_LOGI(TAG, "Starting Auto-Baud Detection...");
    
    can_speed_t speeds[] = {CAN_500KBPS, CAN_250KBPS, CAN_1000KBPS, CAN_125KBPS};
    int num_speeds = 4;
    
    for (int i = 0; i < num_speeds; i++) {
        ESP_LOGI(TAG, "Trying Speed: %d...", (int)speeds[i]);
        
        // 1. Configure Speed
        ESP_ERROR_CHECK(mcp2515_set_mode(MODE_CONFIG));
        ESP_ERROR_CHECK(mcp2515_set_bitrate(speeds[i]));
        
        // 2. Set Listen Only Mode (Critical! Don't disrupt bus)
        ESP_ERROR_CHECK(mcp2515_set_mode(MODE_LISTENONLY));
        
        // 3. Listen for a set time (e.g., 500ms)
        // If traffic is heavy, we catch it instantly. If light, we need wait.
        TickType_t end_tick = xTaskGetTickCount() + pdMS_TO_TICKS(500);
        
        bool traffic_found = false;
        while (xTaskGetTickCount() < end_tick) {
            if (mcp2515_check_message() == ESP_OK) {
                traffic_found = true;
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(10));
        }
        
        if (traffic_found) {
            ESP_LOGI(TAG, "Success! Traffic detected at Speed index %d", (int)speeds[i]);
            // Switch back to Normal mode (or leave in ListenOnly if preferred)
            return speeds[i];
        }
    }
    
    ESP_LOGW(TAG, "Autobaud failed. Defaulting to 500KBPS.");
    return CAN_500KBPS; // Default if nothing found (vehicle off?)
}

void perform_mcp2515_self_test(void) {
    ESP_LOGI(TAG, "Starting MCP2515 Loopback Self-Test...");
    
    // 1. Enter Loopback Mode
    ESP_ERROR_CHECK(mcp2515_set_mode(MODE_LOOPBACK));
    vTaskDelay(pdMS_TO_TICKS(10)); // Give it a moment

    // 2. Prepare Test Frame
    can_frame_t test_frame = {
        .id = 0x123,
        .dlc = 4,
        .data = {0xDE, 0xAD, 0xBE, 0xEF},
        .ext = 0,
        .rtr = 0
    };

    // 3. Send Frame
    ESP_LOGI(TAG, "Sending Test Frame ID: 0x123...");
    esp_err_t err = mcp2515_send(&test_frame);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to send test frame!");
        mcp2515_set_mode(MODE_NORMAL);
        return;
    }

    // 4. Wait for Receipt
    vTaskDelay(pdMS_TO_TICKS(50));
    
    // 5. Check
    if (mcp2515_check_message() == ESP_OK) {
        can_frame_t rx_frame;
        if (mcp2515_receive(&rx_frame) == ESP_OK) {
            if (rx_frame.id == 0x123 && rx_frame.data[0] == 0xDE) {
                ESP_LOGI(TAG, "SELF-TEST PASSED: Received Loopback Frame!");
                ESP_LOGI(TAG, "Hardware SPI connection seems OK.");
            } else {
                ESP_LOGE(TAG, "SELF-TEST WARNING: Received wrong data ID: %lX", rx_frame.id);
            }
        } else {
             ESP_LOGE(TAG, "SELF-TEST FAIL: Could not read frame.");
        }
    } else {
        ESP_LOGE(TAG, "SELF-TEST FAIL: No frame received in Loopback.");
        ESP_LOGE(TAG, "Check SPI wiring (MISO/MOSI/CS/CLK). Check if MCP2515 has 5V (required for TJA1050 oscillator) or 3.3V.");
    }

    // 6. Restore Normal Mode
    ESP_LOGI(TAG, "Restoring Normal Mode...");
    ESP_ERROR_CHECK(mcp2515_set_mode(MODE_NORMAL));
}

// --- Wi-Fi Setup ---
static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                                    int32_t event_id, void* event_data) {
    if (event_id == WIFI_EVENT_AP_STACONNECTED) {
        wifi_event_ap_staconnected_t* event = (wifi_event_ap_staconnected_t*) event_data;
        ESP_LOGI(TAG, "station "MACSTR" join, AID=%d",
                 MAC2STR(event->mac), event->aid);
    } else if (event_id == WIFI_EVENT_AP_STADISCONNECTED) {
        wifi_event_ap_stadisconnected_t* event = (wifi_event_ap_stadisconnected_t*) event_data;
        ESP_LOGI(TAG, "station "MACSTR" leave, AID=%d",
                 MAC2STR(event->mac), event->aid);
    }
}

void wifi_init_softap(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        NULL));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid = WIFI_SSID,
            .ssid_len = strlen(WIFI_SSID),
            .channel = WIFI_CHANNEL,
            .password = WIFI_PASS,
            .max_connection = MAX_STA_CONN,
            .authmode = WIFI_AUTH_WPA_WPA2_PSK,
        },
    };
    if (strlen(WIFI_PASS) == 0) {
        wifi_config.ap.authmode = WIFI_AUTH_OPEN;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "wifi_init_softap finished. SSID:%s password:%s channel:%d",
             WIFI_SSID, WIFI_PASS, WIFI_CHANNEL);
}

// --- TCP Server Task ---
void tcp_server_task(void *pvParameters) {
    char rx_buffer[512];
    char addr_str[128];
    int addr_family = AF_INET;
    int ip_protocol = 0;
    struct sockaddr_in6 dest_addr;

    struct sockaddr_in *dest_addr_ip4 = (struct sockaddr_in *)&dest_addr;
    dest_addr_ip4->sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr_ip4->sin_family = AF_INET;
    dest_addr_ip4->sin_port = htons(PORT);
    ip_protocol = IPPROTO_IP;

    int listen_sock = socket(addr_family, SOCK_STREAM, ip_protocol);
    if (listen_sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }
    
    // Set SO_REUSEADDR
    int opt = 1;
    setsockopt(listen_sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    ESP_LOGI(TAG, "Socket created");

    // Enable Keep Alive (Optional, for TCP level)
    int keepAlive = 1;
    setsockopt(listen_sock, SOL_SOCKET, SO_KEEPALIVE, &keepAlive, sizeof(int));

    int err = bind(listen_sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    if (err != 0) {
        ESP_LOGE(TAG, "Socket unable to bind: errno %d", errno);
        close(listen_sock);
        vTaskDelete(NULL);
        return;
    }
    ESP_LOGI(TAG, "Socket bound, port %d", PORT);

    err = listen(listen_sock, 1);
    if (err != 0) {
        ESP_LOGE(TAG, "Error occurred during listen: errno %d", errno);
        close(listen_sock);
        vTaskDelete(NULL);
        return;
    }

    while (1) {
        ESP_LOGI(TAG, "Socket listening");

        struct sockaddr_storage source_addr;
        socklen_t addr_len = sizeof(source_addr);
        sock_client = accept(listen_sock, (struct sockaddr *)&source_addr, &addr_len);
        
        if (sock_client < 0) {
            ESP_LOGE(TAG, "Unable to accept connection: errno %d", errno);
            break;
        }

        // Convert ip address to string
        if (source_addr.ss_family == PF_INET) {
            inet_ntoa_r(((struct sockaddr_in *)&source_addr)->sin_addr, addr_str, sizeof(addr_str) - 1);
        }
        ESP_LOGI(TAG, "Socket accepted ip address: %s", addr_str);
        
        // Set NoDelay (Nagle Disable) to improve latency
        int nodelay = 1;
        setsockopt(sock_client, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof(nodelay));

        // Receive Loop
        while (1) {
            int len = recv(sock_client, rx_buffer, sizeof(rx_buffer) - 1, 0);
            if (len < 0) {
                ESP_LOGE(TAG, "Error occurred during receiving: errno %d", errno);
                break;
            } else if (len == 0) {
                ESP_LOGI(TAG, "Connection closed");
                break;
            } else {
                rx_buffer[len] = 0; // Null-terminate
                
                // Process multiple commands separated by \n using strtok_r
                char *saveptr;
                char *line = strtok_r(rx_buffer, "\n", &saveptr);
                while (line != NULL) {
                    // Remove carriage return
                    size_t l = strlen(line);
                    if (l > 0 && line[l-1] == '\r') line[l-1] = 0;

                    if (strlen(line) > 0) {
                        ESP_LOGI(TAG, "TCP RX: %s", line); // Log the command
                        process_command(line);
                    }
                    
                    line = strtok_r(NULL, "\n", &saveptr);
                }
            }
        }

        shutdown(sock_client, 0);
        close(sock_client);
        sock_client = -1;
    }
    
    close(listen_sock);
    vTaskDelete(NULL);
}

// --- Common Logic ---
void send_to_pc(const char *msg) {
    // 1. Send to Serial
    printf("%s\n", msg);
    
    // 2. Send to TCP if connected
    if (sock_client != -1) {
        // Needs newline for Python logic
        char buf[256];
        snprintf(buf, sizeof(buf), "%s\n", msg);
        send(sock_client, buf, strlen(buf), 0);
    }
}

void process_command(char *cmd_buf) {
    if (strncmp(cmd_buf, "CAN_SPEED:", 10) == 0) {
        int speed_kbps = atoi(cmd_buf + 10);
        ESP_LOGI(TAG, "CMD Speed: %d kbps", speed_kbps);
        
        ESP_ERROR_CHECK(mcp2515_set_mode(MODE_CONFIG));
        esp_err_t err = mcp2515_set_bitrate((can_speed_t)speed_kbps);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "Speed changed OK");
        } else {
            ESP_LOGE(TAG, "Speed change FAIL");
        }
        ESP_ERROR_CHECK(mcp2515_set_mode(MODE_NORMAL));
    }
    else if (strncmp(cmd_buf, "TX:", 3) == 0) {
        // TX:ID,DLC,D0...
        can_frame_t tx_frame;
        memset(&tx_frame, 0, sizeof(tx_frame));
        
        char *ptr = cmd_buf + 3;
        char *token = strtok(ptr, ",");
        
        if (token) {
            tx_frame.id = (uint32_t)strtoul(token, NULL, 16);
            token = strtok(NULL, ",");
            if (token) {
                tx_frame.dlc = (uint8_t)atoi(token);
                tx_frame.rtr = 0;
                tx_frame.ext = (tx_frame.id > 0x7FF) ? 1 : 0;
                
                for (int i = 0; i < tx_frame.dlc; i++) {
                    token = strtok(NULL, ",");
                    if (token) {
                        tx_frame.data[i] = (uint8_t)strtoul(token, NULL, 16);
                    }
                }
                
                esp_err_t tx_err = mcp2515_send(&tx_frame);
                if (tx_err == ESP_OK) {
                   // Optional confirmation
                } else {
                   // Error
                }
            }
        }
    }
}


void app_main(void)
{
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_LOGI(TAG, "ESP_WIFI_MODE_AP");
    wifi_init_softap();
    
    // Start TCP Server
    xTaskCreate(tcp_server_task, "tcp_server", 4096, NULL, 5, NULL);

    // Set stdin to non-blocking
    fcntl(fileno(stdin), F_SETFL, O_NONBLOCK);

    ESP_LOGI(TAG, "Init SPI...");
    spi_bus_config_t buscfg = {
        .miso_io_num = MCP_MISO,
        .mosi_io_num = MCP_MOSI,
        .sclk_io_num = MCP_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 0
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO));

    ESP_LOGI(TAG, "Init MCP2515...");
    ESP_ERROR_CHECK(mcp2515_init(SPI2_HOST, MCP_CS_PIN, MCP_INT));
    
    // Auto-Detect Speed
    can_speed_t detected_speed = perform_autobaud();
    
    // Set Final Speed and Mode
    ESP_ERROR_CHECK(mcp2515_set_mode(MODE_CONFIG));
    ESP_ERROR_CHECK(mcp2515_set_bitrate(detected_speed));
    
    // Run Self-Test (Skip loopback test if we want to process real data, 
    // or keep it if we want to integrity check logic)
    // perform_mcp2515_self_test(); // Disabled to prefer Live Data
    
    // Enter Normal Mode to Interact
    ESP_ERROR_CHECK(mcp2515_set_mode(MODE_NORMAL));

    ESP_LOGI(TAG, "Ready...");

    can_frame_t frame;
    char cmd_buf[64];
    char out_buf[128];

    while (1) {
        // 1. Check Serial Input
        if (fgets(cmd_buf, sizeof(cmd_buf), stdin) != NULL) {
            cmd_buf[strcspn(cmd_buf, "\r\n")] = 0;
            process_command(cmd_buf);
        }

        // 2. Check CAN Message (Process up to 10 frames per loop)
        int frames_processed = 0;
        while (mcp2515_check_message() == ESP_OK && frames_processed < 10) {
            if (mcp2515_receive(&frame) == ESP_OK) {
                // PKT:ID,DLC,D0...
                int offset = snprintf(out_buf, sizeof(out_buf), "PKT:%lX,%d", frame.id, frame.dlc);
                if (!frame.rtr) {
                    for (int i = 0; i < frame.dlc; i++) {
                        offset += snprintf(out_buf + offset, sizeof(out_buf) - offset, ",%02X", frame.data[i]);
                    }
                }
                send_to_pc(out_buf);
            }
            frames_processed++;
        }
        
        // Yield to IDLE task
        vTaskDelay(1);
    }
}

