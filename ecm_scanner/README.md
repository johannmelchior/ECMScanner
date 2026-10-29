# ECM Scanner

Este diretório contém o aplicativo principal de diagnóstico CAN.

## Arquivos
- `main.py`: interface principal e lógica do scanner.
- `brp_dtc_codes.json`: base de dados dos códigos de falha BRP (genérica, sem modelo).
- `brp_dtc_by_model.json`: base de DTCs BRP **por modelo** (gerada a partir das sessões BUDS2).
- `sessions_decrypted/`: sessões `.buds2` já decifradas (entrada do gerador).
- `tools/build_brp_dtc_by_model.py`: gera `brp_dtc_by_model.json`.
- `yamaha_dtc_codes.json`: base de dados dos códigos de falha Yamaha.
- `yds_protocol.py`: elo série Yamaha reconstruído do `YDS.exe` (9600, wake 0x1C, handshake).
- `test_yds_protocol.py`: testes do elo YDS contra um transporte falso (`python -m unittest test_yds_protocol -v`).
- `brp_modules_from_edb.json`: mapeamento de módulos BRP (request/response IDs) extraído do EDB/ODX.
- `brp_packet_semantics_from_edb.json`: semântica diagnóstica de rede (módulo, pares request/response, modo extended e perfil funcional) extraída do EDB.
- `requirements.txt`: dependências Python do scanner.

## Como executar
No PowerShell:

```powershell
cd c:\Users\johan\Documents\projetoCAN\python-code\ecm_scanner
pip install -r requirements.txt
python main.py
```

## DTC por modelo (BRP)

O BUDS2 guarda, em cada sessão `.buds2`, os DTCs de **um** modelo de veículo, por
ECU (`<devices deviceName="ECM" ecuVariantName="EV_...">`). O gerador converte
essas sessões numa base com dimensão de modelo:

```powershell
cd Z:\projetoCAN\ecm_scanner
..\.venv\Scripts\python.exe tools\build_brp_dtc_by_model.py --xml-dir sessions_decrypted
```

Resultado atual: **39 modelos**, **976 entradas DTC** (967 com descrição), contra
apenas 60 códigos na base genérica — 542 códigos passam a ter descrição.

### Como o modelo é escolhido em runtime

1. **VIN (mais fiável).** O botão "LER VIN" pede `22 F1 90` ao ECM; a resposta
   `62 F1 90 …` é guardada e procurada em `vin_index` pelo prefixo mais longo.
   Um VIN conhecido manda sobre qualquer outra inferência.
2. **Módulos + códigos.** Se o VIN não estiver na base, acumulam-se os módulos que
   responderam (mesmo sem DTCs) e os códigos lidos; `resolve_brp_model()` pontua
   cada modelo com 60 % cobertura dos módulos + 40 % precisão, e metade do peso
   vai para a fração de códigos conhecidos.
3. Só se troca de modelo quando há **um** candidato (empate mantém a tabela
   genérica e mostra os candidatos na barra de estado).
4. O seletor "Auto (por ECU)" permite forçar manualmente um modelo.

> `vin_index` contém **apenas** VINs de sessões cujo nome é o modelo (ficheiros
> demo). VINs de sessões reais associadas por heurística ficam em `observed_vins`
> e **não** são indexados, para não propagar associações erradas.

### Regenerar a partir de `.buds2` por decifrar

O modo `--buds2-dir` decifra as sessões (requer `pycryptodome`):

```powershell
..\.venv\Scripts\python.exe tools\build_brp_dtc_by_model.py `
    --buds2-dir "C:\Program Files (x86)\BRP\BUDS2\Files" `
    --keys-file buds2_keys.json
```

`buds2_keys.json` é uma lista com uma palavra-passe candidata por linha (as chaves
saem da licença local do BUDS2; ver o README do módulo `rea` na sessão).

### DTC Yamaha — códigos numéricos do YDS

A Yamaha **não usa códigos OBD-II**. O YDS apresenta o DTC como número decimal
(`CODE : 12`) e a tabela vem do próprio YDS:

- `yamaha_dtc_codes.json` — **73 códigos, 01 a 73**, gerado por
  `tools/extract_yds_db.py` a partir do bloco `0xA0` do `SEItem`
  (`0xA001` → `01` "Pulser coil", … `0xA049` → `73`).
- `normalize_yamaha_code()` aceita `7`, `07`, `"7"` ou `12` e devolve sempre
  duas posições (`"07"`, `"12"`); valores 1-99 são formato YDS, `P0120` é
  marcado como OBD (só modelos com CAN) e o resto fica `raw`.
