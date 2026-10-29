"""
_decode_kline_raw.py — Decoder PWM para protocolo K-Line Yamaha WaveRunner VX110

HIPÓTESE CONFIRMADA:
- Fs (osciloscópio) = 523776 Hz = EXATAMENTE 32 × 16368 baud
- 16368 baud UART: bytes dominantes FE (11111110) e 20 (00100000)
- FE = duty cycle 87.5% HIGH = bit "1" do protocolo real
- 20 = duty cycle 12.5% HIGH = bit "0" do protocolo real
- Real baud = 16368 / 10 = 1636.8 Hz (1 byte UART = 1 bit real)
- Cada bit real = exatamente 320 amostras do osciloscópio

ENCODING PWM (observado):
  Bit "1" → pulso LOW curto (~122µs = 2 bits UART) + HIGH longo (~488µs)
             decode UART @ 16368 → byte 0xFE = 11111110
  Bit "0" → pulso LOW longo (~366µs = 6 bits UART) + HIGH curto + LOW + HIGH(stop)
             decode UART @ 16368 → byte 0x20 = 00100000
  Transição → bytes intermediários: 0xA0, 0xB2, 0x96, 0x92, etc.

MÉTODO:
  1. Threshold o sinal analógico → bitstream binário @ Fs
  2. Agrupar em janelas de 320 amostras = 1 bit real
  3. Amostrar no centro de cada janela → bit real 0 ou 1
  4. Buscar bytes UART no bitstream real (start=0, 8 bits LSB-first, stop=1)
"""

import sys
from collections import Counter, defaultdict


def load_oscope(path):
    """Carrega arquivo de osciloscópio .txt — retorna (bits[], dt_us, N, header)"""
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    header = {}
    data = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith('#'):
            body = s[1:]
            if '=' in body:
                k, v = body.split('=', 1)
                header[k.strip().upper()] = v.strip()
            continue
        try:
            data.append(float(s))
        except:
            pass
    N = len(data)
    clock_s = float(header.get('CLOCK', '2.0 S').split()[0])
    dt_us = clock_s * 1_000_000.0 / N
    vmin, vmax = min(data), max(data)
    th = (vmin + vmax) / 2.0
    bits = [1 if x > th else 0 for x in data]
    print(f"LOAD: N={N} Fs={N/clock_s:.0f}Hz dt={dt_us:.4f}µs")
    print(f"      vmin={vmin:.3f}V vmax={vmax:.3f}V th={th:.3f}V")
    return bits, dt_us, N, header


def find_crossings(bits, dt_us, max_show=40):
    """Encontra cruzamentos de threshold e mostra intervalos."""
    crossings = []
    for i in range(len(bits) - 1):
        if bits[i] != bits[i + 1]:
            crossings.append(i)
    intervals = [(crossings[i+1] - crossings[i]) * dt_us for i in range(min(max_show, len(crossings)-1))]
    print(f"\nCROSSINGS: total={len(crossings)}")
    print(f"  first{min(max_show, len(intervals))} intervals (µs): {[round(x, 1) for x in intervals[:max_show]]}")
    return crossings


def decode_real_bitstream(bits, dt_us, real_baud=1636.8, start_sample=None):
    """
    Decodifica o bitstream de nível real (não UART) amostrando no centro
    de cada janela de (1/real_baud) segundos.

    start_sample: índice da primeira borda de descida (início do 1º start bit).
                  Se None, detecta automaticamente o 1º falling edge.
    """
    spb = (1_000_000.0 / real_baud) / dt_us  # amostras por bit real ≈ 320
    spb_int = round(spb)
    print(f"\nDECODE_RAW: real_baud={real_baud:.1f}Hz  spb={spb:.2f} (~{spb_int} amostras)")

    # Detectar 1ª borda de descida (idle HIGH → start bit LOW)
    if start_sample is None:
        for i in range(len(bits) - 1):
            if bits[i] == 1 and bits[i + 1] == 0:
                start_sample = i + 1
                break
    if start_sample is None:
        print("  ERRO: nenhuma borda de descida encontrada")
        return [], spb

    print(f"  Início de decodificação: sample {start_sample}  t={start_sample*dt_us/1000:.3f}ms")

    # Amostrar cada janela no centro
    real_bits = []
    t = start_sample
    N = len(bits)
    while t + spb_int <= N:
        mid = int(t + spb * 0.5)
        if mid < N:
            real_bits.append((t, bits[mid]))
        t += spb_int

    print(f"  Bits reais decodificados: {len(real_bits)}")
    return real_bits, spb


