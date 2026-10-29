#!/usr/bin/env python3
"""
Decoder K-line robusto: reconstroi bits via run-length a partir dos pulsos.
Testa multiplos baud rates e exibe bytes decodificados com timestamps.
"""
import sys
from collections import Counter

THRESHOLD = 2.0
T_TOTAL_S = 5.0


def load_data(path):
    data = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for l in f:
            l = l.strip()
            if l and not l.startswith("#"):
                data.append(float(l))
    return data


def get_raw_pulses(data, thr, T_us):
    """Retorna (nivel, dur_us, start_sample) para cada run de nivel."""
    pulses = []
    n = len(data)
    i = 0
    while i < n:
        nivel = 1 if data[i] > thr else 0
        j = i
        while j < n and (1 if data[j] > thr else 0) == nivel:
            j += 1
        dur_us = (j - i) * T_us
        pulses.append((nivel, dur_us, i))
        i = j
    return pulses


def filter_noise(pulses, min_us=50.0):
    """Remove pulsos menores que min_us fundindo com vizinhos."""
    result = list(pulses)
    changed = True
    while changed:
        changed = False
        merged = []
        i = 0
        while i < len(result):
            n, d, s = result[i]
            if d < min_us and i > 0 and i < len(result) - 1:
                # Funde com entorno
                prev_n, prev_d, prev_s = merged[-1]
                next_n, next_d, next_s = result[i + 1]
                if prev_n == next_n:
                    # Remove este pulso e o proximo, expande o anterior
                    merged[-1] = (prev_n, prev_d + d + next_d, prev_s)
                    i += 2
                    changed = True
                    continue
            merged.append(result[i])
            i += 1
        result = merged
    return result


def reconstruct_bits(pulses, bit_us):
    """
    Reconstroi stream de bits: cada pulso vira round(dur/bit_us) bits.
    Retorna (bit_stream, sample_map) onde sample_map[i] = sample do bit i.
    """
    bit_stream = []
    sample_map = []
    for nivel, dur_us, start_s in pulses:
        n = max(1, round(dur_us / bit_us))
        for k in range(n):
            bit_stream.append(nivel)
            # Interpolacao linear do sample dentro do pulso
            sample_map.append(int(start_s + k * (dur_us / bit_us) * (bit_us / dur_us) * (dur_us / bit_us)))
    return bit_stream, sample_map


def decode_uart(bit_stream, sample_map, T_us, max_bytes=500):
    """
    Parse UART: start(0) + 8 bits LSB + stop(1).
    Retorna lista de (t_ms, byte_val, stop_ok).
    """
    decoded = []
    i = 1
    while i < len(bit_stream) - 10:
        if bit_stream[i - 1] == 1 and bit_stream[i] == 0:
            # start bit
            byte_val = 0
            for bn in range(8):
                pos = i + 1 + bn
                if pos < len(bit_stream):
                    byte_val |= (bit_stream[pos] << bn)
            stop_pos = i + 9
            stop_ok = (bit_stream[stop_pos] == 1) if stop_pos < len(bit_stream) else False
            t_ms = sample_map[i] * T_us / 1000 if i < len(sample_map) else 0
            decoded.append((t_ms, byte_val, stop_ok))
            i += 10
            continue
        i += 1
    return decoded


