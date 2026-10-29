#!/usr/bin/env python3
"""
Decoder UART de alta precisao: amostragem por centro de bit (bit-center sampling).
Nao usa run-length encoding. Trabalha diretamente no vetor de amostras digitizado.
Permite testar varios baud rates e verifica o padrao do wakeup K-line.
"""
import sys

THRESHOLD = 2.0
T_TOTAL_S = 5.0


def load_data(path):
    data = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                data.append(float(line))
    return data


def digitize(data, thr):
    return [1 if v > thr else 0 for v in data]


def center_sample_uart(bits, start_sample, N, bit_samples):
    """
    Decodifica 1 byte UART a partir de start_sample (falling edge = inicio do start bit).
    Amostra N bits de dados no centro de cada bit.
    Retorna (byte_val, stop_ok) ou None se fora do range.
    """
    byte_val = 0
    half = bit_samples / 2.0
    for bn in range(N):
        pos = int(start_sample + (bn + 1.5) * bit_samples)
        if pos >= len(bits):
            return None
        byte_val |= (bits[pos] << bn)
    stop_pos = int(start_sample + (N + 1.5) * bit_samples)
    if stop_pos >= len(bits):
        return None
    stop_ok = bits[stop_pos] == 1
    return byte_val, stop_ok


def decode_all(bits, T_us, baud, start=0, end=None):
    """
    Varre o sinal e decodifica todos os bytes UART encontrados.
    Retorna lista de (t_ms, byte_val, stop_ok).
    """
    if end is None:
        end = len(bits)
    bit_samples = (1e6 / baud) / T_us  # amostras por bit
    decoded = []
    i = start + 1

    while i < end:
        # Procura falling edge (HIGH->LOW = potencial start bit)
        if bits[i - 1] == 1 and bits[i] == 0:
            result = center_sample_uart(bits, i, 8, bit_samples)
            if result is not None:
                byte_val, stop_ok = result
                t_ms = i * T_us / 1000
                decoded.append((t_ms, byte_val, stop_ok))
                # Avanca para depois do byte completo (10 bits)
                next_i = int(i + 10 * bit_samples)
                i = max(i + 1, next_i)
                continue
        i += 1

    return decoded


def scan_bauds(bits, T_us, start=0, bauds=None):
    if bauds is None:
        bauds = [4800, 7800, 8000, 9600, 10400, 12000, 15625, 16040, 19200, 28800]

    print(f"\n{'Baud':>8}  {'OK':>6}  {'ERR':>6}  {'%OK':>7}  {'Total':>6}")
    print("-" * 45)
    results = []
    for baud in bauds:
        decoded = decode_all(bits, T_us, baud, start=start)
        ok = sum(1 for _, _, s in decoded if s)
        err = len(decoded) - ok
        pct = 100 * ok / len(decoded) if decoded else 0
        results.append((pct, baud, decoded))
        print(f"{baud:>8}  {ok:>6}  {err:>6}  {pct:>6.1f}%  {len(decoded):>6}")

    best = max(results, key=lambda x: (x[0], len(x[2])))
    print(f"\nMelhor: {best[1]} baud  ({best[0]:.1f}% stop OK, {len(best[2])} bytes)")
    return best


def print_hex_stream(decoded, only_ok=True, max_bytes=200):
    vals = [(t, b) for t, b, s in decoded if (not only_ok or s)]
    print(f"\n=== HEX STREAM {'(stop=OK)' if only_ok else '(todos)'}: {len(vals)} bytes ===")
    for row_start in range(0, min(len(vals), max_bytes), 16):
        row = vals[row_start:row_start + 16]
        hex_part = " ".join(f"{b:02X}" for _, b in row)
        asc_part = "".join(chr(b) if 0x20 <= b <= 0x7e else "." for _, b in row)
        print(f"  {row_start:4d}: {hex_part:<48}  {asc_part}")


def print_bytes_with_time(decoded, max_show=120, gap_thresh=3.0):
    print(f"\n{'T(ms)':>9}  {'HEX':>4}  {'Dec':>3}  Stop")
    print("-" * 35)
    prev_t = decoded[0][0] if decoded else 0
    for t, b, s in decoded[:max_show]:
        if t - prev_t > gap_thresh:
            print(f"\n  --- GAP {t - prev_t:.1f}ms ---\n")
        print(f"{t:>9.3f}  {b:02X}  {b:>3d}  {'OK' if s else ''}")
        prev_t = t


