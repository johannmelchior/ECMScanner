# Firmware AVR

Base inicial para um firmware proprio para a interface AVR usada com software Wolks falsificado.

Objetivo:
- reutilizar o hardware existente da interface
- falar com o PC via FT245RL
- controlar K-Line via L9637D
- controlar CAN via SJA1000 + TJA1040C
- expor uma interface USB simples para o software do PC

Arquitetura alvo presumida:

```text
PC <-> FT245RL <-> ATmega162 <-> L9637D <-> Yamaha K-Line
                    \-> SJA1000 -> TJA1040C -> BRP CAN
```

Estado atual:
- AVR alvo: ATmega162
- clock confirmado: cristal de 16 MHz (`F_CPU=16000000UL`; o bootloader de 500000 baud so responde porque ja foi compilado para 16 MHz)
- placa destravada para gravacao ISP
- interface fisica ja esta em maos para inspecao e continuidade
- interface USB confirmada como FTDI FT245RL
- controlador CAN confirmado como SJA1000T
- transceptor K-Line confirmado no verso como L9637D
- transceptor CAN confirmado no verso como TJA1040C
- header inferior confirmado como ICSP, com ligacoes ao menos para `MISO` e `MOSI` do ATmega162
- camada FT245RL ja estruturada com handshake `RD#`/`WR#`/`RXF#`/`TXE#` e buffers RX/TX em software
- protocolo USB inicial para K-Line Yamaha implementado (`WAKEUP`, `SET_BAUD`, `TX_BYTE`, `RX_BYTE`)
- acesso inicial a registradores do SJA1000T implementado para `init`, `TX` e `RX` de frames CAN padrao
- bitrates CAN suportados hoje no firmware: `50`, `100`, `125`, `250`, `500` e `1000 kbps`
- `1 Mbps` ja esta previsto para CAN HS com `SJA1000T + TJA1040C`, sujeito a validacao em barramento real
- protocolo USB operando exclusivamente em modo enquadrado `SYNC/LEN/CMD/PAYLOAD/CHECKSUM`
- modo de boot padrao atualizado para `Yamaha passthrough` (bridge bruto USB<->K-Line, sem framing)

## Estrutura

- `src/`
  - codigo-fonte principal do firmware
- `include/`
  - headers de board, K-Line, CAN e USB/FIFO
- `docs/`
  - notas de arquitetura e bring-up
- `tools/`
  - scripts auxiliares futuros para build/flash/log

## Fases recomendadas

1. Bring-up do AVR
2. Comunicacao basica com FT245RL
3. Bridge K-Line bruto
4. Bridge CAN bruto
5. Protocolo USB minimo com comandos simples
6. Integracao com ferramentas do PC

## Build esperado

Toolchain AVR classica:
- avr-gcc
- avr-libc
- avr-objcopy
- avrdude

Build local:

```powershell
cd c:\Users\johan\Documents\projetoCAN\firmware AVR
make
```

Flash via ISP (metodo validado):

```powershell
cd c:\Users\johan\Documents\projetoCAN\firmware AVR
make flash PROGRAMMER=arduino PORT=COM13 BAUD=19200
```

Check de assinatura do MCU (sem gravar):

```powershell
cd c:\Users\johan\Documents\projetoCAN\firmware AVR
avrdude -v -p m162 -c arduino -P COM13 -b 19200 -n
```

Resultado esperado do check:
- `Device signature = 1E 94 04 (ATmega162)`

Automacao build+flash+check:

```powershell
cd c:\Users\johan\Documents\projetoCAN\firmware AVR
./tools/build_flash_check.ps1 -Port COM13
```

## Escopo do firmware

Este firmware deve ser enxuto. A interpretacao do protocolo Yamaha K-Line e BRP CAN deve ficar no PC sempre que possivel.

No AVR, o foco deve ser:
- transporte bruto
- temporizacao de wakeup
- configuracao de baud e bitrate
- TX/RX de K-Line
- TX/RX de CAN
- framing simples USB <-> MCU

### Boot padrao: enquadrado (operacao normal)

