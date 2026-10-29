#!/usr/bin/env python3
"""
Extrai transacoes Yamaha iniciadas por 0xF8 a partir de um log de osciloscopio.

Uso:
    python kline_f8_frame_extract.py <arquivo.txt> [baud]

Foco:
- comparar wakeup (`yam.txt`) vs lenta (`yamaha funcionando.txt`)
- contar pares e triplas no formato F8 -> byte1 -> byte2
- mostrar exemplos cronologicos das primeiras transacoes
"""

import sys
from collections import Counter


THRESHOLD = 2.0
DEFAULT_BAUD = 15625


def load_oscilloscope(fname):
    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    clock_s = None
    size = None
    header_end = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#CLOCK="):
            clock_s = float(s.split("=")[1].split()[0])
        elif s.startswith("#SIZE="):
            size = int(s.split("=")[1])
        elif s and not s.startswith("#"):
            header_end = i
            break

    if not clock_s or not size:
        raise ValueError("Cabecalho invalido: #CLOCK/#SIZE nao encontrados")

    sample_rate = size / clock_s
    digital = []
    for line in lines[header_end:]:
        s = line.strip()
        if not s:
            continue
        try:
            digital.append(1 if float(s) >= THRESHOLD else 0)
        except ValueError:
            continue
    return digital, sample_rate, clock_s, size


def decode_uart(digital, sample_rate, baud, limit=None):
    bit_samples = sample_rate / baud
    raw_bytes = []
    i = 1
    max_index = len(digital) - int(11 * bit_samples)

    while i < max_index:
        if digital[i - 1] == 1 and digital[i] == 0:
            bits = []
            for bit_num in range(8):
                sample_pos = int(i + (bit_num + 1.5) * bit_samples)
                if sample_pos >= len(digital):
                    bits = []
                    break
                bits.append(digital[sample_pos])

            stop_pos = int(i + 9.5 * bit_samples)
            if len(bits) == 8 and stop_pos < len(digital):
                byte_val = sum(bit << pos for pos, bit in enumerate(bits))
                stop_ok = digital[stop_pos] == 1
                raw_bytes.append((i / sample_rate * 1000, byte_val, stop_ok))
                if limit is not None and len(raw_bytes) >= limit:
                    break

            i += int(10 * bit_samples)
            continue
        i += 1

    return raw_bytes


def extract_f8_transactions(decoded, max_gap_us=10000):
    transactions = []
    for i in range(len(decoded) - 2):
        t0, b0, s0 = decoded[i]
        t1, b1, s1 = decoded[i + 1]
        t2, b2, s2 = decoded[i + 2]
        gap1_us = (t1 - t0) * 1000
        gap2_us = (t2 - t1) * 1000
        if b0 != 0xF8:
            continue
        if gap1_us > max_gap_us or gap2_us > max_gap_us:
            continue
        transactions.append({
            "t_ms": t0,
            "b1": b1,
            "b2": b2,
            "stop_pattern": (s0, s1, s2),
            "gap1_us": gap1_us,
            "gap2_us": gap2_us,
        })
    return transactions


def print_summary(fname, baud, decoded, transactions):
    ok = sum(1 for _, _, stop_ok in decoded if stop_ok)
    err = len(decoded) - ok
    pair_counts = Counter(tx["b1"] for tx in transactions)
    triple_counts = Counter((tx["b1"], tx["b2"]) for tx in transactions)

    print(f"Arquivo: {fname}")
    print(f"Baud: {baud}")
    print(f"Bytes decodificados: {len(decoded)} | OK={ok} | ERR={err}")
    print(f"Transacoes F8 extraidas: {len(transactions)}")

    print("\n=== TOP F8 -> byte1 ===")
    for byte1, count in pair_counts.most_common(12):
        print(f"  F8 {byte1:02X} : {count}")

    print("\n=== TOP F8 -> byte1 -> byte2 ===")
    for (byte1, byte2), count in triple_counts.most_common(16):
        print(f"  F8 {byte1:02X} {byte2:02X} : {count}")

    print("\n=== PRIMEIRAS TRANSACOES ===")
    for tx in transactions[:20]:
        s0, s1, s2 = tx["stop_pattern"]
        stop_str = "".join("O" if s else "E" for s in (s0, s1, s2))
        print(
            f"  t={tx['t_ms']:8.3f} ms  F8 {tx['b1']:02X} {tx['b2']:02X}"
            f"  stop={stop_str}  gaps=[{tx['gap1_us']:.0f},{tx['gap2_us']:.0f}]us"
        )


def main():
    fname = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\johan\Documents\projetoCAN\yamaha funcionando.txt"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BAUD

    digital, sample_rate, clock_s, size = load_oscilloscope(fname)
    print(f"Amostras: {size}  Clock: {clock_s}s  Fs: {sample_rate:.0f} Hz  T: {1e6/sample_rate:.3f}us")
    decoded = decode_uart(digital, sample_rate, baud)
    transactions = extract_f8_transactions(decoded)
    print_summary(fname, baud, decoded, transactions)


if __name__ == "__main__":
    main()