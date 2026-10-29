# Sea-Doo CAN Diagnostic Map (from EDB)

Fonte analisada:
- EDB extraido: C:\Users\johan\Documents\projetoCAN\temp_7z\keygen2\edb_extracted\edb.xml

Arquivos gerados:
- Tabela completa CSV: docs/seadoo_odx_can_map.csv

## Resumo rapido

- Total de entradas ODX (odxBaseVariants): 93
- IDs CAN de requisicao unicos: 41
- IDs CAN de resposta unicos: 42

Top CAN IDs de requisicao (frequencia):
- 71E -> 9
- 7E0 -> 8
- 7A4 -> 7
- 7C0 -> 6
- 7C7 -> 5
- 710 -> 5
- 7B6 -> 3
- 7C1 -> 3
- 7A3 -> 3
- 7B5 -> 3
- 7B2 -> 3
- 713 -> 3

## Mapa focado (modulos-chave)

Observacao: este mapa representa enderecamento diagnostico (UDS/ODX), nao sinais broadcast de runtime.

### ECM
- Engine Control Module: req 710 / resp 720 (extended true, reqExt 1, respExt F3)
- Engine Control Module: req 7E0 / resp 7E8 (extended false)
- Variantes: ETEC, ETEC 2, EZ, KA, M3C, M3C NG, NEWX

### IBR e IBRM
- Intelligent Brake Reverse Module (IBR): req 7B2 / resp 7BA
- IBR variante extended: req 718 / resp 728 (reqExt 9, respExt F3)
- Intelligent Brake Reverse Monitor (IBRM): req 7B5 / resp 7BD
- IBRM variante extended: req 71B / resp 72B (reqExt C, respExt F3)

### Cluster / HUB
- Cluster Module: req 713 / resp 723 (extended true)
- Cluster Module (funcional): req 7C0 / resp 7C8 (extended false)
- HUB2 Cluster: req 7C0 / resp 7C0
- HUB3 Cluster 5: req 7B3 / resp 7BB
- HUB3 Cluster 7_10 e Info Display: req 7C0 / resp 7C8

### VCM / ABS
- Vehicle Control Module: req 715 / resp 725 (extended true)
- Vehicle Control Module: req 7B6 / resp 7BE (extended false)
- ABS/VCM (2WV): req 7B6 / resp 7BE

### CCK (Configuration Keys)
- Familia CCK principal: req 71E / resp 72E
- Variacoes: VTS, SKI Mode, X-PACK, Track Kit, Trixx, Australia, JPS
- CCK Gen2 Track Kit: req 7A4 / resp 7AC

### Outros relevantes
- DPS: req 716/726 e 7C3/7CB
- THCM: req 735/745 e 7C6/7CE
- GPSCAN: req 7A6 / resp 7AD
- BCM: req 762 / resp 76A
- BMS: req 7C1 / resp 7C9
- OBC: req 767 / resp 76F; OBC Slave req 760 / resp 768
- INV: req 770 / resp 778
- SDCU: req 7A3 / resp 7AB

## Proximo passo sugerido

Para cruzar este mapa com seus logs CAN reais, use RequestedCanId/ResponseCanId da planilha CSV como chave de correlacao com os IDs observados no barramento.
