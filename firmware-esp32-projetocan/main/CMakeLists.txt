idf_component_register(SRCS  "main.c" "mcp2515.c"
                       INCLUDE_DIRS "."
                       REQUIRES nvs_flash esp_wifi esp_netif lwip driver)

