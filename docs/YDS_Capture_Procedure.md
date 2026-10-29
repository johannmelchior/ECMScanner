# Captura do tráfego YDS (com0com + serial_bridge)

O que falta saber não está no `YDS.exe`: os **comandos byte-a-byte** de DTC,
actuação e monitor vivem dentro da máquina de estados `FUN_00470250`
(32 623 bytes) e não foram mapeados. A interface Yamaha é selada, mas o elo
**PC ↔ interface** pode ser escutado com um par virtual.

## Comandos já extraídos estaticamente

Todos os 177 call sites de `FUN_00479570` foram analisados com
`CallByteArgs.java`. Destes, 27 passam o byte como **imediato directo**
(`PUSH <byte>` imediatamente antes da chamada), o que é fiável:

| Byte | Função chamadora | Ecrã provável |
|---|---|---|
| `0xFD` `0xE5` `0xFE` `0xFF` | `FUN_004798f0` | abertura / handshake |
| `0x07` `0x0D` `0x0E` | `FUN_00470250` | máquina de estados de diagnóstico |
| `0xF1` | `FUN_00483800`, `FUN_00488370`, `FUN_00499060`, `FUN_0049c840` | 4 ecrãs distintos |
| `0xFB` | `FUN_0040ad80`, `FUN_0040e5a0` | |
| `0xFC` | `FUN_0040aac0`, `FUN_0040aa50`, `FUN_0040e420` | |
| `0xA0` `0xA2` `0xA3` `0xA4` | `FUN_0044b890`, `FUN_0044bad0`, `FUN_0044bb00`, `FUN_0044bb80` | |
| `0x00` | `FUN_0042c520` | |

Os restantes 150 call sites recebem o byte de um registador (40 deles com valor
dinâmico, calculado em runtime). É precisamente aí que a captura é necessária:
só vendo o byte no fio se sabe o que cada ecrã envia.

## O que as capturas de 22/05 já provaram

Doze ficheiros `C:\Temp\yds_bridge_*.txt` (e dois `.pcapng`) foram analisados com
`yds_capture_decode.py`. Em **todas** elas o YDS só transmitiu:

| Byte | Ocorrências | Significado |
|---|---|---|
| `0x1C` | 31 | wake-up a 300 baud |
| `0xFD` | 83 | primeiro byte do handshake |
| `0xF1` | 6 | comando real (ver tabela abaixo), 3 tentativas sem resposta |

E a sequência real, numa das capturas (`yds_bridge_20260522_181552.txt`):

```
t=46.641  0x1C          <- wake-up
t=47.000  0xFD          <- tentativa 1
t=47.094  0xFD          <- tentativa 2
t=47.203  0xFD          <- tentativa 3
t=50.781  0x1C          <- YDS reabre e repete tudo
...       (3 ciclos de ~4 s)
```

Isto **confirma** o descompilado: `1C` primeiro, `FD` com **3 tentativas**
(`FUN_00479570`), e o YDS a voltar a abrir quando não há resposta.

Nenhuma resposta foi obtida porque o bridge corria a **1 000 000 baud** numa
linha de **9600** — os 8 523 bytes de RX são ruído de amostragem.

## Pré-requisitos

| Item | Estado |
|---|---|
| Driver com0com | instalado (`C:\com0com`, `com0com.sys`) |
| Par virtual criado | **não existe nenhum** — é preciso criar |
| `serial_bridge.py` | actualizado com modo `--yds` |
| `yds_capture_decode.py` | novo, descodifica o log |

## Alternativa sem hardware — emular a caixa

Se a interface não estiver disponível, `yds_box_emulator.py` faz o papel dela.
As respostas do handshake são conhecidas do descompilado, por isso o YDS
completa a abertura e passa a enviar os comandos dos ecrãs — que é o que
queremos.

```powershell
# com o par COM1/COM2 criado, YDS abre COM1:
python yds_box_emulator.py --port COM2 --log C:\Temp\yds_emu
```

Depois abrir o YDS, entrar em Diagnostic / Actuation / Monitor e navegar.
No fim (Ctrl+C) o emulador imprime os bytes novos que o YDS enviou — esses são
os candidatos a comando de DTC e de actuação.

Opções úteis:

```powershell
--variant b          # 0xE5 responde 0xED em vez de 0xEF
--no-echo            # transporte sem eco
--set 21=61          # resposta fixa para um byte (hex)
--default-response 00
```

O log sai no mesmo formato do bridge e é lido pelo mesmo descodificador.

> Limite: o emulador garante a abertura e a captura dos pedidos, mas não
> produz dados reais de monitor. O YDS vai mostrar valores vazios/erro depois
> do handshake — o que interessa é o que ele **envia**.

## Diagnóstico quando nada responde

