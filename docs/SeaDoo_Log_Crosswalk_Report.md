# Sea-Doo Log x ODX Crosswalk

Fontes:
- Log: firmware-esp32-projetocan/extracted_uds.csv
- Mapa ODX: docs/seadoo_odx_can_map.csv

Arquivos gerados:
- docs/seadoo_log_crosswalk.csv

## Resumo
- Frames no log: 271
- IDs observados unicos: 4
- IDs observados com match no ODX: 4
- IDs observados sem match no ODX: 0

## Top IDs observados (log)
- 7E0: 117 frames
- 7E8: 60 frames
- 7BB: 51 frames
- 7B3: 43 frames

## Top correspondencias ODX
- ID 7E0 -> Engine Control Module NEWX [ECM] (request) req=7E0 resp=7E8 frames=117
- ID 7E0 -> Vehicle Control Unit [VCU] (request) req=7E0 resp=7E8 frames=117
- ID 7E0 -> N/A [N/A] (request) req=7E0 resp=7E8 frames=117
- ID 7E0 -> Starboard Engine Control Module [Starboard] (request) req=7E0 resp=7E8 frames=117
- ID 7E0 -> Engine Control Module ETEC 2 [ECM] (request) req=7E0 resp=7E8 frames=117
- ID 7E0 -> Engine Control Module [ECM] (request) req=7E0 resp=7E8 frames=117
- ID 7E0 -> Engine Control Module EZ [ECM] (request) req=7E0 resp=7E8 frames=117
- ID 7E0 -> Engine Control Module [ECM] (request) req=7E0 resp=7E8 frames=117
- ID 7E8 -> Engine Control Module NEWX [ECM] (response) req=7E0 resp=7E8 frames=60
- ID 7E8 -> Vehicle Control Unit [VCU] (response) req=7E0 resp=7E8 frames=60
- ID 7E8 -> N/A [N/A] (response) req=7E0 resp=7E8 frames=60
- ID 7E8 -> Starboard Engine Control Module [Starboard] (response) req=7E0 resp=7E8 frames=60
- ID 7E8 -> Engine Control Module ETEC 2 [ECM] (response) req=7E0 resp=7E8 frames=60
- ID 7E8 -> Engine Control Module [ECM] (response) req=7E0 resp=7E8 frames=60
- ID 7E8 -> Engine Control Module EZ [ECM] (response) req=7E0 resp=7E8 frames=60
- ID 7E8 -> Engine Control Module [ECM] (response) req=7E0 resp=7E8 frames=60
- ID 7BB -> HUB3 Cluster 5 [Cluster] (response) req=7B3 resp=7BB frames=51
- ID 7BB -> VIP Cluster [Cluster] (response) req=7B3 resp=7BB frames=51
- ID 7B3 -> HUB3 Cluster 5 [Cluster] (request) req=7B3 resp=7BB frames=43
- ID 7B3 -> VIP Cluster [Cluster] (request) req=7B3 resp=7BB frames=43

## Servicos UDS vistos no payload (byte 2)
- SID 0x22: 86 frames
- SID 0x7E: 44 frames
- SID 0x2F: 32 frames
- SID 0x3E: 30 frames
- SID 0x6F: 26 frames
- SID 0x62: 22 frames
- SID 0x30: 6 frames
- SID 0x00: 5 frames
- SID 0x50: 4 frames
- SID 0x67: 2 frames
- SID 0x10: 2 frames
- SID 0x27: 2 frames
- SID 0xD9: 1 frames
- SID 0xC8: 1 frames
- SID 0x93: 1 frames
- SID 0x77: 1 frames
- SID 0xE5: 1 frames
- SID 0xE3: 1 frames
- SID 0x70: 1 frames
- SID 0x0E: 1 frames
- SID 0x48: 1 frames
- SID 0x7F: 1 frames

## Observacao
- Este cruzamento usa CAN ID para mapear modulo e direcao diagnostica (request/response).
- Para mapear DID/DTC detalhado, o proximo passo e decodificar payload por SID (ex.: 22, 19, 3E).