- `describe_yamaha_code()` resolve o nome a partir da tabela; código fora da
  base devolve aviso para consultar o manual, nunca um P-code inventado.
- `read_yamaha_dtc()`: em K-Line envia **KWP2000 `readDTCByStatus`
  (`84 11 F1 18 00 FF 00 <cksum>`)** e usa `parse_yamaha_kwp_dtc()`; em CAN
  mantém OBD Mode 03 + UDS 19.
- `parse_yamaha_kwp_dtc()` aceita os dois arranjos que o ECM pode devolver
  (`DTC_H,DTC_L,status` ou `DTC_L,status`) e guarda o byte de status e o valor
  bruto para diagnóstico.

O bloco `0xC0` do `SEItem` (21 itens) **não** é DTC: a partir do 12 são funções
de controlo (`Tacho pulse stop control`, `Over-rev control`, `Buzzer control`).

### Como o YDS abre e mantém a sessão

O `YDS.exe` foi descompilado com Ghidra 12.1.4 — ver
[`docs/YDS_Protocol_Decompiled.md`](../docs/YDS_Protocol_Decompiled.md). O
resultado substitui a hipótese anterior, que vinha de uma captura feita a
**10400 baud** (baud errado ⇔ os bytes lidos eram ruído, incluindo os 36 % de
`0xFE` e as "pausas de 2–6 ms").

O YDS **não** fala KWP2000 no elo PC↔equipamento. Fala um protocolo orientado a
byte, **9600 8N1**, onde cada byte enviado é devolvido em eco antes da resposta:

1. **Abertura:** `COM%d` a **300 baud** → `PurgeComm` → envia **`0x1C`** →
   fecha → reabre a **9600** (`FUN_004798f0`).
2. **Handshake:** `FD E5 E5 FE FF FE FF`. A resposta a `0xE5` tem de ser `0xEF`
   (variante A) ou `0xED` (variante B); `0xFE` e `0xFF` são enviados duas vezes
   e as respostas têm de repetir.
3. **Endereço do módulo:** escada `F0 EF EE ED EC E4 E3 E2 E1 E0`, parando no
   primeiro que responde (`FUN_0047a120`).
4. **Troca de byte:** `PurgeComm` → escreve 1 byte → lê o eco (tem de ser igual)
   → lê 1 byte de resposta. **110 ms** por byte, **3 tentativas**
   (`FUN_00479570` / `FUN_0046efc0` / `FUN_0046eeb0`).
5. **Não existe `TesterPresent`.** Manter a sessão viva é continuar a trocar
   bytes de identidade (`0xFE`).

Não existe `10400` (`0x28A0`) nem `15625` (`0x3D09`) em nenhum ponto do binário:
a única constante de baud na zona de comunicação é `0x2580` = 9600.

Por isso a app passou a:

- usar **`9600 - Yamaha`** por omissão no combo K-Line;
- fazer a abertura no estilo YDS quando a caixa **`Yamaha YDS link`** está
  marcada (`yds_protocol.YdsByteLink`), registando cada troca no console;
- enviar os pedidos Yamaha como sequência de trocas de 1 byte
  (`_yamaha_tx_request`), que é o único primitivo que o YDS usa;
- oferecer **`Poll keep-alive`**, que no link YDS repete `0xFE` em vez do
  `21 01` KWP;
- recusar o keepalive KWP (`TesterPresent`) quando o link YDS está activo.

> Limite: os comandos byte-a-byte de DTC e de actuação estão dentro da máquina
> de estados `FUN_00470250` (32 623 bytes) e ainda não foram mapeados. Até lá o
> link abre e sincroniza correctamente, e todos os bytes ficam no console.


## Yamaha — actuadores (testes activos)

Separador **ATUADOR** na aba Yamaha, alimentado pelo bloco `0x90` do `SEItem`:
**62 actuadores** com o nome do próprio YDS (`Spark ignition coil #1`,
`Operate injector #1`, `Drop cylinder #1`, `YPVS`, `Operate stepping motor`, …).

Cada linha envia um frame KWP2000 endereçado:

```
<fmt> 11 F1 <svc> <id> <iocp> [valor] <cksum>
```

- `fmt` = `0x80 | len(payload)` — o mesmo esquema do `readDTCByStatus`
  (`84 11 F1 18 00 FF 00 <cksum>`).
- `svc` configurável: **`0x30`** (KWP `inputOutputControlByLocalIdentifier`)
  por omissão, ou `0x32`.
