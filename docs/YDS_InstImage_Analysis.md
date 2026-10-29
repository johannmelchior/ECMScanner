# YDS InstImage — análise

`C:\Program Files\YDS\InstImage` é a **imagem do instalador** do YDS (Yamaha
Diagnostic System, Mitsubishi Electric). Contém o payload comprimido e uma copia
ja descompactada da base de dados de diagnostico.

## Inventario

| Item | Bytes | Conteudo |
|---|---|---|
| `data1.cab` | 536 141 | payload InstallShield (cifrado) |
| `data2.cab` | 2 099 214 | payload InstallShield (cifrado) |
| `data1.hdr` | 14 329 | cabecalho do instalador |
| `setup.inx` | 143 187 | script do instalador |
| `ikernel.ex_` | 346 602 | kernel do InstallShield |
| `layout.bin` | 417 | layout da instalacao |
| `Setup.exe` / `Setup.ini` | 56 320 / 159 | bootstrap |
| `DB\Comm\*.dbf` | 13 ficheiros | tabelas de diagnostico (texto) |
| `DB\Sys\SE*.dbf` | 28 ficheiros | mapas por sistema/ECU |
| `DB\YDIS.Msg` | 18 603 | textos da interface (INI) |
| `DB\YDSINFO.CFG` | 96 | versao da base |
| `Driver\ISO_adap.*` | 26 KB | driver da interface ISO |

## Versao da base

`DB\YDSINFO.CFG`:

```ini
[DATABASE]
VER=1.87.0.0
YAMAHA= 60V8533006
MELCO=F007T90881
TRIAL=F-9302-138
DSPVER= 1.33
```

Os ficheiros individuais trazem o seu proprio part number/data/versao no
cabecalho, e **nao estao todos na mesma versao** (ex.: `SEItem` 1.73.0.0 de
2006-12-09, `SEConv` 1.83.0.0 de 2009-05-13). A versao 1.87.0.0 e a do pacote.

## Os `.dbf` nao sao dBase

Nao tem o formato xBase. Cada ficheiro tem:

1. Um cabecalho ASCII com nome, part number, data, versao e descricao
   (`"Item File"`, `"System File"`, `"Message File"`, ...).
2. Registos de **tamanho fixo** sem separadores.
3. Texto codificado em ASCII com o **bit 7 ligado** (`0xC5` = `E`, `0xA0` =
   espaco, `0xD9 0xC5 0xD3` = `YES`).

Layouts confirmados:

| Ficheiro | Descricao | Inicio | Registo | Texto | Registos |
|---|---|---|---|---|---|
| `SEItem.dbf` | Item File | 100 | 32 | 30 | 363 |
| `SEConv.dbf` | conversoes | 100 | 32 | 30 | 63 |
| `SEUnit.dbf` | unidades | 100 | 12 | 10 | 21 |
| `SEMess.dbf` | mensagens de actuacao | 100 | 102 | 100 | 271 |
| `SEAct.dbf` | Actuator File | 88 | 6 | — | 256 |
| `SEAnybit.dbf` | Anybit File | 88 | 6 | — | 13 |
| `SEByte.dbf` | ByteDiag File | 145 | 5 | — | 41 |
| `SESwitch.dbf` | Switch File | ~100 | 12 | 10 | — |
| `SEMap.dbf` | Map File | 120 | — | — | tabelas de escala (float32) |
| `Sys\SE*.dbf` | System File | 202 | 6 | — | 21–1607 |

### O que cada tabela contem

- **SEItem** — o dicionario de parametros monitorizados: `Engine speed`,
  `Fuel pressure (5.0-10.8)`, `TPS voltage (0.5-4.5)`, `Water temperature
  (below 90)`, ... O item **117 e `Code`** (o codigo de falha).
- **SEConv** — formulas de conversao aplicadas ao valor bruto: `X`, `X*25`,
  `(X*5/256-0.5)*7.84/4`, `X*5/256*760*1.33/4`, `X-30`, ...
- **SEUnit** — unidades: `r/min`, `MPa`, `HPa`, `deg`, `V`, `ms`, `0C`, `0F`,
  `h`, `min`, `inHg`, `psi`, `%`, `0:OFF 1:ON`, `hPa`, `kPa`, `sec`, `Times`,
  `step`, `km/h`, `mph`.
