# Bring-up Plan

## Meta inicial

Obter um firmware minimo confiavel para provar que o ATmega162 esta sob controle e que a interface consegue trocar dados com o PC.

## Fase 1 - Bring-up AVR

1. Compilar e gravar um firmware minimo
2. Confirmar reset, clock e watchdog
3. Piscar LED de status, se houver LED conhecido
4. Caso nao haja LED conhecido, alternar um GPIO de teste

## Fase 2 - FT245RL

1. Confirmar mapeamento de dados e sinais de handshake
2. Implementar envio de bytes do AVR para o PC
3. Implementar recebimento de bytes do PC para o AVR
4. Criar comando `PING` / resposta `PONG`
5. Validar no hardware cada sinal com multimetro antes de habilitar `BOARD_HAS_FT245`
6. Testar especificamente `D0..D7`, `RXF#`, `TXE#`, `RD#` e `WR#` do FT245RL

## Fase 3 - K-Line

1. Confirmar pinos do L9637D no AVR
2. Implementar idle, drive low e leitura RX
3. Implementar envio UART simples em baud configuravel
4. Implementar wakeup Yamaha com temporizacao customizada

## Fase 4 - CAN

1. Confirmar barramento entre AVR e SJA1000
2. Ler/escrever registradores do SJA1000
3. Inicializar bitrate e modo normal
4. Receber frames e encaminhar ao PC
5. Transmitir frames recebidos do PC

## Fase 5 - Protocolo USB minimo

Comandos sugeridos:
- `0x01` GET_INFO
- `0x02` SET_MODE
- `0x03` KLINE_WAKEUP
- `0x04` KLINE_TX
- `0x05` CAN_SET_BITRATE
- `0x06` CAN_TX
- `0x07` GPIO_SET

## Riscos abertos

1. Pinagem real do SJA1000 ainda nao confirmada
2. Pinagem real do L9637D ainda nao confirmada
3. FT245RL usa FIFO, nao UART COM direta
4. Placa pode ter glue logic adicional nao documentada

## Inspecao fisica inicial

Achados da foto frontal:
- ATmega162 confirmado visualmente
- FT245RL confirmado visualmente
- SJA1000T confirmado visualmente no CI longo da face frontal
- ha um header inferior confirmado como ICSP

Achados da foto traseira e da inspecao manual:
- L9637D confirmado no verso como interface K-Line
- transceptor CAN dedicado presente no verso
- cristal do AVR confirmado em 16 MHz
- ICSP com ligacoes confirmadas pelo menos para `MISO` e `MOSI`

Checklist de confirmacao com a placa em bancada:
1. tirar foto do verso da placa
2. tirar macro legivel da marcacao do CI FTDI e do CI longo a esquerda
3. medir continuidade entre header ISP e pinos do ATmega162 para localizar `MISO`, `MOSI`, `SCK`, `RESET`, `VCC` e `GND`
4. medir continuidade entre o FTDI e as portas do AVR para montar o mapa do barramento
5. medir continuidade entre o conector OBD e os CIs de interface para separar K-Line e CAN
6. fechar o restante do header ICSP: `SCK`, `RESET`, `VCC` e `GND`
7. identificar o modelo exato do transceptor CAN do verso

Sinais prioritarios do FT245RL para mapear primeiro:
- `D0..D7`
- `RXF#`
- `TXE#`
- `RD#`
- `WR#`
- `PWREN#` se estiver usado na placa
- `SI/WU` e `RESET#` apenas se houver trilha util ao AVR