- `iocp`: `0x07` (assumir controlo) por omissão; `0x00` no `PARAR` devolve o
  controlo ao ECU.
- `valor` opcional (ex.: posição do ISC).

Exemplos gerados:

```
Spark ignition coil #1 on  -> 83 11 F1 30 01 07 BD
Spark ignition coil #1 off -> 83 11 F1 30 01 00 B6
Operate injector #8    on  -> 84 11 F1 30 3E 07 01 FC
```

Por segurança há **devolução automática do controlo ao ECU ao fim de 10 s**
(`yamaha_actuator_auto_off_s`), como o YDS faz — não deixa um injector ou bobina
sob controlo do tester. Todas as trocas TX/RX e NRC são escritas no log da aba.

**Limite honesto:** o serviço exacto que o YDS usa não está em claro nos dados.
O `SEByte.dbf` contém `B2 11 00 07` (0xB2 é o eco positivo de **0x32**), mas o
KWP2000 padrão para testes de actuador é **0x30**. Comece em `0x30`; se a
resposta for `7F 30 11` (serviceNotSupported) mude para `0x32`.

### Tabelas de actuação do YDS

| Ficheiro | Início | Registo | Conteúdo |
|---|---|---|---|
| `SEAct.dbf` | 88 | 6 | 13 registos `[idx, 0x09, msgInicial, nMsgs]` |
| `SEAnybit.dbf` | 88 | 6 | 10 registos `[idx, 0x05, msgInicial, 10]` |
| `SEByte.dbf` | 145 | 5 | descritores de byte |

O `SEMess` indexa por grupo no nibble alto: `0x0000` = mensagens de actuação
("Ignition coil #1 selected."), `0x1000` = pré-condições, `0x2000` = notas
("NOTE: Ignition coil is being tested…").

## Yamaha — dicionário YDS e keepalive

### Separador MONITOR

O separador **MONITOR** da aba Yamaha carrega o dicionário do YDS
(`yamaha_yds_items.json`, gerado por `tools/extract_yds_db.py`): **363
parâmetros** canónicos (`Engine speed`, `TPS voltage`, `Water temperature`, ...),
o item 117 é `Code`. A lista é preguiçosa (botão **Carregar**) para não atrasar o
arranque, tem filtro por texto e um conversor que aplica as **63 fórmulas** de
escala do YDS (ex.: `X*5/256*760*1.33/4`).

### Keepalive K-Line (sessão que caía aos ~30 s)

**No link YDS (protocolo `Yamaha` com `Yamaha YDS link` marcado) não há
`TesterPresent`**: o YDS original não o envia. Manter a sessão viva é continuar
a trocar bytes de identidade, o que a opção **`Poll keep-alive`** faz enviando
`0xFE`. Se o keepalive KWP for ligado nesse modo, a app recusa e avisa.

O texto abaixo aplica-se ao modo KWP antigo (`Yamaha YDS link` desmarcado).

A sessão KWP2000 morre no idle do ECU se o tester não enviar `TesterPresent`
dentro de P3. Três correções:

1. **Keep-Alive ligado por omissão** (antes vinha desligado, logo não havia
   keepalive nenhum).
2. **`StartCommunication` enviado como um frame atómico** (`kline_tx_frame`).
   Byte-a-byte via USB cria gaps de vários ms e o ECU aborta o fast-init.
3. **Resposta lida em bloco** (`kline_rx_bulk`). Byte-a-byte estoura o buffer de
   1 byte do AVR e perde bytes — era a origem do "ruído".

O frame de keepalive é calculado em `_yamaha_tester_present_frame()`:
`82 <ecu> F1 3E 80 <cksum>`, a cada 1500 ms, enviado pelo próprio firmware.

## Yamaha K-Line

### Logs de referencia
- `c:\Users\johan\Documents\projetoCAN\yam.txt`: captura de wakeup/inicializacao. Representa o momento em que a chave e ligada, o painel acorda a ECU e a sessao comeca.
- `c:\Users\johan\Documents\projetoCAN\yamaha funcionando.txt`: captura com o motor funcionando em lenta. Este arquivo deve ser usado para mapear canais, valores e hipoteses de RPM/telemetria.

### Procedimento de inicializacao observado em `yam.txt`
Analise atual baseada nos scripts `analyze_kline.py`, `decode_kline.py`, `kline_baudrate_scan.py` e `kline_center_sample.py`:

1. A ECU aparenta entrar em estado ativo por volta de `698.5 ms`.
2. A linha permanece em `HIGH` por aproximadamente `47.4 ms`.
3. Em seguida aparece um wakeup temporal forte com tres janelas longas:
	- `LOW` por aproximadamente `95.5 ms`
	- `HIGH` por aproximadamente `95.5 ms`
	- `LOW` por aproximadamente `95.5 ms`
