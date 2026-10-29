# Bootloader FT245 Architecture

## Objetivo

Permitir atualizacao de firmware do `ATmega162` pela interface `FT245RL`, evitando uso rotineiro do `ICSP`.

O `ICSP` continua necessario para:
- gravar o bootloader pela primeira vez
- recuperar a placa se bootloader ou aplicacao ficarem corrompidos
- ajustar `fuses`

## Arquitetura proposta

```text
PC updater <-> FT245RL <-> ATmega162 bootloader
                           |
                           +-> valida pacote
                           +-> grava flash via SPM
                           +-> confirma CRC
                           +-> salta para aplicacao
```

## Reuso do protocolo principal

O bootloader deve reutilizar o mesmo enquadramento de pacotes do firmware principal:
- `SYNC = 0x5A`
- `LEN`
- `CMD`
- `PAYLOAD`
- `CHECKSUM XOR`

Isso reduz risco e simplifica a ferramenta do PC.

## Comandos sugeridos do bootloader

- `0x70` `BL_GET_INFO`
- `0x71` `BL_ERASE_APP`
- `0x72` `BL_WRITE_PAGE`
- `0x73` `BL_READ_PAGE`
- `0x74` `BL_VERIFY_CRC`
- `0x75` `BL_JUMP_APP`

## Estrategia de entrada no bootloader

Opcoes seguras:
- timeout curto apos reset aguardando `BL_GET_INFO`
- flag em EEPROM ou RAM preservada por watchdog reset
- comando explicito do firmware principal seguido de reset

## Como saber se o AVR ja tem bootloader

Sem dessoldar nada, ha tres formas praticas:

1. Ler os `fuses` por `ICSP`.
Se `BOOTRST` estiver programado para iniciar pela boot section e o tamanho da boot section estiver reservado, existe chance real de bootloader presente.

2. Ler a flash inteira por `ICSP` e inspecionar a regiao de boot.
Se a secao final da flash nao estiver vazia (`0xFF`) e contiver codigo consistente, ha bootloader gravado.

3. Observar comportamento apos reset pela FT245RL.
Se a placa responde imediatamente com algum protocolo proprio antes da aplicacao principal, isso e sinal forte de bootloader ativo.

## Metodo recomendado de verificacao

1. Ler `lfuse`, `hfuse` e `efuse` com `avrdude`.
2. Ler o dump completo da flash.
3. Verificar se a regiao de boot esta reservada e contem codigo.

Exemplo de comandos, com a placa ligada via `ICSP`:

```powershell
avrdude -p m162 -c arduino -P COM5 -b 19200 -U hfuse:r:-:h -U lfuse:r:-:h -U efuse:r:-:h
avrdude -p m162 -c arduino -P COM5 -b 19200 -U flash:r:build\atmega162_dump.hex:i
```

## Criterio pratico

Se a secao de boot estiver vazia ou os `fuses` nao apontarem para boot reset, trate a placa como sem bootloader.

## Riscos

- bootloader mal escrito pode bloquear atualizacao pela FT245RL
- falta de checksum/CRC pode corromper a aplicacao
- queda de energia durante gravacao pode deixar apenas o bootloader funcional