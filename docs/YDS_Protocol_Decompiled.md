# YDS.exe — Protocolo de comunicação (decompilado com Ghidra 12.1.4)

Análise **estática** de `C:\Program Files\YDS\YDS.exe` (Delphi, 4 774 400 bytes) sem
qualquer ligação ao WaveRunner. Método: importação + auto-análise no Ghidra headless,
seguida de scripts próprios que fazem dumping de strings, imediatos, chamadas e
pseudo-código C.

Artefactos gerados (fora do repositório):

| Caminho | Conteúdo |
|---|---|
| `C:\tools\ghidra_12.1.4_PUBLIC` | Ghidra 12.1.4 (`GHIDRA_INSTALL_DIR`) |
| `C:\tools\jdk-25.0.5+8` | JDK 25 (Temurin) exigido pelo Ghidra 12.x |
| `C:\tools\ghidra_proj\YDS` | projeto Ghidra com o programa analisado |
| `C:\tools\ghidra_scripts` | scripts `DumpYds`, `DumpFrom`, `CallsTo`, `CallsCtx`, `DumpPtr` |
| `C:\tools\yds_out` | 10 591 funções, 4,4 MB de C descompilado, strings/imediatos/APIs |
| `C:\tools\yds_comm2` | módulo de comunicação completo (131 funções) |
| `C:\tools\yds_ctx` | desmontagem em torno de cada chamada ao primitivo de byte |

Reproduzir:

```powershell
$env:JAVA_HOME="C:\tools\jdk-25.0.5+8"
$env:HEADLESS="1"
& "C:\tools\ghidra_12.1.4_PUBLIC\support\analyzeHeadless.bat" `
    C:\tools\ghidra_proj YDS -process "YDS.exe" -noanalysis `
    -scriptPath "C:\tools\ghidra_scripts" `
    -postScript DumpFrom.java "C:\tools\yds_comm2" 0 0046e140,0046e2a0,...
```

---

## 1. Ligação série com o equipamento

### 1.1 Abertura da porta — `FUN_0046ebe0`

```
CreateFileA("COM%d", GENERIC_READ|GENERIC_WRITE, 0, 0, OPEN_EXISTING, 0, 0)
SetCommMask(h, 0)
SetupComm(h, inQueue, 200)
COMMTIMEOUTS:
    ReadIntervalTimeout        = 0xFFFFFFFF   // leitura não bloqueante
    ReadTotalTimeoutMultiplier = 0
    ReadTotalTimeoutConstant   = 0            // devolve logo o que estiver no buffer
    WriteTotalTimeoutConstant  = 20000        // 20 s
SetCommTimeouts(h, &to)
```

O nome do dispositivo vem do formato `"COM%d"` (`s_COM_d_0059ed70`), com o número da
porta como argumento.

### 1.2 Configuração da DCB — `FUN_0046f140`

```
GetCommState(h, &dcb)
dcb.DCBlength = 28
dcb.BaudRate  = <param_2>
dcb.ByteSize  = 8
dcb.Parity    = 0            // NOPARITY
dcb.StopBits  = 0            // ONESTOPBIT
dcb.XonLim = dcb.XoffLim = 1024
dcb.Flags = (Flags & 0xFFFFDCF9) | 0x1001
SetCommState(h, &dcb)
```

`0x1001` = `fBinary` + `fRtsControl = RTS_CONTROL_ENABLE`; a máscara limpa `fParity`,
`fOutxCtsFlow`, `fOutX`, `fInX` → **sem controlo de fluxo**. DTR/RTS activos.

### 1.3 Configuração usada (todos os call sites)

| Parâmetro | Valor | Origem |
|---|---|---|
| Baud rate de trabalho | **9600** (`0x2580`) | `FUN_004798f0`, `FUN_0048b760`, `FUN_0048b880` |
| Baud rate de wake-up | **300** (`0x12C`) | `FUN_004798f0` |
| Formato | 8-N-1 | `FUN_0046f140` |
| Timeout por byte | **110 ms** (`0x6E`) | `PUSH 0x6e` antes de cada troca de byte |
| Buffer de entrada | 1024 (`0x400`) | `SetupComm` |
| Tentativas por byte | **3** | `FUN_00479570` |

> Não existe **nenhum** `10400` (`0x28A0`) nem `15625` (`0x3D09`) no binário inteiro.
> A única constante de baud na zona de comunicação é `0x2580` = 9600.

---

## 2. Primitivo de troca de byte — `FUN_00479570`

Assinatura real (convenção Delphi *register*): `(self, byte, timeout)`.

```
para tentativa in 1..3:
    se PurgeComm(h) != 0: devolve 1
    se WriteFile(h, &byte, 1) == 0: devolve 1
    eco = ler_byte(110 ms)                  // DEVE ser igual ao byte enviado
    se erro ou eco != byte: devolve 2
    resp = ler_byte(110 ms)
    se erro: devolve 2
    self+0x58 = resp        // resposta de 1 byte
    self+0x54 = resp
    devolve 0
