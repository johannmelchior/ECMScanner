# Hardware Diagram Notes

## Componentes confirmados

- MCU principal: `ATmega162`
- Interface USB/FIFO: `FT245RL`
- Controlador CAN: `SJA1000T`
- Interface K-Line: `L9637D`
- PHY CAN: `TJA1040C`
- Clock do MCU: cristal `16 MHz` (`F_CPU=16000000UL`). A nota anterior que indicava 8 MHz estava errada: com `F_CPU=8000000` num cristal de 16 MHz todos os bauds K-Line saiam a 2x (`10400` → 20833 reais), o que produzia ruido total no barramento
- Header inferior: `ICSP`

## Ligacoes confirmadas

- `ICSP -> ATmega162.MISO`
- `ICSP -> ATmega162.MOSI`
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

## Ligacoes presumidas pela arquitetura

- `USB host -> FT245RL`
- `FT245RL <-> ATmega162`
- `ATmega162 <-> SJA1000T`
- `SJA1000T <-> TJA1040C`
- `TJA1040C <-> conector OBD`
- `ATmega162 <-> L9637D`
- `L9637D <-> conector OBD`

## Pendencias para fechar o diagrama eletrico/funcional

- mapear eventual enable do `L9637D`, se houver
- fechar `ICSP.SCK`, `RESET`, `VCC` e `GND`
- fechar quais pinos do OBD sao `K-Line`, `CANH` e `CANL`

## Observacao sobre o barramento FT245RL

As confirmacoes atuais fecham o barramento de dados inteiro:
- `D0..D7 -> PB0..PB7`

Isso confirma que o barramento de dados do FT245RL esta ligado bit a bit na `PORTB` do ATmega162.

Implicacao para firmware:
- a leitura e escrita do barramento podem ser feitas diretamente por `PINB` e `PORTB`
- os sinais de controle confirmados atualmente ficam em `PD3`, `PD4`, `PD5` e `PE0`
- o FT245RL nao expoe `OE#`; a leitura deve ser controlada por `RD#` em conjunto com `RXF#`

## Esboco funcional

```text
USB <-> FT245RL <-> ATmega162 <-> L9637D <-> K-Line / OBD
                    |
                    +-> SJA1000T <-> TJA1040C <-> CAN / OBD
                    |
                    +-> ICSP
                    |
                    +-> Crystal 16 MHz
```