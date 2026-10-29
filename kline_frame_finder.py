#!/usr/bin/env python3
"""
kline_frame_finder.py - Analise de autocorrelacao e estrutura de frames
=======================================================================
Tenta descobrir o tamanho do frame K-Line por correlacao estatistica.
"""
import re
from collections import Counter, deque

LOG_FILE = r"C:\Temp\yds_bridge2_20260522_152859.txt"
LINE_RE = re.compile(r'^\[(\d+\.\d+)\]\s+(TX|RX)\s+\[\s*(\d+)\]\s+((?:[0-9A-Fa-f]{2}\s*)+)')

def parse_rx_stream(path):
    """Retorna lista de (timestamp, byte) do stream RX."""
    stream = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = LINE_RE.match(line.strip())
            if m and m.group(2) == 'RX':
                ts = float(m.group(1))
                for b in bytes.fromhex(m.group(4).replace(' ', '')):
                    stream.append((ts, b))
    return stream

def autocorrelation(data, max_period=64):
    """Compute agreement score for each hypothesis period."""
    n = len(data)
    scores = {}
    for period in range(2, min(max_period+1, n//4)):
        matches = sum(1 for i in range(n - period) if data[i] == data[i + period])
        scores[period] = matches / (n - period)
    return scores

def find_steady_state(stream, t_start=24.9):
    """Take only steady-state data after t_start."""
    return [(ts, b) for ts, b in stream if ts >= t_start]

def candidate_frames(data, period):
    """Split data into frames of given period and show most common."""
    frames = []
    for i in range(0, len(data) - period + 1, period):
        frames.append(tuple(data[i:i+period]))
    return Counter(frames)

def find_transition_points(data, window=8):
    """Find positions where the pattern changes significantly."""
    if len(data) < window * 2:
        return []
    transitions = []
    for i in range(window, len(data) - window):
        before = Counter(data[i-window:i])
        after  = Counter(data[i:i+window])
        # Simple divergence: sum of absolute differences in freq
        all_keys = set(before) | set(after)
        div = sum(abs(before.get(k,0) - after.get(k,0)) for k in all_keys)
        transitions.append((i, div))
    return sorted(transitions, key=lambda x: -x[1])[:20]

def decode_as_binary(data, zero_byte=0xE0, one_set={0x60, 0x20}):
    """Map bytes to 0/1 bits and group into bytes."""
    bits = []
    for b in data:
        if b == zero_byte:
            bits.append(0)
        elif b in one_set:
            bits.append(1)
        else:
            bits.append(None)  # unknown/rare

    # Remove None - try to decode around them
    clean_bits = [b for b in bits if b is not None]

    # Group clean bits into bytes (groups of 8)
    byte_list = []
    for i in range(0, len(clean_bits) - 7, 8):
        chunk = clean_bits[i:i+8]
        val = 0
        for idx, bit in enumerate(chunk):
            val |= bit << (7 - idx)  # MSB first
        byte_list.append(val)
    return byte_list, bits

def main():
    print("=" * 72)
    print("KLINE FRAME FINDER")
    print("=" * 72)

    stream = parse_rx_stream(LOG_FILE)
    print(f"Total RX bytes: {len(stream)}")

    # --- Separar fase inicial e fase estavel
    early  = [(ts,b) for ts,b in stream if ts < 24.9]
    steady = [(ts,b) for ts,b in stream if ts >= 24.9]
    print(f"Early phase (t<24.9s): {len(early)} bytes")
    print(f"Steady state (t>=24.9s): {len(steady)} bytes")

    raw_early  = bytes(b for _,b in early)
    raw_steady = bytes(b for _,b in steady)

    # --- Show early phase decoded
    print("\n=== FASE INICIAL (primeiros 100 bytes brutos) ===")
    for i in range(0, min(100, len(raw_early)), 16):
        chunk = raw_early[i:i+16]
        print(f"  {i:04X}: {' '.join('%02X'%b for b in chunk)}")

    # --- Autocorrelation no estado estavel
    print("\n=== AUTOCORRELACAO (estado estavel) ===")
    scores = autocorrelation(list(raw_steady), max_period=64)
    sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
    print("  Top 15 periodos candidatos:")
    for period, score in sorted_scores[:15]:
        bar = '|' * int(score * 60)
        print(f"    period={period:3d}: match={score:.4f} {bar}")

    # --- Tentar frame sizes
    best_period = sorted_scores[0][0]
    print(f"\n=== FRAMES DE TAMANHO {best_period} ===")
    fc = candidate_frames(list(raw_steady), best_period)
    print(f"  Frames unicos: {len(fc)}")
    print(f"  Top 10 mais comuns:")
    for frame, cnt in fc.most_common(10):
        hex_s = ' '.join('%02X'%b for b in frame)
        print(f"    [{hex_s}] x{cnt}")

    # Tambem testar alguns periodos tipicos de K-Line
    for test_period in [4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 16, 3, 2]:
        fc = candidate_frames(list(raw_steady), test_period)
        top1 = fc.most_common(1)
        if top1:
            top_count = top1[0][1]
            total = sum(fc.values())
            pct = 100 * top1[0][1] * test_period / len(raw_steady)
            if pct > 5:  # só mostra se top frame >= 5% dos bytes
                top_hex = ' '.join('%02X'%b for b in top1[0][0])
                print(f"  period={test_period:3d}: {len(fc)} frames unicos, top=[{top_hex}] {top_count}x ({pct:.1f}%)")

    # --- Decodificar como bits (0xE0=0, 0x60=1)
    print("\n=== DECODIFICACAO BINARIA (E0=bit0, 60/20=bit1) ===")
    byte_list, bits = decode_as_binary(list(raw_steady))
    print(f"  Total bits: {len(bits)}, None bits (raros): {sum(1 for b in bits if b is None)}")
    print(f"  Bytes decodificados (MSB first, agrupado a cada 8 bits): {len(byte_list)}")
    print(f"  Primeiros 64 bytes decodificados:")
    for i in range(0, min(64, len(byte_list)), 16):
        chunk = byte_list[i:i+16]
        hex_s = ' '.join('%02X'%b for b in chunk)
        asc_s = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"    {i:04X}: {hex_s:<48} |{asc_s}|")

    # Autocorrelacao nos bits decodificados
    if len(byte_list) > 20:
        bin_scores = autocorrelation(byte_list, max_period=32)
        bin_sorted = sorted(bin_scores.items(), key=lambda x: -x[1])
        print(f"\n  Autocorrelacao nos bytes binario-decodificados:")
        for period, score in bin_sorted[:8]:
            print(f"    period={period:3d}: {score:.4f}")

    # LSB first alternative
    print("\n=== DECODIFICACAO BINARIA LSB-FIRST ===")
    byte_list_lsb = []
    clean_bits = [b for b in bits if b is not None]
    for i in range(0, len(clean_bits) - 7, 8):
        chunk = clean_bits[i:i+8]
        val = 0
        for idx, bit in enumerate(chunk):
            val |= bit << idx  # LSB first
        byte_list_lsb.append(val)
    print(f"  Primeiros 64 bytes (LSB first):")
    for i in range(0, min(64, len(byte_list_lsb)), 16):
        chunk = byte_list_lsb[i:i+16]
        hex_s = ' '.join('%02X'%b for b in chunk)
        asc_s = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"    {i:04X}: {hex_s:<48} |{asc_s}|")

    # --- Analise dos primeiros bytes apos TX (handshake)
    # Track TX events e analisar RX logo apos
    print("\n=== ANALISE DO HANDSHAKE K-LINE ===")
    all_stream_with_dir = []
    with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = LINE_RE.match(line.strip())
            if m:
                ts = float(m.group(1))
                dirn = m.group(2)
                data = bytes.fromhex(m.group(4).replace(' ', ''))
                all_stream_with_dir.append((ts, dirn, data))

    print("  Sequencia de init (primeiros 200ms):")
    for ts, dirn, data in all_stream_with_dir:
        if ts > 22.8:
            break
        arr = '->' if dirn == 'TX' else '<-'
        hex_s = ' '.join('%02X'%b for b in data)
        print(f"    [{ts:.3f}] {arr} {hex_s}")

    # --- Janela de 1s dos dados brutos (estado estavel)
    print("\n=== JANELA 1s ESTADO ESTAVEL (t=25.0-26.0) ===")
    window = [b for ts, b in steady if 25.0 <= ts <= 26.0]
    print(f"  Bytes na janela: {len(window)}")
    for i in range(0, len(window), 16):
        chunk = window[i:i+16]
        print(f"  {i:03d}: {' '.join('%02X'%b for b in chunk)}")

    # Contar E0 e 60 comprimentos de runs
    print("\n=== RUNS DE E0 E 60 (estado estavel) ===")
    run_e0_lengths = Counter()
    run_60_lengths = Counter()
    cur_byte = None
    cur_len = 0
    for b in raw_steady:
        if b == 0xE0:
            if cur_byte == 0x60:
                run_60_lengths[cur_len] += 1
            if cur_byte != 0xE0:
                cur_byte = 0xE0
                cur_len = 0
            cur_len += 1
        elif b in (0x60, 0x20):
            if cur_byte == 0xE0:
                run_e0_lengths[cur_len] += 1
            if cur_byte not in (0x60, 0x20):
                cur_byte = 0x60
                cur_len = 0
            cur_len += 1
        else:
            cur_byte = b
            cur_len = 1

    print(f"  Comprimentos de runs de 0xE0:")
    for length, count in sorted(run_e0_lengths.items()):
        print(f"    run={length:3d}: {count:5d}x")
    print(f"  Comprimentos de runs de 0x60/0x20:")
    for length, count in sorted(run_60_lengths.items()):
        print(f"    run={length:3d}: {count:5d}x")

if __name__ == '__main__':
    main()