def find_uart_bytes(real_bits_list, real_baud=1636.8, dt_us=1.9092, spb=320):
    """
    Encontra bytes UART no bitstream de nível real.
    Cada elemento de real_bits_list = (sample_index, bit_value).
    UART: idle=1, start=0, bit0-bit7 LSB-first, stop=1
    """
    bits_only = [b for (_, b) in real_bits_list]
    samples_only = [s for (s, _) in real_bits_list]
    n = len(bits_only)
    decoded = []
    i = 1
    while i < n - 10:
        # Detectar borda descendo: era 1, agora é 0 → start bit
        if bits_only[i - 1] == 1 and bits_only[i] == 0:
            # Extrair 8 data bits + stop bit
            if i + 9 >= n:
                break
            data_bits = bits_only[i + 1: i + 9]  # 8 bits
            stop = bits_only[i + 9]
            if stop == 1:
                # Montar byte (LSB first)
                val = 0
                for b, bit in enumerate(data_bits):
                    if bit:
                        val |= (1 << b)
                t_ms = samples_only[i] * dt_us / 1000.0
                decoded.append((t_ms, val))
                i += 10  # pular para próximo byte
                continue
        i += 1
    return decoded


def group_frames(decoded_bytes, gap_ms=20.0):
    """Agrupa bytes decodificados em frames por gap de tempo."""
    if not decoded_bytes:
        return []
    frames = []
    current = [decoded_bytes[0]]
    for tup in decoded_bytes[1:]:
        if tup[0] - current[-1][0] > gap_ms:
            frames.append(current)
            current = [tup]
        else:
            current.append(tup)
    frames.append(current)
    return frames