def analyze_frames(decoded, only_ok=True, max_bytes=300):
    """Tenta detectar tamanho de frame por repetição de padroes."""
    from collections import Counter
    vals = [b for _, b, s in decoded if (not only_ok or s)][:max_bytes]

    print(f"\n=== ANALISE DE FRAMES ===")
    for n in [2, 3, 4, 5, 6]:
        frames = [tuple(vals[i:i + n]) for i in range(0, len(vals) - n, n)]
        cnt = Counter(frames)
        top3 = cnt.most_common(3)
        frms = "  |  ".join(f"[{' '.join(f'{b:02X}' for b in fr)}]x{c}" for fr, c in top3)
        print(f"  N={n}: {frms}")


def analyze_inter_byte_gaps(decoded, only_ok=True, gap_thresh=2.0, top_n=20):
    """Analisa os gaps maiores entre bytes para inferir estrutura de mensagem."""
    vals = [(t, b) for t, b, s in decoded if (not only_ok or s)]
    gaps = []
    for i in range(1, len(vals)):
        g = vals[i][0] - vals[i - 1][0]
        if g > gap_thresh:
            ctx_b = [vals[j][1] for j in range(max(0, i - 3), i)]
            ctx_a = [vals[j][1] for j in range(i, min(len(vals), i + 3))]
            gaps.append((g, vals[i - 1][0], ctx_b, ctx_a))

    # Histograma de gaps
    from collections import Counter
    hist = Counter(round(g) for g, *_ in gaps)
    print(f"\n=== HISTOGRAMA DE GAPS (>{gap_thresh}ms) ===")
    for gsize in sorted(hist):
        bar = "#" * min(40, hist[gsize])
        print(f"  {gsize:3d}ms: {hist[gsize]:3d}  {bar}")

    # Padrao de gap
    print(f"\n=== PRIMEIROS {top_n} GAPS ===")
    for g, t, cb, ca in gaps[:top_n]:
        hex_b = " ".join(f"{b:02X}" for b in cb)
        hex_a = " ".join(f"{b:02X}" for b in ca)
        print(f"  t={t:.1f}ms  gap={g:.1f}ms  | ...{hex_b} || {hex_a}...")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\johan\Documents\yamaha funcionando.txt"
    force_baud = int(sys.argv[2]) if len(sys.argv) > 2 else None

    print(f"Carregando {path} ...")
    data = load_data(path)
    T_us = T_TOTAL_S * 1e6 / len(data)
    print(f"Amostras: {len(data)} | T: {T_us:.3f} us | Fs: {1e6 / T_us:.0f} Hz")

    bits = digitize(data, THRESHOLD)

    # Localizar inicio do sinal util
    start_sample = 0
    for i in range(1, len(bits) - 10):
        if bits[i] == 1 and all(bits[i + j] == 1 for j in range(5)):
            start_sample = i
            break
    print(f"Sinal ativo a partir de: t={start_sample * T_us / 1000:.2f} ms")

    # Scan de baud rates
    print("\n=== SCAN DE BAUD RATES (bit-center sampling) ===")
    extra_bauds = [4800, 7812, 8192, 9600, 10400, 14400, 15625, 16000, 16040, 19200, 28800]
    best_pct, best_baud, best_decoded = scan_bauds(bits, T_us, start=start_sample, bauds=extra_bauds)

    if force_baud:
        best_baud = force_baud
        best_decoded = decode_all(bits, T_us, force_baud, start=start_sample)
        ok = sum(1 for _, _, s in best_decoded if s)
        print(f"Forcado: {best_baud} baud  ({100*ok/len(best_decoded):.1f}% OK, {len(best_decoded)} bytes)")

    # Mostrar resultados do melhor baud
    print_bytes_with_time(best_decoded, max_show=80, gap_thresh=3.0)
    print_hex_stream(best_decoded, only_ok=True, max_bytes=200)
    analyze_frames(best_decoded, only_ok=True, max_bytes=300)
    analyze_inter_byte_gaps(best_decoded, only_ok=True, gap_thresh=3.0, top_n=15)


if __name__ == "__main__":
    main()
