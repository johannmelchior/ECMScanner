# ECMScanner

Implementação aberta de um scanner de diagnóstico para ECUs de motos de água e
motoneiges **BRP** (Sea-Doo / Ski-Doo) e **Yamaha** (WaveRunner), com interface
própria em CAN e K-Line.

O objectivo é ler códigos de falha, monitorizar parâmetros e accionar actuadores
sem depender do software do fabricante.

## Estado actual

| Área | Situação |
|---|---|
| BRP — CAN (UDS/KWP) | DTC por modelo, 39 modelos / 976 entradas, identificação por VIN |
| Yamaha — K-Line | Base de DTC do YDS (73 códigos numéricos), monitor e actuadores |
| Interface AVR | K-Line + CAN, firmware próprio, bootloader FT245 |
| Interface ESP32 | CAN + ponte Wi-Fi |
| Engenharia inversa | BUDS2 e YDS documentados (ver `docs/`) |

## Estrutura

```
ecm_scanner/                Aplicação principal (Python + CustomTkinter)
  main.py                   Interface e lógica de diagnóstico
  avr_interface.py          Protocolo USB do firmware AVR
  yds_protocol.py           Elo série Yamaha reconstruído do YDS.exe
  brp_dtc_by_model.json     Base de DTC BRP por modelo (gerada)
  yamaha_dtc_codes.json     Base de DTC Yamaha (gerada)
  tools/                    Geradores das bases de dados

firmware AVR/                    Firmware ATmega162 @ 16 MHz (avr-gcc)
firmware-esp32-projetocan/       Firmware ESP32 (ESP-IDF)
python-code/                     Scripts de engenharia inversa e análise de barramento
docs/                            Relatórios técnicos e protocolos reconstruídos
```

## Hardware

- **Interface AVR** — ATmega162 a 16 MHz, ponte USB FT245, saídas K-Line e CAN.
  Ver [`firmware AVR/README.md`](firmware%20AVR/README.md).
- **Interface ESP32** — transceiver CAN + SoftAP para diagnóstico sem fios.

## Como executar

```powershell
cd ecm_scanner
pip install -r requirements.txt
python main.py
```

Os testes do elo Yamaha correm sem hardware:

```powershell
cd ecm_scanner
python -m unittest test_yds_protocol -v
```

## Documentação técnica

| Documento | Conteúdo |
|---|---|
| [YDS_Protocol_Decompiled.md](docs/YDS_Protocol_Decompiled.md) | Protocolo do `YDS.exe` descompilado com Ghidra |
| [YDS_InstImage_Analysis.md](docs/YDS_InstImage_Analysis.md) | Formato das bases `.dbf` do YDS |
| [YDS_Capture_Procedure.md](docs/YDS_Capture_Procedure.md) | Como capturar o tráfego e diagnosticar falhas |
| [BUDS2_ReversEngineering_Analysis.md](docs/BUDS2_ReversEngineering_Analysis.md) | Formato `.buds2`, `.i2s` e licenciamento |
| [BRP_DTC_Protocol_Details.md](docs/BRP_DTC_Protocol_Details.md) | DTC no CAN da BRP |

## O que **não** está versionado

Este repositório contém apenas código e documentação. Ficam de fora, por serem
locais, proprietários ou dados de veículos concretos:

- ambientes virtuais, `build/`, `dist/` e firmware compilado;
- `sessions_decrypted/`, `*.buds2`, `*.i2s`, `*.odx`, `*.dbf` — material da BRP;
  regenerar com `ecm_scanner/tools/build_brp_dtc_by_model.py`;
- chaves, licenças e identificadores de máquina;
- capturas de barramento (`*.pcapng`, `can_log_*.csv`, `logs/`) e capturas do
  analisador lógico;
- instaladores de terceiros e datasheets.

Ver [`.gitignore`](.gitignore) para a lista completa e o motivo de cada regra.

## Aviso

Trabalho independente de interoperabilidade sobre equipamento próprio. Não é
distribuído qualquer binário, chave ou base de dados dos fabricantes; as bases
`*.json` são dados derivados, gerados localmente a partir de software
licenciado pelo utilizador.

