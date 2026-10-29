#!/usr/bin/env python3
"""
Estudo de frames Yamaha K-line iniciados por F8.

Objetivos:
- Decodificar bytes UART por amostragem no centro do bit
- Extrair transacoes iniciadas por 0xF8
- Comparar wakeup/inicializacao com telemetria continua

Uso:
  python kline_f8_frame_study.py <arquivo.txt> [baud] [start_ms] [end_ms]

Exemplos:
  python kline_f8_frame_study.py yam.txt 15625 1040 1200
  python kline_f8_frame_study.py "yamaha funcionando.txt" 15625
"""

import sys
from collections import Counter

THRESHOLD_V = 2.0


def load_oscilloscope(fname):
    with open(fname, "r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()

    clock_s = None
    size = None
    header_end = 0
    for index, line in enumerate(lines):
        text = line.strip()
        if text.startswith("#CLOCK="):
            clock_s = float(text.split("=")[1].split()[0])
        elif text.startswith("#SIZE="):
            size = int(text.split("=")[1])
        elif text and not text.startswith("#"):
            header_end = index
            break

    if not clock_s or not size:
        raise ValueError("Arquivo sem cabecalho #CLOCK/#SIZE valido")

    sample_rate = size / clock_s
    data = []
    for line in lines[header_end:]:
        text = line.strip()
        if not text:
            continue
        try:
            data.append(float(text))
        except ValueError:
            continue

    digital = [1 if value >= THRESHOLD_V else 0 for value in data]
    return digital, sample_rate, clock_s, size


def decode_uart(digital, sample_rate, baud, start_ms=0.0, end_ms=None):
    bit_samples = sample_rate / baud
    start_index = max(1, int(start_ms * sample_rate / 1000.0))
    end_index = len(digital) if end_ms is None else min(len(digital), int(end_ms * sample_rate / 1000.0))

    decoded = []
    index = start_index
    while index < end_index - int(11 * bit_samples):
        if digital[index - 1] == 1 and digital[index] == 0:
            bits = []
            for bit_number in range(8):
                sample_pos = int(index + (bit_number + 1.5) * bit_samples)
                if sample_pos >= len(digital):
                    bits = []
                    break
                bits.append(digital[sample_pos])

            stop_pos = int(index + 9.5 * bit_samples)
            if len(bits) == 8 and stop_pos < len(digital):
                byte_val = sum(bit << pos for pos, bit in enumerate(bits))
                stop_ok = digital[stop_pos] == 1
                timestamp_ms = index / sample_rate * 1000.0
                decoded.append((timestamp_ms, byte_val, stop_ok))

            index += int(10 * bit_samples)
            continue
        index += 1
    return decoded


def extract_f8_frames(decoded, max_len=3, only_stop_ok=False, max_gap_ms=10.0):
    usable = decoded if not only_stop_ok else [(t, b, s) for t, b, s in decoded if s]
    frames = []
    for index in range(len(usable)):
        t0, b0, s0 = usable[index]
        if b0 != 0xF8:
            continue

        frame = [(t0, b0, s0)]
        prev_t = t0
        for next_index in range(index + 1, min(len(usable), index + max_len)):
            tn, bn, sn = usable[next_index]
            if tn - prev_t > max_gap_ms:
                break
            frame.append((tn, bn, sn))
            prev_t = tn
        frames.append(frame)
    return frames


def summarize_frames(frames, title, top_n=12):
    print(f"\n=== {title} ===")
    if not frames:
        print("Nenhum frame F8 encontrado.")
        return

    pairs = Counter()
    triples = Counter()
    gaps = []
    for frame in frames:
        if len(frame) >= 2:
            pairs[frame[1][1]] += 1
            gaps.append((frame[1][0] - frame[0][0]) * 1000.0)
        if len(frame) >= 3:
            triples[(frame[1][1], frame[2][1])] += 1

    print(f"Frames F8 extraidos: {len(frames)}")
    if gaps:
        avg_gap = sum(gaps) / len(gaps)
        print(f"Gap medio F8->byte1: {avg_gap:.1f} us")

    print("Top F8 -> byte1:")
    for value, count in pairs.most_common(top_n):
        print(f"  F8 {value:02X} : {count}")

    print("Top F8 -> byte1 -> byte2:")
    for (b1, b2), count in triples.most_common(top_n):
        print(f"  F8 {b1:02X} {b2:02X} : {count}")

    print("Primeiros frames:")
    for frame in frames[:15]:
        t_start = frame[0][0]
        payload = " ".join(f"{byte:02X}{'' if stop_ok else '*'}" for _, byte, stop_ok in frame)
        print(f"  t={t_start:8.3f} ms  [{payload}]")


def detect_window(fname):
    lowered = fname.lower()
    if lowered.endswith("yam.txt") or lowered == "yam.txt":
        return 1040.0, 1200.0
    return 0.0, None


def main():
    fname = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\johan\Documents\projetoCAN\yam.txt"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 15625

    default_start_ms, default_end_ms = detect_window(fname)
    start_ms = float(sys.argv[3]) if len(sys.argv) > 3 else default_start_ms
    end_ms = float(sys.argv[4]) if len(sys.argv) > 4 else default_end_ms

    digital, sample_rate, clock_s, size = load_oscilloscope(fname)
    decoded = decode_uart(digital, sample_rate, baud, start_ms=start_ms, end_ms=end_ms)

    ok_count = sum(1 for _, _, stop_ok in decoded if stop_ok)
    err_count = len(decoded) - ok_count

    print(f"Arquivo: {fname}")
    print(f"Amostras: {size}  Clock: {clock_s}s  Fs: {sample_rate:.0f} Hz")
    print(f"Baud: {baud}  Janela: {start_ms:.1f} ms -> {end_ms if end_ms is not None else 'EOF'}")
    print(f"Bytes decodificados: {len(decoded)}  OK={ok_count}  ERR={err_count}")

    all_frames = extract_f8_frames(decoded, max_len=3, only_stop_ok=False)
    ok_frames = extract_f8_frames(decoded, max_len=3, only_stop_ok=True)

    summarize_frames(all_frames, "Frames F8 (todos os bytes)")
    summarize_frames(ok_frames, "Frames F8 (somente stop=OK)")


if __name__ == "__main__":
    main()