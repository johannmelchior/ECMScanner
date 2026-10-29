#!/usr/bin/env python3
"""Extrai o dicionario de diagnostico do YDS (Yamaha) para JSON.

A pasta ``InstImage`` do YDS e a imagem do instalador; as tabelas ``DB/*.dbf``
nao sao dBase: tem um cabecalho ASCII proprio e registos de tamanho fixo
(texto codificado com o bit 7 ligado, ex. 0xC5 = "E", 0xA0 = espaco).

Layouts confirmados por analise (offset inicial, tamanho do registo, texto):

    SEItem.dbf   100  32  30   "Item File"     - parametros monitorizados
    SEConv.dbf   100  32  30   "Conv File"     - formulas de conversao
    SEUnit.dbf   100  12  10   "Unit File"     - unidades
    SEMess.dbf   100 102 100   "Message File"  - textos de actuacao
    SEAct.dbf     88   6   -   "Actuator File" - testes de actuacao
    SEAnybit.dbf  88   6   -   "Anybit File"
    SEByte.dbf   145   5   -   "ByteDiag File"
    Sys/SE*.dbf  202   6   -   "System File"   - mapa por sistema/ECU

Nao existe tabela de descricao de codigos de falha fora do SEItem: o YDIS.Msg
mostra apenas ``CODE : <numero>`` (secao C207 "Diag Code"). As descricoes estao
no SEItem, no bloco cujo byte alto do indice e 0xA0: 73 codigos numericos
(01-73), que e o formato que a Yamaha usa (nunca P/B/C/U).

Uso:
    python tools/extract_yds_db.py
    python tools/extract_yds_db.py --yds-dir "C:/Program Files/YDS" --out x.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import struct
import sys
from datetime import datetime, timezone

DEFAULT_YDS = r"C:\Program Files\YDS"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "yamaha_yds_items.json")

# nome do ficheiro -> (offset, tamanho do registo, bytes de texto)
TEXT_TABLES = {
    "SEItem.dbf": (100, 32, 30),
    "SEConv.dbf": (100, 32, 30),
    "SEUnit.dbf": (100, 12, 10),
    "SEMess.dbf": (100, 102, 100),
}

BINARY_TABLES = {
    "SEAct.dbf": (88, 6),
    "SEAnybit.dbf": (88, 6),
    "SEByte.dbf": (145, 5),
}

# SEItem codifica a categoria no byte alto do indice. Bloco 0xA0 = codigos de
# falha (Yamaha usa numeros 01-99, nunca P/C/B/U). Bloco 0xC0 = funcoes de
# controlo/actuacao, nao falhas. Bloco 0xD0 = histograma de horas por regime.
BLOCK_DTC = 0xA0
BLOCK_CONTROL = 0xC0
BLOCK_HOURS = 0xD0
BLOCK_ACTUATION = 0x90
BLOCK_MONITOR = 0x00

DEFAULT_DTC_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "yamaha_dtc_codes.json")

RE_DATE = re.compile(r"\b(20\d{6})\b")
RE_VERSION = re.compile(r"\b(\d+\.\d+\.\d+\.\d+)\b")
RE_PNO = re.compile(r"\b(F\d{3,4}[A-Z]\d{5}[A-Z]?-\d{4}-\d+(?:SE\d{5})?)\b")
RE_DESC = re.compile(r"\b(Message File|System File|Item File|Actuator File|"
                     r"ByteDiag File|Switch File|Map File|Pattern File|"
                     r"Anybit File|Conv File|Unit File|Form File)\b")


def decode_text(raw: bytes) -> str:
    """Texto do YDS: ASCII com o bit 7 ligado (0xA0 = espaco)."""
    return bytes(c & 0x7F for c in raw).decode("latin-1").strip()


def parse_header(blob: bytes) -> dict:
    head = "".join(chr(c) if 32 <= c < 127 else " " for c in blob[:140])
    info = {}
    for key, pattern in (("part_number", RE_PNO), ("date", RE_DATE),
                         ("version", RE_VERSION), ("description", RE_DESC)):
        match = pattern.search(head)
        if match:
            info[key] = match.group(1)
    if not info:
        info["raw"] = head.strip()
    return info


def read_text_table(path, offset, step, text_len):
    """Le uma tabela de texto; descarta o registo sentinela de padding."""
    blob = open(path, "rb").read()
    rows = []
    pos = offset
    while pos + step <= len(blob):
        index = struct.unpack("<H", blob[pos:pos + 2])[0]
        text = decode_text(blob[pos + 2:pos + 2 + text_len])
        if text and set(text) != {"*"}:
            rows.append({"index": index, "text": text})
        pos += step
    return rows


def read_system_file(path):
    """System File: registos de 6 bytes (chave, valor, flags) a partir de 202."""
    blob = open(path, "rb").read()
    entries = []
    pos = 202
    while pos + 6 <= len(blob):
        key, value, flags = struct.unpack("<HHH", blob[pos:pos + 6])
        if key == 0xFFFF:
            break
        entries.append([key, value, flags])
        pos += 6
    return entries


def read_ydis_messages(path):
    """YDIS.Msg e INI de texto puro: Mxxx="texto" agrupado por seccao Cxxx."""
    text = open(path, encoding="latin-1").read()
    sections = {}
    current = "?"
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        if line.startswith("C") and "=" in line:
            key, _, value = line.partition("=")
            current = value.strip() or key.strip()
            sections.setdefault(current, [])
        elif line.startswith("M") and "=" in line:
            key, _, value = line.partition("=")
            sections.setdefault(current, []).append(value.strip().strip('"'))
    return sections


def split_by_block(items):
    """Separa os itens SEItem pela categoria codificada no byte alto do indice."""
    blocks = {BLOCK_MONITOR: [], BLOCK_ACTUATION: [], BLOCK_DTC: [],
              BLOCK_CONTROL: [], BLOCK_HOURS: []}
    others = []
    for item in items:
        block = (item["index"] >> 8) & 0xFF
        number = item["index"] & 0xFF
        entry = {"code": number, "text": item["text"]}
        if block in blocks:
            blocks[block].append(entry)
        else:
            others.append({"index": item["index"], "text": item["text"]})
    for key in blocks:
        blocks[key].sort(key=lambda e: e["code"])
    return blocks, others


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yds-dir", default=DEFAULT_YDS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--dtc-out", default=DEFAULT_DTC_OUT,
                        help="ficheiro de DTC Yamaha gerado a partir do bloco 0xA0")
    args = parser.parse_args()

    db_dir = os.path.join(args.yds_dir, "InstImage", "DB")
    comm_dir = os.path.join(db_dir, "Comm")
    if not os.path.isdir(comm_dir):
        sys.exit("nao encontrado: %s" % comm_dir)

    cfg_path = os.path.join(db_dir, "YDSINFO.CFG")
    config = {}
    if os.path.exists(cfg_path):
        for line in open(cfg_path, encoding="latin-1"):
            if "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()

    tables = {}
    headers = {}
    for name, (offset, step, text_len) in TEXT_TABLES.items():
        path = os.path.join(comm_dir, name)
        if not os.path.exists(path):
            continue
        blob = open(path, "rb").read()
        headers[name] = parse_header(blob)
        tables[name.replace(".dbf", "").lower()] = read_text_table(
            path, offset, step, text_len)

    for name, (offset, step) in BINARY_TABLES.items():
        path = os.path.join(comm_dir, name)
        if not os.path.exists(path):
            continue
        blob = open(path, "rb").read()
        headers[name] = parse_header(blob)
        count = max(0, (len(blob) - offset) // step)
        tables[name.replace(".dbf", "").lower()] = {
            "record_size": step,
            "records": count,
        }

    systems = {}
    for path in sorted(glob.glob(os.path.join(db_dir, "Sys", "*.dbf"))):
        name = os.path.basename(path)
        blob = open(path, "rb").read()
        systems[name] = {
            "header": parse_header(blob),
            "entries": read_system_file(path),
        }

    msg_path = os.path.join(db_dir, "YDIS.Msg")
    messages = read_ydis_messages(msg_path) if os.path.exists(msg_path) else {}

    blocks, other_items = split_by_block(tables.get("seitem", []))

    payload = {
        "schema": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": os.path.join(args.yds_dir, "InstImage"),
        "config": config,
        "table_headers": headers,
        "items": tables.get("seitem", []),
        "monitor_items": blocks[BLOCK_MONITOR],
        "actuation_items": blocks[BLOCK_ACTUATION],
        "dtc_items": blocks[BLOCK_DTC],
        "control_items": blocks[BLOCK_CONTROL],
        "hours_items": blocks[BLOCK_HOURS],
        "other_items": other_items,
        "conversions": tables.get("seconv", []),
        "units": tables.get("seunit", []),
        "messages": tables.get("semess", []),
        "binary_tables": {k: v for k, v in tables.items()
                          if k in ("seact", "seanybit", "sebyte")},
        "systems": systems,
        "ydis_categories": {k: v for k, v in messages.items() if v},
    }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)

    # yamaha_dtc_codes.json: codigos numericos 01-99 consumidos pelo main.py
    dtc_codes = {}
    for entry in blocks[BLOCK_DTC]:
        dtc_codes["%02d" % entry["code"]] = {
            "desc": entry["text"],
            "sol": "",
        }
    with open(args.dtc_out, "w", encoding="utf-8") as handle:
        json.dump(dtc_codes, handle, ensure_ascii=False, indent=1)

    print("config        : %s" % config)
    print("itens         : %d" % len(payload["items"]))
    print("  monitor     : %d" % len(payload["monitor_items"]))
    print("  actuacao    : %d" % len(payload["actuation_items"]))
    print("  DTC (0xA0)  : %d  -> %s" % (len(payload["dtc_items"]),
                                          payload["dtc_items"][0]["text"]
                                          if payload["dtc_items"] else "-"))
    print("  controlo    : %d" % len(payload["control_items"]))
    print("  horas       : %d" % len(payload["hours_items"]))
    print("conversoes    : %d" % len(payload["conversions"]))
    print("unidades      : %d" % len(payload["units"]))
    print("mensagens     : %d" % len(payload["messages"]))
    print("sistemas      : %d" % len(payload["systems"]))
    print("categorias UI : %d" % len(payload["ydis_categories"]))
    print("escrito       : %s" % args.out)
    print("DTC escrito   : %s (%d codigos)" % (args.dtc_out, len(dtc_codes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
