# Hardware Inspection

## Estado confirmado ate agora

Inspecao visual e confirmacoes manuais consolidadas a partir das fotos da interface em bancada.

Componentes visiveis com boa confianca:
- ATmega162 em TQFP como MCU principal
- FTDI FT245RL em SSOP ligado ao barramento USB
- SJA1000T no encapsulamento longo da face frontal
- L9637D no verso como interface K-Line
- TJA1040C no verso como transceptor CAN
- conector OBD integrado na borda superior
- header de 4 pinos na borda inferior da PCB
- cristal de 16 MHz para o ATmega162 (confirmado: `F_CPU=16000000UL`; o bootloader so responde a 500000 baud porque ja foi compilado para 16 MHz). A nota anterior que dizia 8 MHz estava errada e explicava o "ruido" na K-Line: com `F_CPU=8000000` num cristal de 16 MHz, `10400` saia como **20833 bps reais** (erro de 100%)

Ligacoes ja confirmadas:
- header inferior e um conector ICSP
- o ICSP chega pelo menos em `MISO` e `MOSI` do ATmega162
- `FT245RL.D0 -> ATmega162.PB0`
- `FT245RL.D1 -> ATmega162.PB1`
- `FT245RL.D2 -> ATmega162.PB2`
- `FT245RL.D3 -> ATmega162.PB3`
- `FT245RL.D4 -> ATmega162.PB4`
- `FT245RL.D5 -> ATmega162.PB5`
- `FT245RL.D6 -> ATmega162.PB6`
- `FT245RL.D7 -> ATmega162.PB7`
- `FT245RL.RXF# -> ATmega162.PE0`
- `FT245RL.TXE# -> ATmega162.PD5`
- `FT245RL.WR# -> ATmega162.PD4`
- `FT245RL.RD# -> ATmega162.PD3`
- `SJA1000T.AD0 -> ATmega162.PA0`
- `SJA1000T.AD1 -> ATmega162.PA1`
- `SJA1000T.AD2 -> ATmega162.PA2`
- `SJA1000T.AD3 -> ATmega162.PA3`
- `SJA1000T.AD4 -> ATmega162.PA4`
- `SJA1000T.AD5 -> ATmega162.PA5`
- `SJA1000T.AD6 -> ATmega162.PA6`
- `SJA1000T.AD7 -> ATmega162.PA7`
- `SJA1000T.ALE/AS -> ATmega162.PE1`
- `SJA1000T.CS# -> ATmega162.PC7`
- `SJA1000T.RD# -> ATmega162.PD7`
- `SJA1000T.WR# -> ATmega162.PD6`
- `SJA1000T.INT# -> ATmega162.PD2`
- `SJA1000T.RESET# -> ATmega162.PE2`
- `SJA1000T.TX0 -> TJA1040C.TxD`
- `SJA1000T.RX0 -> TJA1040C.RxD`
- `L9637D.TX -> ATmega162.PD1`
- `L9637D.RX -> ATmega162.PD0`

Itens ainda nao fechados:
- linhas restantes do ICSP: `SCK`, `RESET`, `VCC` e `GND`
- mapeamento conector OBD <-> K-Line/CAN

## O que esta foto muda no firmware

1. Mantem a estrategia de usar o ATmega162 como centro do firmware.
2. Reforca que a camada USB deve ser modelada como FTDI paralelo/FIFO, nao como UART simples.
3. Confirma que o barramento CAN passa por um SJA1000T e por um transceptor dedicado, entao a camada CAN deve continuar separada em controlador e PHY.
4. Confirma que a K-Line usa L9637D, o que combina com a estrategia atual do firmware.
5. Justifica manter `BOARD_HAS_FT245=0` ate o mapa real de sinais ser fechado por continuidade.

## FT245RL confirmado

A segunda foto fechou a identificacao do CI USB como `FT245RL`.

Isso confirma de vez que o lado PC deve ser tratado como FIFO paralelo de 8 bits com handshake, usando principalmente:
- `D0..D7`
- `RXF#`
- `TXE#`
- `RD#`
- `WR#`

Sinais secundarios que podem ou nao estar conectados ao AVR:
- `PWREN#`
- `SI/WU`
- `RESET#`

Observacao de bancada:
- `PWREN#` parece seguir para um resistor puxado a `VCC`; se isso se confirmar, ele nao precisa entrar no firmware da primeira fase

Implicacao pratica para o firmware:
- a base atual de `usb_fifo.c` continua na direcao correta
- ainda nao devemos habilitar `BOARD_HAS_FT245` sem continuidade real entre FT245RL e ATmega162

## Dados para diagrama futuro

Blocos ja confirmados para um diagrama funcional:
- `USB <-> FT245RL <-> ATmega162`
- `ATmega162 <-> SJA1000T <-> TJA1040C <-> CANH/CANL`
- `ATmega162 <-> L9637D <-> K-Line`
- `ICSP <-> ATmega162`
- `cristal 16 MHz <-> ATmega162`

Sinais ja confirmados parcialmente para o diagrama:
- `ICSP.MISO -> ATmega162.MISO`
- `ICSP.MOSI -> ATmega162.MOSI`

Sinais ainda pendentes para completar o diagrama:
- `ICSP.SCK`
- `ICSP.RESET`
- `ICSP.VCC`
- `ICSP.GND`
- saidas `L9637D <-> conector OBD`
- saidas `TJA1040C <-> conector OBD`

## Proxima rodada de coleta

Fotos uteis:
- verso completo da placa
- close do CI FTDI
- close do CI longo do lado esquerdo
- close da area do header inferior

Medidas uteis:
- continuidade do header inferior para o ATmega162
- continuidade dos pinos do FTDI para as portas do AVR
- continuidade do conector OBD para os CIs de interface