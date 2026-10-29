#!/usr/bin/env python3
"""Decodifica uma captura do serial_bridge em trocas YDS.

O YDS (ver docs/YDS_Protocol_Decompiled.md) fala com o equipamento byte a byte:
PurgeComm -> TX 1 byte -> RX eco (igual ao enviado) -> RX resposta, com 110 ms
por byte e 3 tentativas. Este script reconstroi essa estrutura a partir do log
do serial_bridge.

Uso:
    python yds_capture_decode.py C:\\Temp\\yds_bridge_YYYYmmdd_HHMMSS.txt
    python yds_capture_decode.py <log> --window 250
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

LINE_RE = re.compile(
    r"^\[\s*(\d+\.\d+)\]\s+(TX|RX)\s+\[\s*\d+\]\s+([0-9A-F ]+?)\s+\|")

WAKE_BYTE = 0x1C
HANDSHAKE = (0xFD, 0xE5, 0xE5, 0xFE, 0xFF, 0xFE, 0xFF)
LADDER = (0xF0, 0xEF, 0xEE, 0xED, 0xEC, 0xE4, 0xE3, 0xE2, 0xE1, 0xE0)


@dataclass
class ByteEvent:
    t: float
    direction: str
    value: int


def parse_log(path: Path) -> list:
    events = []
    skipped = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "|keepalive|" in raw:
            skipped += 1
            continue
        match = LINE_RE.match(raw)
        if not match:
            continue
        t = float(match.group(1))
        direction = match.group(2)
        for token in match.group(3).split():
            events.append(ByteEvent(t, direction, int(token, 16)))
    return events, skipped


def classify(events: list, window_ms: float) -> list:
    """Agrupa em trocas (TX -> eco? -> resposta) dentro de uma janela."""
    exchanges = []
    i = 0
    total = len(events)
    while i < total:
        event = events[i]
        if event.direction != "TX":
            i += 1
            continue

        sent = event.value
        replies = []
        j = i + 1
        while j < total:
            # Nada depois do proximo TX pode pertencer a esta troca.
            if events[j].direction == "TX":
                break
            if (events[j].t - event.t) * 1000.0 > window_ms:
                break
            replies.append(events[j])
            j += 1

        echo = None
        response = None
        if replies:
            if replies[0].value == sent:
                echo = replies[0].value
                if len(replies) > 1:
                    response = replies[1].value
            else:
                response = replies[0].value

        exchanges.append({
            "t": event.t,
            "sent": sent,
            "echo": echo,
            "response": response,
            "noise": max(0, len(replies) - (1 if echo is not None else 0)
                         - (1 if response is not None else 0)),
        })
        i += 1
    return exchanges


def hexs(value) -> str:
    return "--" if value is None else f"0x{value:02X}"


def report(path: Path, events: list, exchanges: list, skipped: int) -> None:
    duration = events[-1].t - events[0].t if events else 0.0
    tx = [e for e in events if e.direction == "TX"]
    rx = [e for e in events if e.direction == "RX"]

    print("=" * 74)
    print(f"CAPTURA: {path.name}")
    print("=" * 74)
    print(f"  duracao      : {duration:.3f} s")
    print(f"  bytes TX     : {len(tx)}      bytes RX: {len(rx)}")
    print(f"  trocas (TX)  : {len(exchanges)}")
    if skipped:
        print(f"  linhas de keepalive ignoradas: {skipped}")

    if not tx:
        print("\n[!] Nenhum byte enviado pelo YDS. O YDS nao chegou a abrir a porta?")
        return

    answered = [x for x in exchanges if x["response"] is not None]
    echoed = [x for x in exchanges if x["echo"] is not None]
    print(f"  com eco      : {len(echoed)}")
    print(f"  com resposta : {len(answered)}")

    if not answered:
        print("\n[!] Nenhuma resposta: o lado fisico nao devolveu nada.")
        print("    Verifique o baud do bridge (--yds => 9600) e a porta do equipamento.")
    elif echoed and len(echoed) >= max(1, len(answered) // 2):
        print("\n[ok] O equipamento devolve o eco do byte enviado -> protocolo YDS confirmado.")
    elif answered:
        print("\n[ok] Respostas recebidas sem eco (transporte directo).")

    wake = [x for x in exchanges if x["sent"] == WAKE_BYTE]
    if wake:
        print(f"\nWake-up 0x1C: {len(wake)} envio(s); "
              f"resposta {'sim' if wake[0]['response'] is not None else 'nao'}")

    first_tx = tx[0]
    print(f"\nPrimeiro byte enviado: {hexs(first_tx.value)} a t={first_tx.t:.3f}s")

    print("\n" + "-" * 74)
    print("TROCAS (primeiras 60)")
    print("-" * 74)
    print(f"{'t(s)':>9}  {'TX':>5}  {'eco':>5}  {'resp':>5}  {'lixo':>5}  nota")
    seen = {}
    for item in exchanges[:60]:
        note = ""
        seen[item["sent"]] = seen.get(item["sent"], 0) + 1
        occurrence = seen[item["sent"]]
        if item["sent"] == WAKE_BYTE:
            note = "wake-up (300 baud)"
        elif item["sent"] in HANDSHAKE:
            note = f"handshake pos {HANDSHAKE.index(item['sent']) + 1}"
            if occurrence > 1:
                note += f" (rep {occurrence})"
        elif item["sent"] in LADDER:
            note = f"escada pos {LADDER.index(item['sent']) + 1}"
        if item["response"] is None:
            note = (note + " sem resposta").strip()
        print(f"{item['t']:9.3f}  {hexs(item['sent']):>5}  {hexs(item['echo']):>5}  "
              f"{hexs(item['response']):>5}  {item['noise']:5d}  {note}")

    if len(exchanges) > 60:
        print(f"... {len(exchanges) - 60} trocas adicionais")

    verdict(exchanges)


def verdict(exchanges: list) -> None:
    """Compara a sequencia observada com o handshake descompilado."""
    print("\n" + "-" * 74)
    print("VEREDICTO FACE AO YDS.EXE DESCOMPILADO")
    print("-" * 74)

    sent = [x["sent"] for x in exchanges]
    answered = [x for x in exchanges if x["response"] is not None]

    if not answered:
        print("  Sem respostas -- incompativel apenas por falta de equipamento,")
        print("  nao por divergencia de protocolo. Repetir com o link fisico bom.")
        return

    # handshake: FD E5 E5 FE FF FE FF
    for index, value in enumerate(HANDSHAKE):
        match = next((x for x in exchanges if x["sent"] == value and x in answered), None)
        if match is None:
            print(f"  [{index + 1}/7] {hexs(value)} : nao observado com resposta")
            continue
        detail = ""
        if value == 0xE5:
            detail = "  OK (0xEF/0xED esperado)" if match["response"] in (0xEF, 0xED) \
                     else f"  !! esperado 0xEF/0xED, veio {hexs(match['response'])}"
        print(f"  [{index + 1}/7] {hexs(value)} -> {hexs(match['response'])}{detail}")

    if WAKE_BYTE in sent:
        print(f"  wake  : {hexs(WAKE_BYTE)} presente antes de 0xFD: "
              f"{'sim' if sent.index(WAKE_BYTE) < sent.index(0xFD) else 'nao'}"
              if 0xFD in sent else f"  wake  : {hexs(WAKE_BYTE)} presente")
    else:
        print(f"  wake  : {hexs(WAKE_BYTE)} NAO enviado (o YDS so o envia ao abrir a porta)")

    ladder_hit = [x for x in exchanges if x["sent"] in LADDER and x["response"] is not None]
    if ladder_hit:
        print(f"  escada: primeiro endereco com resposta = {hexs(ladder_hit[0]['sent'])} "
              f"-> {hexs(ladder_hit[0]['response'])}")
    else:
        print("  escada: nenhum endereco F0..E0 respondido")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", help="Ficheiro .txt do serial_bridge")
    parser.add_argument("--window", type=float, default=250.0,
                        help="Janela em ms para associar a resposta (padrao 250)")
    args = parser.parse_args()

    path = Path(args.log)
    if not path.exists():
        print(f"nao encontrado: {path}", file=sys.stderr)
        return 2

    events, skipped = parse_log(path)
    if not events:
        print(f"nenhum byte reconhecido em {path}", file=sys.stderr)
        return 2

    report(path, events, classify(events, args.window), skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