4. Depois do wakeup longo, surge uma janela curta em `HIGH` de aproximadamente `7.8 ms`.
5. A partir de cerca de `1040.2 ms`, comecam bursts curtos de comunicacao digital entre painel e ECU.

Resumo pratico do wakeup:

```text
HIGH 47 ms -> LOW 95 ms -> HIGH 95 ms -> LOW 95 ms -> HIGH 7.8 ms -> bursts curtos
```

### Interpretacao atual
- `yam.txt` documenta melhor o mecanismo de wakeup do painel para iniciar a ECU do que um payload UART completamente confiavel.
- Os bursts seguintes mostram que existe trafego digital real logo apos o wakeup, mas os bytes ainda nao estao perfeitamente enquadrados o suficiente para afirmar o comando exato com confianca total.
- `yamaha funcionando.txt` e o log correto para estudar o protocolo em regime estavel, porque mostra o motor em lenta e trafego repetitivo de operacao.

### Scripts uteis
- `c:\Users\johan\Documents\projetoCAN\python-code\analyze_kline.py`: localizar wakeup, listar transicoes e comparar 10400/16040 baud.
- `c:\Users\johan\Documents\projetoCAN\python-code\decode_kline.py`: filtrar ruido/ringing e achar o inicio do trafego apos wakeup.
- `c:\Users\johan\Documents\projetoCAN\python-code\kline_baudrate_scan.py`: estimar baud e inspecionar o padrao de wakeup.
- `c:\Users\johan\Documents\projetoCAN\python-code\kline_center_sample.py`: validar enquadramento por amostragem no centro do bit.
- `c:\Users\johan\Documents\projetoCAN\python-code\kline_waverunner_analysis.py`: analisar o log com o motor em lenta e tentar extrair canais/valores.

## Ferramenta PC para a interface AVR

O firmware AVR agora expoe um protocolo binario enquadrado pela interface `FT245RL`. Para falar com ele do lado do PC sem alterar o `main.py` atual, foi adicionada uma ferramenta dedicada neste diretorio:

- `avr_interface.py`: biblioteca Python para o protocolo AVR enquadrado
- `avr_cli.py`: cliente de linha de comando para testes de bancada

Essa ferramenta reutiliza o mesmo `pyserial` ja presente no projeto e agora usa `1000000 baud` por padrao no backend AVR de aplicacao.

Observacao:
- o bootloader FT245 continua documentado e validado separadamente em `500000 baud`

### Exemplos

```powershell
cd c:\Users\johan\Documents\projetoCAN\python-code\ecm_scanner
python avr_cli.py --port COM5 info
python avr_cli.py --port COM5 set-mode kline
python avr_cli.py --port COM5 kline-set-baud 10400
python avr_cli.py --port COM5 kline-debug 120
python avr_cli.py --port COM5 kline-wait-high 30000 20
python avr_cli.py --port COM5 kline-wakeup
python avr_cli.py --port COM5 kline-tx 0xF8
python avr_cli.py --port COM5 kline-rx 200
python avr_cli.py --port COM5 set-mode can
python avr_cli.py --port COM5 can-set-bitrate 500
python avr_cli.py --port COM5 can-status
python avr_cli.py --port COM5 can-rx
```

### Estrategia de integracao

O `main.py` do scanner continua usando hoje o protocolo textual legado do ESP32/CAN. A nova dupla `avr_interface.py` + `avr_cli.py` existe para bring-up da placa AVR sem misturar protocolos incompatíveis dentro do GUI grande antes da hora.

Quando a bancada estiver estavel, o proximo passo e integrar `avr_interface.py` como backend opcional dentro do scanner.

No backend AVR do `main.py`, ao conectar em `9600 - Yamaha` com **`Yamaha YDS link`** marcado, o scanner executa a abertura do YDS: 300 baud + `0x1C`, 9600 e o handshake `FD E5 E5 FE FF FE FF`, seguido da escada de endereços `F0..E0`. Com a caixa desmarcada mantém-se o comportamento KWP anterior (classificação `baixo`/`alto`/`comunicando`, wakeup e `StartCommunication`).

Para diagnostico passivo Yamaha, o combo de K-Line tambem expoe `15625 - Yamaha` e `16040 - Yamaha`. Nesses bauds experimentais o backend AVR conecta e sniffa normalmente, mas nao dispara auto-init para nao contaminar a observacao do barramento.