O firmware sobe em `MODE_KLINE` com protocolo enquadrado, que e o que o scanner
PC (`ecm_scanner`) precisa. Controlado em `src/main.c`:

- `#define YAMAHA_PASSTHROUGH_BOOT 0U` (**padrao atual**)
- `#define YAMAHA_PASSTHROUGH_BOOT 1U` para passthrough bruto USB <-> K-Line

> **Aviso importante:** em `PASSTHROUGH_BOOT 1U` o loop principal faz `continue`
> antes de `process_usb_commands()`, portanto **nenhum comando enquadrado e
> processado**. Consequencias praticas:
> - o `CMD_REBOOT (0x05)` deixa de funcionar e a entrada no bootloader passa a
>   exigir **reset fisico** (replugar o USB);
> - os bytes que a app envia (`5A ...`) sao despejados **crus na K-Line** como
>   lixo, o que aparece como "ruido" no barramento e impede qualquer resposta.
>
> Use passthrough apenas quando quiser passar o YDS original pela interface;
> para o scanner volte a `0U`.

Limitacoes atuais da camada CAN:
- a API USB exposta hoje cobre apenas frames padrao de `11 bits`
- `CAN_RX_POLL` trabalha por polling; ainda nao ha fila orientada a interrupcao no AVR
- o firmware ainda nao expoe status detalhado do controlador (`bus-off`, erros, counters, arbitration lost)
- filtros de aceitacao e timestamps ainda nao sao configuraveis pelo PC

## FT245RL com placa em mao

A camada `usb_fifo` ja foi preparada para o fluxo paralelo do FT245RL:
- barramento de dados de 8 bits separado dos sinais de controle
- leitura e escrita nao bloqueantes via `usb_fifo_poll()`
- filas RX/TX em RAM para desacoplar protocolo e tempo de barramento

Com o mapeamento FT245RL confirmado, o firmware ja usa `BOARD_HAS_FT245=1` em `board.h`.

## Protocolo USB minimo com modos K-Line/CAN

Modos:
- `0x00` `IDLE`
- `0x01` `K-LINE`
- `0x02` `CAN`

Codigos de status nas respostas:
- `0xA5` `RSP_OK`
- `0x7F` `RSP_ERR`
- `0xA6` `RSP_NO_DATA` (quando aplicavel)

Lista completa de comandos aceitos pelo firmware:

1. `0x01` `GET_INFO`
- Payload RX: nenhum
- Resposta: `RSP_OK, 0x1C, <modo_ativo>`

2. `0x02` `SET_MODE`
- Payload RX: `<mode>` (`0x00`, `0x01`, `0x02`)
- Resposta: `RSP_OK` ou `RSP_ERR`

3. `0x03` `KLINE_WAKEUP`
- Payload RX: nenhum
- Requisito: modo ativo `K-LINE`
- Resposta: `RSP_OK` ou `RSP_ERR`

4. `0x04` `GET_MODE`
- Payload RX: nenhum
- Resposta: `RSP_OK, <modo_ativo>`

5. `0x10` `KLINE_SET_BAUD`
- Payload RX: `baud_lo, baud_hi`
- Requisito: modo ativo `K-LINE`
- Resposta: `RSP_OK` ou `RSP_ERR`

6. `0x11` `KLINE_TX_BYTE`
- Payload RX: `byte`
- Requisito: modo ativo `K-LINE`
- Resposta: `RSP_OK` ou `RSP_ERR`

7. `0x12` `KLINE_RX_BYTE`
- Payload RX: `timeout_lo, timeout_hi` (ms)
- Requisito: modo ativo `K-LINE`
- Resposta de sucesso: `RSP_OK, <byte>`
- Resposta de falha/timeout: `RSP_ERR, 0x00`

8. `0x15` `KLINE_WAIT_HIGH`
- Payload RX: `timeout_lo, timeout_hi, stable_lo, stable_hi` (ms)
- Requisito: modo ativo `K-LINE`
- Semantica: aguarda a K-Line ficar baixa e depois subir, permanecendo em nivel alto por `stable_ms`
- Resposta de sucesso: `RSP_OK`
- Resposta de falha/timeout: `RSP_ERR`