```

`ler_byte` = `FUN_0046efc0`: espera em `ClearCommError` até haver 1 byte no buffer ou
expirar o timeout, devolvendo **0** em caso de timeout.

**O equipamento faz eco de cada byte enviado.** O protocolo é estritamente
**1 byte enviado -> 1 byte de eco -> 1 byte de resposta**.

`FUN_00479730` é idêntico mas com **1 única tentativa**.

---

## 3. Sequência de abertura / handshake — `FUN_004798f0`

```
abrir COM1 @ 300 baud   (fallback: COM2 @ 300)
PurgeComm
enviar 0x1C                       // pulso de wake-up a 300 baud
PurgeComm
fechar
reabrir COMn @ 9600 baud

trocar(0xFD)                      // se falhar: repetir 300/0x1C/9600 em COM2
trocar(0xE5) -> resposta DEVE ser 0xEF ou 0xED
trocar(0xE5) -> resposta DEVE ser 0xEF ou 0xED
trocar(0xFE) -> guardar r1
trocar(0xFF) -> guardar r2
trocar(0xFE) -> DEVE ser igual a r1
trocar(0xFF) -> DEVE ser igual a r2
```

* `0xE5 -> 0xEF` => `self+0x4C = 0` (variante A)
* `0xE5 -> 0xED` => `self+0x4C = 1` (variante B)
* outra resposta => falha `return 3`
* `0xFE`/`0xFF` cujas respostas não repetem => falha `return 4`

Ou seja: **YDS envia `0x1C` a 300 baud, reabre a 9600 e depois faz uma troca de 7 bytes
com verificação de eco e de repetibilidade.** Não há keep-alive de 30 s — a ligação é
aberta, sincronizada e mantida pelo polling da máquina de estados.

### 3.1 Escada de endereçamento — `FUN_0047a120`

YDS procura o endereço do módulo enviando, por ordem:

```
0xF0, 0xEF, 0xEE, 0xED, 0xEC, 0xE4, 0xE3, 0xE2, 0xE1, 0xE0
```

e pára no primeiro cujo eco + resposta forem válidos; o byte de resposta fica em
`self+0x58`.

---

## 4. Variante "texto" (`self+0x5C == 10`)

Quando a porta resolvida é 10, o mesmo objecto de comunicação usa um protocolo ASCII
por linhas (usado pelo `YDISDevice0`, ver `FUN_0047a2c0`):

| Envio | Resposta | Função |
|---|---|---|
| `\fAS\r\n` (`0C 41 53 0D 0A`) | `AAS\r\n` | `FUN_0047af10` — estado |
| `\fAT01000001\r\n` | `AAT\r\n` | `FUN_0047ab60` — transmissão |
| `\fEC<hh>\r\n` (`hh` = byte em hex) | `AEC<hh>\r\n` | `FUN_0047ad30` — leitura de um byte |

Leitura de linha: `FUN_0047a720` acumula até `'R' ... '\n'` (resposta) ou `'D'` (dados),
com timeout de 10 000 ms e buffer de 0x438 bytes.

---

## 5. Máquina de estados principal — `FUN_00470250` (32 623 bytes)

É o condutor central da sessão de diagnóstico. Objecto de comunicação em `[ESI+0xAF0]`.
Contém 44 chamadas à troca de byte e conduz tudo byte a byte, incluindo a escada
`0xF0/0xEF/...`, comandos `0xFD`, `0xFC`, `0xFB`, `0x07`, `0x06`, `0x0D`, `0x39`, etc.

---

## 6. Consequências para o `ecm_scanner`

| Ponto | Antes | Correto (YDS) |
|---|---|---|
| Baud Yamaha | `10400` por omissão | **9600** |
| Wake-up | opcional, `Init KWP 81 11 F1 3E` | **`0x1C` a 300 baud**, depois reabrir a 9600 |
| Handshake | nenhum | `FD E5 E5 FE FF FE FF` com eco verificado |
| Nível de protocolo | tramas KWP2000 com comprimento + checksum | **byte a byte com eco**, sem cabeçalho nem checksum |
| Timeout | 40 ms de gap / poll `21 01` | **110 ms por byte**, 3 tentativas, `PurgeComm` antes de cada |

A conclusão anterior ("o ECM transmite continuamente, não é preciso init") foi tirada de
uma captura feita a **10400 baud**; com o baud errado os bytes lidos são ruído e as
"pausas de 2-6 ms" não correspondem a tramas reais.

---

## 7. Limites desta análise

* O protocolo **entre a caixa de interface Yamaha e a ECU** (lado K-Line) não está no
  `YDS.exe`: a aplicação fala com a caixa. O que aqui está provado é o elo
  **PC <-> caixa**.
* `SESpec.dll` (59 904 bytes, `InstImage\DB\Comm\`) foi analisado: exporta apenas
  `GetSpecialFuncVal` e limita-se a preencher uma tabela de valores especiais — não
  contém lógica de protocolo.
* Nenhuma evidência de keep-alive periódico: o único `SetTimer` na zona de comunicação
  (`FUN_0047ba40`) usa 100 ms mas serve para redesenho de UI.