def test_baud(pulses, bit_us, T_us):
    bs, sm = reconstruct_bits(pulses, bit_us)
    decoded = decode_uart(bs, sm, T_us, max_bytes=2000)
    ok = sum(1 for _, _, s in decoded if s)
    err = sum(1 for _, _, s in decoded if not s)
    return ok, err, decoded


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\johan\Documents\yamaha funcionando.txt"
    force_baud = int(sys.argv[2]) if len(sys.argv) > 2 else None

    print(f"Carregando {path}...")
    data = load_data(path)
    T_us = T_TOTAL_S * 1e6 / len(data)
    print(f"Amostras: {len(data)} | T: {T_us:.3f} us | Fs: {1e6/T_us:.0f} Hz\n")

    raw_pulses = get_raw_pulses(data, THRESHOLD, T_us)
    print(f"Pulsos brutos: {len(raw_pulses)}")

    # Histograma rapido das durações antes de filtrar
    hist = Counter(int(d / 5) * 5 for _, d, _ in raw_pulses if 20 < d < 400)
    top5 = sorted(hist.items(), key=lambda x: -x[1])[:8]
    print(f"Top durações (us): " + "  ".join(f"{k}us×{v}" for k, v in top5))

    # Deduzir "baud" candidato a partir do pico mais comum de duração curta
    short_peaks = [(k, v) for k, v in sorted(hist.items()) if k < 200]
    if short_peaks:
        # Pico dominante em duracoes curtas = 1 bit
        dominant = max((v for k, v in short_peaks if 40 <= k <= 120), default=60)
        dominant_dur = max(((k, v) for k, v in short_peaks if 40 <= k <= 120), key=lambda x: x[1], default=(62, 0))[0]
        guessed_baud = round(1e6 / dominant_dur / 100) * 100
        print(f"Pico dominante curto: {dominant_dur}us -> baud estimado: {guessed_baud}")

    # Filtrar ruido (<50us)
    clean_pulses = filter_noise(raw_pulses, min_us=50.0)
    print(f"Pulsos apos filtro: {len(clean_pulses)}\n")

    # Escanear baud rates
    print("=== SCAN DE BAUD RATES ===")
    print(f"{'Baud':>8}  {'OK':>6}  {'ERR':>6}  {'%OK':>7}  {'Total':>6}  {'Nota'}")
    print("-" * 55)

    candidates = [4800, 7812, 9600, 10400, 12500, 15625, 16040, 19200, 28800]
    best = (0, 0, None, 0)
    for baud in candidates:
        bit_us = 1e6 / baud
        ok, err, dec = test_baud(clean_pulses, bit_us, T_us)
        total = ok + err
        pct = 100 * ok / total if total > 0 else 0
        note = "<<< MELHOR" if pct > (best[0]) else ""
        if pct > best[0]:
            best = (pct, baud, dec, bit_us)
        print(f"{baud:>8}  {ok:>6}  {err:>6}  {pct:>6.1f}%  {total:>6}  {note}")

    best_pct, best_baud, best_dec, best_bit_us = best
    if force_baud:
        best_baud = force_baud
        best_bit_us = 1e6 / force_baud
        _, _, best_dec = test_baud(clean_pulses, best_bit_us, T_us)[0], test_baud(clean_pulses, best_bit_us, T_us)[1], test_baud(clean_pulses, best_bit_us, T_us)[2]

    print(f"\nMelhor baud: {best_baud} ({best_pct:.1f}% stop bits OK)")

    # Decodificar com melhor baud
    decoded = best_dec
    valid = [(t, b) for t, b, s in decoded if s]
    all_bytes = [(t, b) for t, b, s in decoded]

    print(f"\n=== BYTES DECODIFICADOS @ {best_baud} BAUD ===")
    print(f"Total: {len(decoded)} | Stop OK: {len(valid)} | Stop ERR: {len(decoded)-len(valid)}")

    # Mostrar primeiros 120 bytes
    print(f"\n{'T(ms)':>9}  {'HEX':>4}  {'Dec':>3}  Stop")
    print("-" * 35)
    prev_t = 0
    for t, b, s in decoded[:120]:
        gap = ""
        if t - prev_t > 5.0:
            gap = f"\n  --- GAP {t-prev_t:.1f}ms ---\n"
        stop_str = "OK" if s else "  "
        print(f"{gap}{t:>9.3f}  {b:02X}  {b:>3d}  {stop_str}")
        prev_t = t

    # HEX stream apenas dos bytes validos
    byte_vals = [b for _, b in valid]
    print(f"\n=== HEX STREAM (stop=OK): {len(byte_vals)} bytes ===")
    # Imprimir em linhas de 16
    for i in range(0, min(len(byte_vals), 160), 16):
        row = byte_vals[i:i+16]
        hex_part = " ".join(f"{b:02X}" for b in row)
        asc_part = "".join(chr(b) if 0x20 <= b <= 0x7e else "." for b in row)
        print(f"  {i:4d}: {hex_part:<48}  {asc_part}")

    # Analise de frames repetidos
    print(f"\n=== ANALISE DE REPETICAO (frames de tamanho N) ===")
    for frame_sz in [3, 4, 5, 6, 7]:
        frames = []
        for i in range(0, len(byte_vals) - frame_sz, frame_sz):
            frames.append(tuple(byte_vals[i:i+frame_sz]))
        cnt = Counter(frames)
        top3 = cnt.most_common(3)
        hex_frames = [(" ".join(f"{b:02X}" for b in fr), c) for fr, c in top3]
        print(f"  N={frame_sz}: " + "  |  ".join(f"[{h}]×{c}" for h, c in hex_frames))

    # Analise de gaps (silencio entre transmissoes)
    print(f"\n=== GAPS ENTRE BYTES (> 2ms) ===")
    for i in range(1, len(decoded)):
        gap = decoded[i][0] - decoded[i-1][0]
        if gap > 2.0:
            t1 = decoded[i-1][0]
            b1 = decoded[i-1][1]
            t2 = decoded[i][0]
            b2 = decoded[i][1]
            context_before = [decoded[j][1] for j in range(max(0,i-5), i)]
            context_after  = [decoded[j][1] for j in range(i, min(len(decoded),i+5))]
            hex_before = " ".join(f"{b:02X}" for b in context_before)
            hex_after  = " ".join(f"{b:02X}" for b in context_after)
            print(f"  t={t1:.1f}ms → t={t2:.1f}ms  gap={gap:.1f}ms  | ...{hex_before} | {hex_after}...")


if __name__ == "__main__":
    main()