O `main.py` agora amostra a K-Line **antes e depois** do wake-up e traduz a
falha. Três desfechos possíveis:

| Observação | Significado | Onde está o problema |
|---|---|---|
| eco presente (o byte enviado volta) | AVR, nível eléctrico e caminho de regresso OK | no veículo: alimentação, ignição ou pino errado |
| sem eco, `edges=0`, `rx=0` | o AVR não vê a linha | fio RX, massa ou nível eléctrico (K-Line em repouso fica a ~12 V) |
| sem eco, mas `edges>0` | há tráfego a outro baud | baud do modelo (tentar 10400, 15625) |

O `K-Line Sniff (passivo)` passou a avisar a cada 2 s quando não vê **um único
byte**, em vez de parecer que está a correr normalmente.

### Cuidado com o eco do próprio AVR

Os bytes `1C`/`FD` que aparecem no CSV do sniff são as **nossas** transmissões
lidas de volta pelo RX. Isso pode significar duas coisas muito diferentes:

- a interface tem transceiver e devolve o que enviamos (normal em K-Line), ou
- o RX está a captar o TX internamente e o fio externo está aberto.

Para distinguir, o teste decisivo é o **eco com a ignição desligada e o fio RX
desligado do veículo**: se continuar a haver eco, a captação é interna.

## Passo 1 — criar o par virtual (precisa de Administrador)

O YDS abre primeiro **COM1** e depois **COM2** (`FUN_004798f0`), por isso o par
deve usar esses números. Num PowerShell **como Administrador**:

```powershell
& "C:\com0com\setupc.exe" install PortName=COM1 PortName=COM2
& "C:\com0com\setupc.exe" list
```

Se `COM1`/`COM2` estiverem reservados, usar números baixos livres
(`install PortName=COM3 PortName=COM4`) e confirmar em `list`.

Alternativa com interface gráfica: `C:\com0com\setupg.exe`.

> O YDS abre **COM1**; o bridge fica com **COM2** e liga ao equipamento real.

## Passo 2 — identificar a porta do equipamento Yamaha

Ligar a interface USB e ver que porta aparece:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
Get-PnpDevice -Class Ports | Select-Object FriendlyName,Status
```

Se o equipamento cair num número baixo (por ex. `COM4`), mudá-lo para `COM20`
no Gestor de Dispositivos, para o YDS nunca o abrir directamente e saltar a
captura.

## Passo 3 — arrancar o bridge

```powershell
cd Z:\projetoCAN
python serial_bridge.py --yds --virtual COM2 --physical COM4 --log C:\Temp\yds_yds
```

O `--yds` faz:

- porta física a **9600** (a única constante de baud do `YDS.exe`);
- **sem** echo-cancel e **sem** keepalive — queremos ver o tráfego como ele é;
- o byte `0x1C` sai a **300 baud** e o resto a 9600, porque o com0com não
  transporta a mudança de DCB que o YDS faz (`FUN_004798f0`).

## Passo 4 — operar o YDS

Com a ignição ligada, no YDS:

1. abrir a ligação ao modelo;
2. entrar em **Diagnostic** (leitura de DTC) e sair;
3. entrar em **Actuation** e accionar dois ou três actuadores;
4. entrar no **Monitor** e deixar correr uns segundos.

Cada ecrã novo acrescenta comandos byte-a-byte ao log.

## Passo 5 — descodificar

```powershell
python yds_capture_decode.py C:\Temp\yds_yds_<data>_<hora>.txt
```

A saída mostra, por troca: instante, byte enviado, eco, resposta, bytes extra e
a posição na sequência (wake-up, handshake, escada). No fim dá um veredicto
contra o protocolo descompilado.

## O que se espera ver

```
[ok] O equipamento devolve o eco do byte enviado -> protocolo YDS confirmado.

Wake-up 0x1C: 1 envio(s); resposta sim
   0xFD -> 0x00
   0xE5 -> 0xEF     (variante A)  ou  0xED  (variante B)
   0xFE -> 0xNN     repetido igual
   0xFF -> 0xMM     repetido igual
escada: primeiro endereco com resposta = 0xF0 -> 0xAA
```

Depois do handshake, cada byte novo que o YDS enviar ao mudar de ecrã é um
comando de DTC, actuação ou monitor — é isso que vai para `yds_protocol.py` e
para o separador correspondente do `ecm_scanner`.

## Se o handshake falhar

| Sintoma | Causa provável |
|---|---|
| `0xFD` sem resposta e sem eco | porta física errada, ou equipamento não alimentado |
| eco presente mas resposta nunca | baud do bridge ≠ 9600 |
| `0xE5` com resposta diferente de `0xEF`/`0xED` | modelo com variante nova — registar o valor |
| handshake passa e depois tudo vazio | ecrã do YDS não gera tráfego; repetir o passo 4 |