def analyze_bytes_as_uart(decoded_bytes, dt_us, spb):
    """
    Análise alternativa: mapeia bytes UART do nível 16368 para bits reais,
    usando: FE → 1,  20 → 0,  FF → 1 (solid high),  00 → 0,  outros → -1 (transição)
    """
    UART_TO_BIT = {
        0xFF: 1, 0xFE: 1, 0x7F: 1,
        0x00: 0, 0x20: 0, 0x01: 0,
    }
    bits_out = []
    for (t, b) in decoded_bytes:
        mapped = UART_TO_BIT.get(b, -1)  # -1 = byte de transição
        bits_out.append((t, b, mapped))
    return bits_out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        r"\\JOHANN\Documents\projetoCAN\yamaha vx 110 inicializacao painel ecm.txt"

    # ── 1. Carregar ──────────────────────────────────────────────────────────
    bits, dt_us, N, header = load_oscope(path)

    # ── 2. Crossings ─────────────────────────────────────────────────────────
    crossings = find_crossings(bits, dt_us, max_show=30)

    # ── 3. Decodificar bitstream real (1636.8 Hz, janela 320 amostras) ───────
    #   Testa alguns baud rates candidatos
    for real_baud, label in [
        (1636.8, '16368/10'),
        (1562.5, '15625/10'),
        (1302.1, '16368/12.57?'),  # para 4-byte frame @ 38558µs: 38558/(4*10) = 963.95 ← errado
    ]:
        real_bits, spb = decode_real_bitstream(bits, dt_us, real_baud=real_baud)
        decoded = find_uart_bytes(real_bits, real_baud=real_baud, dt_us=dt_us, spb=spb)
        frames = group_frames(decoded, gap_ms=20.0)

        print(f"\n{'='*60}")
        print(f"REAL_BAUD={real_baud:.1f} ({label})")
        print(f"  Bytes decodificados: {len(decoded)}")
        print(f"  Frames (gap>20ms): {len(frames)}")
        if frames:
            sizes = [len(f) for f in frames]
            print(f"  Tamanhos de frames: {sorted(Counter(sizes).items())}")
        print(f"\n  Primeiros 60 bytes:")
        row = []
        for (t, v) in decoded[:60]:
            row.append(f"{v:02X}")
        print("  " + " ".join(row))

        if frames:
            print(f"\n  FRAME_HIST:")
            for idx, frame in enumerate(frames[:20]):
                bytelist = " ".join(f"{b:02X}" for (_, b) in frame)
                t0 = frame[0][0]
                t1 = frame[-1][0]
                dur = t1 - t0 if len(frame) > 1 else 0
                print(f"  [{idx+1:02d}] t={t0:.1f}ms dur={dur:.1f}ms len={len(frame)} : {bytelist}")

        # Análise de N-grams dos bytes reais
        if decoded:
            vals = [v for (_, v) in decoded]
            c2 = Counter(zip(vals, vals[1:]))
            c1 = Counter(vals)
            print(f"\n  TOP10 bytes: {c1.most_common(10)}")
            print(f"  TOP10 bigrams: {c2.most_common(10)}")

        print()

    # ── 4. Análise de run-lengths na camada física ────────────────────────────
    print("\n" + "="*60)
    print("RUN_LENGTH ANALYSIS (camada física):")
    runs = []
    i = 0
    while i < N - 1:
        level = bits[i]
        j = i
        while j < N and bits[j] == level:
            j += 1
        dur_us = (j - i) * dt_us
        runs.append((level, dur_us))
        i = j

    # Histograma de durações (apenas os primeiros 5000 runs)
    runs_analyze = runs[:5000]
    high_durs = [d for (l, d) in runs_analyze if l == 1]
    low_durs  = [d for (l, d) in runs_analyze if l == 0]

    def hist_bins(durs, bins=20, max_us=1500):
        if not durs:
            return {}
        step = max_us / bins
        hist = defaultdict(int)
        for d in durs:
            b = min(int(d / step), bins - 1)
            hist[b] += 1
        return {int(k * step): v for k, v in sorted(hist.items())}

    print(f"\n  HIGH durations histogram (µs → count):")
    for k, v in sorted(hist_bins(high_durs).items()):
        bar = '#' * min(60, v // max(1, len(high_durs)//100))
        print(f"  {k:5d}: {v:5d} {bar}")

    print(f"\n  LOW durations histogram (µs → count):")
    for k, v in sorted(hist_bins(low_durs).items()):
        bar = '#' * min(60, v // max(1, len(low_durs)//100))
        print(f"  {k:5d}: {v:5d} {bar}")

    print(f"\n  Maior HIGH: {max(high_durs):.1f}µs  Maior LOW: {max(low_durs):.1f}µs")
    print(f"  Top5 HIGH: {sorted(high_durs, reverse=True)[:5]}")
    print(f"  Top5 LOW:  {sorted(low_durs, reverse=True)[:5]}")

    # Distribuição de durações curtas (< 700µs => dentro de 1 bit real)
    short_high = [d for d in high_durs if d < 700]
    short_low  = [d for d in low_durs  if d < 700]
    if short_high:
        avg_sh = sum(short_high)/len(short_high)
        print(f"\n  HIGH curtos (<700µs): n={len(short_high)} avg={avg_sh:.1f}µs")
    if short_low:
        avg_sl = sum(short_low)/len(short_low)
        typical_low_counts = Counter(round(d/dt_us) for d in short_low)
        # Most common low pulse durations in samples
        top_low = sorted(typical_low_counts.items(), key=lambda x: -x[1])[:10]
        print(f"  LOW curtos (<700µs): n={len(short_low)} avg={avg_sl:.1f}µs")
        print(f"  LOW durações mais comuns (amostras): {top_low}")


if __name__ == '__main__':
    main()