- **SEAct / SEAnybit / SEByte** — descritores dos testes de activacao. `SEAct`
  tem 13 registos `[idx, 0x09, msgInicial, nMsgs]` e `SEAnybit` 10 registos
  `[idx, 0x05, msgInicial, 10]` — ambos a apontar para o `SEMess`.
  `SEByte` contem `B2 11 00 07`, pista para o servico de actuador.
- **SEMess** — 271 mensagens, indexadas por grupo no nibble alto:
  `0x0000` = actuacao ("Ignition coil #1 selected."), `0x1000` = pre-condicoes
  ("Make sure that the engine is not running."), `0x2000` = notas
  ("NOTE: Ignition coil is being tested...").
- **SESwitch** — rotulos de estado (`ON`, `OFF`, `YES`, `NO`, ...).
- **SEMap** — tabelas de escala valor→grandeza fisica (floats: `0x42C80000` =
  100.0, `0x42C60000` = 99.0, ...).
- **Sys\SE0000..SE0018 / SE1000..SE1010** — 28 mapas por sistema, registos de
  6 bytes `(chave, valor, flags)`, comecam em `14 00 18 00 01 00`
  (`0x0014 → 0x0018`, flag 1). Varios sao byte-identicos entre si.
- **YDIS.Msg** — INI com todos os textos da interface, agrupados em 80 seccoes
  (`C001 COMMON MESSAGE`, `C017 Diagnosis Record`, `C197 Extended Data Logger`,
  `C207 Diag Code`, ...).

## A tabela de codigos de falha esta no SEItem (bloco 0xA0)

O `SEItem` codifica a **categoria no byte alto do indice**:

| Bloco | Itens | Conteudo |
|---|---|---|
| `0x00xx` | 176 | parametros monitorizados |
| `0x0Fxx` | 15 | sinais auxiliares (LPS, cruise assist) |
| `0x90xx` | 62 | testes de actuacao |
| **`0xA0xx`** | **73** | **codigos de falha (DTC) — 01 a 73** |
| `0xC0xx` | 21 | funcoes de controlo (nao sao falhas) |
| `0xD0xx` | 15 | histograma de horas por regime |

O bloco `0xA0` e a tabela de DTC do YDS: indice `0xA001` → codigo **01**
("Pulser coil"), `0xA049` → codigo **73**. Confirmado por o YDIS.Msg mostrar
apenas `CODE : <numero>` (seccao C207) — o numero corresponde a este indice.

O bloco `0xC0` parece semelhante mas nao e falha: a partir do 12 muda para
`Tacho pulse stop control`, `Warming up operation`, `Over-rev control`,
`Speed down control`, `Buzzer control` — sao **funcoes de controlo**.

A Yamaha usa **apenas codigos numericos decimais** (01-99); nao usa P/B/C/U.
A versao 1.87.0.0 da base traz 73 codigos; modelos mais recentes podem chegar a 99.

## Os `.cab` estao cifrados

Assinatura `ISc(` (InstallShield 5). O bloco de descritores em `0x200` ja e
dados cifrados, nao uma tabela de nomes — 7-Zip 19.00 recusa
(`Can not open the file as [Cab] archive`) e `expand.exe` apenas copia. Extrair
exige um leitor do formato IS5 (algoritmo de descompressao proprio).

## Conclusao pratica

O valor esta tanto no **dicionario de monitorizacao** (`SEItem` 0x00) como na
**tabela de DTC** (`SEItem` 0xA0):

- nomes canonicos dos 176 parametros Yamaha;
- **73 codigos de falha numericos (01-73) com descricao**;
- 63 formulas de conversao prontas a aplicar;
- 21 unidades;
- 80 categorias de UI (mapa funcional do YDS).

Extraido para o projeto por `ecm_scanner/tools/extract_yds_db.py`:

- `ecm_scanner/yamaha_yds_items.json` — dicionario completo, com os itens ja
  separados por categoria (`monitor_items`, `actuation_items`, `dtc_items`,
  `control_items`, `hours_items`);
- `ecm_scanner/yamaha_dtc_codes.json` — **73 codigos 01-73** no formato
  `{"01": {"desc": "Pulser coil", "sol": ""}}`, consumido pelo `main.py`.