9. `0x16` `KLINE_GET_STATUS`
- Payload RX: `observe_lo, observe_hi` (ms)
- Requisito: modo ativo `K-LINE`
- Resposta: `RSP_OK, state, high_lo, high_hi, low_lo, low_hi, edges, rx_bytes`
- `state=0`: linha baixa estavel
- `state=1`: linha alta estavel
- `state=2`: atividade/comunicacao detectada
- `high_*` / `low_*`: tempo observado em alto/baixo durante a janela
- `edges`: quantidade de transicoes vistas na amostragem
- `rx_bytes`: quantidade de bytes UART recebidos na janela

10. `0x19` `KLINE_SNIFF`
- Payload RX: `enable` (`0x00` desativa, `0x01` ativa)
- Requisito: modo ativo `K-LINE`
- Semantica: ativa sniff cego da linha (somente RX, sem handshake/protocolo)
- Ao ativar, o firmware desliga `KLINE_KEEPALIVE` para nao injetar trafego
- Resposta: `RSP_OK, enabled` ou `RSP_ERR`

Pacote push usado durante sniff:
- `CMD=0x25` `KLINE_SNIFF_AUTO`
- Payload TX: `RSP_OK, raw_byte, err_flags`
- `err_flags`: bit0=`FE`, bit1=`DOR`, bit2=`UPE`
- Observacao: bytes com erro tambem sao enviados (modo bruto)

11. `0x20` `CAN_SET_BITRATE`
- Payload RX: `kbps_lo, kbps_hi`
- Requisito: modo ativo `CAN`
- Resposta: `RSP_OK` ou `RSP_ERR`

12. `0x21` `CAN_TX_STD`
- Payload RX: `id_lo, id_hi(11-bit), dlc, data[dlc]`
- Requisito: modo ativo `CAN`
- Regras: `dlc <= 8`, tamanho do payload deve bater com `dlc`
- Resposta: `RSP_OK` ou `RSP_ERR`

13. `0x22` `CAN_RX_POLL`
- Payload RX: nenhum
- Requisito: modo ativo `CAN`
- Resposta com frame: `RSP_OK, id_lo, id_hi, dlc, data[dlc]`
- Sem frame disponivel: `RSP_NO_DATA`
- Erro de modo/parametro: `RSP_ERR`

14. `0x23` `CAN_GET_STATUS`
- Payload RX: nenhum
- Requisito: modo ativo `CAN`
- Resposta: `RSP_OK, sr, rxerr, txerr, ecc, alc, ewl, rmc, kbps_lo, kbps_hi`
- `sr` = registrador de status bruto do `SJA1000T`
- `rxerr` / `txerr` = contadores de erro RX/TX
- `ecc` = ultimo `Error Code Capture`
- `alc` = ultimo `Arbitration Lost Capture`
- `ewl` = `Error Warning Limit`
- `rmc` = quantidade de mensagens atualmente na FIFO RX do controlador

Observacoes:
- Modo enquadrado usa `SYNC=0x5A`, `LEN`, `CMD`, `PAYLOAD`, `CHECKSUM(XOR)`.
- O envio/leitura K-Line atual usa a USART de hardware do ATmega162 com baud configuravel; apenas os pulsos de wakeup seguem em GPIO manual.
- a inicializacao Yamaha no scanner agora consulta `KLINE_GET_STATUS` no connect de `Yamaha 10400` e classifica a linha como `baixo`, `alto` ou `comunicando` antes de decidir se espera a subida, segue direto para o wakeup ou evita interferir num barramento ja ativo.
- no caminho AVR aplicacao <-> PC, as ferramentas passam a usar `1000000 baud` por padrao no lado host; o bootloader continua documentado em `500000 baud` ate nova validacao de bancada.
- E uma base inicial para bring-up; ajustes finos de temporizacao podem ser necessarios na bancada.

## Protocolo USB enquadrado

O firmware usa exclusivamente o protocolo enquadrado para operacao robusta e para reuso futuro no bootloader.

Formato do pacote:

```text
0x5A | LEN | CMD | PAYLOAD... | CHECKSUM
```

Onde:
- `0x5A` = byte de sincronismo
- `LEN` = tamanho do payload
- `CMD` = comando
- `CHECKSUM` = XOR de `LEN`, `CMD` e bytes de `PAYLOAD`

Todos os comandos USB do firmware sao trafegados no formato enquadrado.

## Bootloader FT245

A arquitetura inicial do bootloader via FT245RL foi documentada em:
- `docs/bootloader_ft245.md`

Resumo:
- o bootloader ficaria no `ATmega162`, nao no `FT245RL`
- o `FT245RL` seria apenas o transporte USB/FIFO
- o protocolo enquadrado atual foi escolhido para poder ser reutilizado no bootloader

### Procedimento de flash via bootloader

Fluxo validado na bancada. **Confirmar sempre a porta**: a interface aparece como
`USB Serial Port (COMx)` com `VID_0403 PID_6001` e pode mudar de numero.

```powershell
Get-CimInstance Win32_PnPEntity | Where-Object { $_.DeviceID -like "*VID_0403*" }
```

O bootloader FT245 responde a `500000 baud`.

> **Se o firmware gravado estiver em `PASSTHROUGH_BOOT 1U`**, o `CMD_REBOOT` nao
> e processado e o script falha com "Bootloader nao respondeu". Nesse caso a
> entrada exige **reset fisico**: correr o flasher e replugar o USB durante a
> janela de sondagem.

1. Build do firmware:

```powershell
make -C "firmware AVR"
```

2. Confirmar que o bootloader responde antes de gravar (reset fisico se preciso):

```powershell
$env:PYTHONIOENCODING = "utf-8"
z:/projetoCAN/.venv/Scripts/python.exe "z:/projetoCAN/python-code/avr_flasher.py" --port COM8 --baud 500000 --info --timeout 25
```

Resposta esperada:
- `Bootloader v1 detectado`
- `Tamanho de pagina : 128 bytes`
- `Paginas de app    : 112`
- `Boot section start: 0x3800`

3. Gravar o firmware e verificar CRC:

```powershell
z:/projetoCAN/.venv/Scripts/python.exe "z:/projetoCAN/python-code/avr_flasher.py" --port COM8 --baud 500000 --hex "z:/projetoCAN/firmware AVR/build/firmware_avr.hex" --verify --jump
```

> `PYTHONIOENCODING=utf-8` e obrigatorio: sem ele a barra de progresso rebenta com
> `UnicodeEncodeError` a meio da gravacao (a app fica apagada).

Observacoes praticas:
- esse e o metodo preferido para atualizacao rotineira; `ICSP` fica para recuperacao, fuses e primeiro bootloader
- se `--info` nao responder, verificar se a interface ainda esta em `COM7`
- o bootloader desta placa usa pagina de `128 bytes`, nao `256`

Troca de modo na pratica:
1. mandar `SET_MODE 0x01` para entrar em K-Line
2. usar `KLINE_SET_BAUD`, `KLINE_WAKEUP`, `KLINE_TX_BYTE`, `KLINE_RX_BYTE`
3. mandar `SET_MODE 0x02` para entrar em CAN
4. usar `CAN_SET_BITRATE`, `CAN_TX_STD`, `CAN_RX_POLL`

## Inspecao visual atual

Pelos dados atuais ja da para afirmar:
- o microcontrolador principal e um ATmega162 em encapsulamento TQFP
- existe um FTDI FT245RL dedicado para a interface USB
- o chip longo escurecido da frente e um SJA1000T
- o verso traz um L9637D para K-Line
- o verso tambem traz um transceptor CAN TJA1040C
- o conector inferior e um ICSP com ligacoes confirmadas para `MISO` e `MOSI`
- o clock do AVR vem de um cristal de 16 MHz (`F_CPU=16000000UL`)

Ainda falta fechar com seguranca:
- quais portas do AVR estao ligadas ao FTDI
- quais linhas do ICSP alem de `MISO` e `MOSI` ja foram confirmadas
- qual pino do conector OBD vai para K-Line ou CAN