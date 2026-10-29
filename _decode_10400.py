"""
_decode_10400.py — Decoder UART 10400 baud otimizado para Fs=209510Hz
Usa dt=4.773us, spb~20.15 amostras por bit.
Analisa qualquer arquivo de osciloscopio.
"""
import sys
from collections import Counter, defaultdict

def load_oscope(path):
    header = {}
    data = []
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for ln in f:
            s = ln.strip()
            if not s: continue
            if s.startswith('#'):
                body = s[1:]
                if '=' in body:
                    k,v = body.split('=',1)
                    header[k.strip().upper()] = v.strip()
                continue
            try: data.append(float(s))
            except: pass
    N = len(data)
    clock_s = float(header.get('CLOCK','5.0 S').split()[0])
    dt_us = clock_s * 1_000_000.0 / N
    vmin, vmax = min(data), max(data)
    th = (vmin + vmax) / 2.0
    bits = [1 if x > th else 0 for x in data]
    print('LOAD: N=%d  CLOCK=%s  Fs=%.0fHz  dt=%.4fus  th=%.3fV' % (
        N, header.get('CLOCK'), N/clock_s, dt_us, th))
    return bits, dt_us, N

def decode_uart(bits, dt_us, baud, phase=0.5, polarity=0):
    """Decodifica UART no bitstream. Polarity=0: idle-HIGH."""
    N = len(bits)
    b = bits if polarity == 0 else [1-x for x in bits]
    spb = (1_000_000.0 / baud) / dt_us
    attempts = valid = 0
    out = []
    i = 1
    minlen = int(spb * 11) + 2
    while i < N - minlen:
        if b[i-1] == 1 and b[i] == 0:  # falling edge = start bit
            attempts += 1
            val = 0
            ok = True
            for bit in range(8):
                idx = int(i + (phase + 1 + bit) * spb)
                if idx >= N: ok = False; break
                if b[idx]: val |= (1 << bit)
            stop_idx = int(i + (phase + 9) * spb)
            if ok and stop_idx < N and b[stop_idx] == 1:
                valid += 1
                out.append((i * dt_us, val))
                i = int(i + spb * 10)
                continue
        i += 1
    ratio = valid / attempts if attempts else 0.0
    return out, attempts, valid, ratio

def group_frames(decoded, gap_us=3000.0):
    if not decoded: return []
    frames = [[decoded[0]]]
    for tup in decoded[1:]:
        if tup[0] - frames[-1][-1][0] > gap_us:
            frames.append([])
        frames[-1].append(tup)
    return frames

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r'\\JOHANN\Documents\projetoCAN\teste2.txt'

    bits, dt_us, N = load_oscope(path)

    # Varredura de bauds e fases para encontrar o melhor
    print('\n=== VARREDURA DE BAUD ===')
    best = None
    results = []
    for baud in [10400, 9600, 4800, 15625, 16368, 7812]:
        best_phase = None
        best_ratio = 0
        best_valid = 0
        for phase_i in range(10):  # 10 fases 0.05..0.95
            phase = 0.05 + phase_i * 0.1
            out, att, val, ratio = decode_uart(bits, dt_us, baud, phase=phase, polarity=0)
            if ratio > best_ratio or (ratio == best_ratio and val > best_valid):
                best_ratio = ratio
                best_phase = phase
                best_valid = val
                best_out = out
        results.append((baud, best_phase, best_ratio, best_valid, best_out))
        print('  baud=%5d  best_phase=%.2f  ratio=%.4f  valid=%d' % (
            baud, best_phase, best_ratio, best_valid))

    # Selecionar melhor
    results.sort(key=lambda x: (x[2], x[3]), reverse=True)
    baud, phase, ratio, valid, stream = results[0]
    print('\nMELHOR BAUD: %d  phase=%.2f  ratio=%.4f  valid=%d' % (baud, phase, ratio, valid))

    if not stream:
        print('Nenhum dado decodificado. Verifique o arquivo.')
        return

    # Analise com o melhor baud
    print('\n=== ANALISE COM BAUD=%d ===' % baud)
    spb = (1_000_000.0 / baud) / dt_us
    print('spb=%.2f amostras/bit' % spb)

    frames = group_frames(stream, gap_us=max(spb * 20, 2000))
    print('Frames (gap>%.0f us): %d' % (max(spb*20, 2000), len(frames)))

    # Histograma de tamanhos
    sizes = Counter(len(f) for f in frames)
    print('Tamanhos de frames: %s' % sorted(sizes.items()))

    # Primeiros 40 frames
    print('\n=== PRIMEIROS 40 FRAMES ===')
    for idx, frame in enumerate(frames[:40]):
        bytelist = ' '.join('%02X' % v for (_,v) in frame)
        t0 = frame[0][0] / 1000.0
        dur = (frame[-1][0] - frame[0][0]) / 1000.0
        gap_prev = ''
        if idx > 0:
            gap_prev = ' gap=%.2fms' % ((frame[0][0] - frames[idx-1][-1][0]) / 1000.0)
        print('[%03d] t=%.3fms%s len=%d : %s' % (idx+1, t0, gap_prev, len(frame), bytelist))

    # Estatisticas de bytes
    all_bytes = [v for (_,v) in stream]
    cnt = Counter(all_bytes)
    print('\n=== TOP 20 BYTES ===')
    for b_val, count in cnt.most_common(20):
        bar = '#' * min(40, count // max(1, len(all_bytes)//200))
        print('  0x%02X (%3d) = %s : %5d  %s' % (b_val, b_val, format(b_val, '08b'), count, bar))

    # Bigrams
    bigrams = Counter(zip(all_bytes, all_bytes[1:]))
    print('\n=== TOP 15 BIGRAMS ===')
    for (a,b_val), count in bigrams.most_common(15):
        print('  %02X %02X : %d' % (a, b_val, count))

    # Checksum analysis
    print('\n=== CHECKSUM ANALYSIS ===')
    for flen in [4, 5, 6, 7, 8]:
        filt = [f for f in frames if len(f) == flen]
        if len(filt) < 3: continue
        # testa XOR simples dos bytes
        xor_ok = sum(1 for f in filt
                     if (lambda blist: blist[-1] == (sum(blist[:-1]) & 0xFF))(
                         [v for (_,v) in f])) 
        sum_ok = sum(1 for f in filt
                     if (lambda blist: (sum(blist) & 0xFF) == 0)(
                         [v for (_,v) in f]))
        print('  len=%d  n=%d  checksum_last_byte_sum=%d/%.0f  sum_zero=%d/%.0f' % (
            flen, len(filt),
            xor_ok, len(filt),
            sum_ok, len(filt)))

    # Periodicidade
    print('\n=== PERIODICIDADE DOS FRAMES ===')
    if len(frames) >= 10:
        gaps = [(frames[i][0][0] - frames[i-1][0][0]) / 1000.0
                for i in range(1, min(50, len(frames)))]
        avg_gap = sum(gaps) / len(gaps)
        print('  Gap medio entre frames: %.2fms' % avg_gap)
        print('  Gaps (ms): %s' % [round(g,2) for g in gaps[:20]])

if __name__ == '__main__':
    main()
