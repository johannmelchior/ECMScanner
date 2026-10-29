"""
_analyze_init_phase.py
Analisa SOMENTE a fase de inicializacao (0 -> ~400ms do arquivo)
para entender o que o painel envia para acordar a ECM.

No arquivo 'yamaha vx 110 inicializacao painel ecm.txt' a ECM
nao estava presente desde o inicio -- os primeiros pulsos sao
do PAINEL tentando acordar a ECM.
"""
import sys
from collections import Counter

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
    clock_s = float(header.get('CLOCK','2.0 S').split()[0])
    dt_us = clock_s * 1_000_000.0 / N
    vmin, vmax = min(data), max(data)
    th = (vmin + vmax) / 2.0
    bits = [1 if x > th else 0 for x in data]
    print('LOAD: N=%d  Fs=%.0fHz  dt=%.4fus  th=%.3fV' % (N, N/clock_s, dt_us, th))
    return bits, dt_us, N

def run_lengths(bits, dt_us, start_us=0, end_us=None, min_dur_us=30):
    """Extrai sequencias de runs (nivel, duracao) no intervalo [start_us, end_us]."""
    N = len(bits)
    i0 = int(start_us / dt_us)
    i1 = int(end_us / dt_us) if end_us else N
    i1 = min(i1, N)
    runs = []
    i = i0
    while i < i1:
        level = bits[i]
        j = i
        while j < i1 and bits[j] == level:
            j += 1
        dur = (j - i) * dt_us
        if dur >= min_dur_us:
            runs.append({'t': i * dt_us, 'level': level, 'dur_us': dur, 'samples': j-i})
        i = j
    return runs

def decode_uart_in_runs(runs, baud_candidates, dt_us):
    """
    Tenta decodificar bytes UART em pulsos LOW encontrados nos runs.
    Cada pulso LOW que dura ~10 bit-periods pode conter 1 byte UART.
    """
    for baud in baud_candidates:
        spb_us = 1_000_000.0 / baud   # microsegundos por bit
        print('\n--- Tentando baud %d (spb=%.1fus) ---' % (baud, spb_us))
        decoded = []
        for i, r in enumerate(runs):
            # procura transicao HIGH->LOW seguida de runs que formam um byte
            if r['level'] == 0:
                # verifica se duracao eh plausivel para 1 byte UART (8-11 bit-periods)
                nbits_approx = r['dur_us'] / spb_us
                if 0.5 <= nbits_approx <= 12:
                    decoded.append((r['t'], r['dur_us'], nbits_approx))
        if decoded:
            print('  Pulsos LOW compativeis com 1 byte @ %d baud: %d' % (baud, len(decoded)))
            for (t, d, nb) in decoded[:20]:
                print('    t=%.3fms  dur=%.1fus  ~%.1f bits' % (t/1000, d, nb))

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        r'\\JOHANN\Documents\projetoCAN\yamaha vx 110 inicializacao painel ecm.txt'

    bits, dt_us, N = load_oscope(path)
    total_us = N * dt_us
    print('Duracao total: %.3fms\n' % (total_us / 1000))

    # =====================================================================
    # FASE 1: Visao geral dos runs em todo o arquivo (resolucao baixa)
    # Separar regiao esparsa (init) da regiao densa (ECM transmitindo)
    # =====================================================================
    print('=== RUNS LONGOS (>500us) em todo o arquivo ===')
    runs_all = run_lengths(bits, dt_us, min_dur_us=500)
    print('Qtd runs > 500us: %d' % len(runs_all))
    print()
    print('t_ms        level  dur_ms')
    gaps_between = []
    prev_t = None
    for r in runs_all[:80]:
        t_ms = r['t'] / 1000
        d_ms = r['dur_us'] / 1000
        marker = ' *** PAUSA LONGA ***' if d_ms > 2 else ''
        print('  %8.3fms  %s  %8.3fms%s' % (t_ms, 'HIGH' if r['level'] else ' LOW', d_ms, marker))

    # =====================================================================
    # FASE 2: Encontrar o ponto onde a comunicacao densa começa
    # (= ponto onde nao ha mais runs > 2ms)
    # =====================================================================
    print()
    print('=== IDENTIFICANDO PONTO DE INICIO DA TRANSMISSAO ECM ===')
    # Janelas de 50ms: contar cruzamentos em cada janela
    window_us = 50_000
    n_windows = int(total_us / window_us)
    crossings_per_window = []
    prev = bits[0]
    cx = [0] * n_windows
    for idx in range(N-1):
        wid = int(idx * dt_us / window_us)
        if wid < n_windows and bits[idx] != bits[idx+1]:
            cx[wid] += 1
    print('Janelas 50ms: cruzamentos por janela (primeiras 60 janelas = 3s):')
    transition_window = None
    for wid in range(min(n_windows, 60)):
        t_ms = wid * 50
        bar = '#' * min(50, cx[wid] // 2)
        marker = ''
        if transition_window is None and cx[wid] > 100:
            transition_window = wid
            marker = '  <--- ECM COMECA AQUI'
        print('  %4dms-%4dms  %4d  %s%s' % (t_ms, t_ms+50, cx[wid], bar, marker))

    if transition_window is not None:
        t_ecm_start = transition_window * 50_000  # us
        print('\nECM comeca a transmitir em aproximadamente: %.1fms' % (t_ecm_start/1000))
    else:
        t_ecm_start = total_us  # nao encontrado
        print('\nECM start nao identificado neste arquivo')

    # =====================================================================
    # FASE 3: Analisar SOMENTE a fase de INIT (antes do ECM start)
    # =====================================================================
    print()
    print('=== FASE INIT: pulsos enviados pelo PAINEL ===')
    init_end_us = t_ecm_start + 10_000  # um pouco apos o inicio
    runs_init = run_lengths(bits, dt_us, end_us=min(init_end_us, total_us), min_dur_us=30)
    
    # Filtrar runs significativos (>50us, <50ms)
    sig_runs = [r for r in runs_init if 50 <= r['dur_us'] <= 50_000]
    
    print('Runs significativos (50us-50ms) na fase init: %d' % len(sig_runs))
    print()
    print('t_ms        level  dur_us     dur_ms')
    for r in sig_runs[:60]:
        t_ms = r['t'] / 1000
        d_us = r['dur_us']
        d_ms = d_us / 1000
        print('  %8.3fms  %s  %8.1fus  %6.3fms' % (
            t_ms, 'HIGH' if r['level'] else ' LOW', d_us, d_ms))

    # =====================================================================
    # FASE 4: Medir os periodos dos pulsos LOW (possiveis bits ou bytes)
    # =====================================================================
    low_runs = [r for r in sig_runs if r['level'] == 0]
    high_runs = [r for r in sig_runs if r['level'] == 1]
    
    if low_runs:
        low_durs = [r['dur_us'] for r in low_runs]
        print()
        print('=== PULSOS LOW na fase INIT ===')
        print('Qtd: %d' % len(low_durs))
        print('Duracoes (us): %s' % [round(d,1) for d in low_durs[:30]])
        # Histograma
        c = Counter(round(d/50)*50 for d in low_durs)
        print('Histograma (arredondado para 50us):')
        for k,v in sorted(c.items()):
            bar = '#' * v
            print('  %6.0fus: %3d  %s' % (k, v, bar))
        # Verificar se os pulsos correspondem a bits ou bytes a algum baud
        print()
        print('Se pulso LOW = 1 bit, baud =', [round(1e6/d) for d in sorted(low_durs)])
        
    if high_runs:
        high_durs = [r['dur_us'] for r in high_runs]
        print()
        print('=== PULSOS HIGH na fase INIT ===')
        print('Qtd: %d' % len(high_durs))
        print('Duracoes (us): %s' % [round(d,1) for d in high_durs[:30]])
        
    # =====================================================================
    # FASE 5: Decoder UART na fase de INIT com multiplos bauds
    # =====================================================================
    print()
    print('=== DECODER UART NA FASE INIT ===')
    # Pegar todos os bits raw na fase init
    i_end = min(int(init_end_us / dt_us), N)
    bits_init = bits[:i_end]
    
    for baud in [15625, 16040, 16368, 10400, 9600, 1200, 2400]:
        spb = (1_000_000.0 / baud) / dt_us  # amostras por bit
        out = []
        i = 1
        while i < len(bits_init) - int(spb*11):
            if bits_init[i-1] == 1 and bits_init[i] == 0:
                val = 0
                ok = True
                for bit in range(8):
                    idx = int(i + (0.5 + 1 + bit) * spb)
                    if idx >= len(bits_init):
                        ok = False; break
                    if bits_init[idx]:
                        val |= (1 << bit)
                stop_idx = int(i + 9.5 * spb)
                if ok and stop_idx < len(bits_init) and bits_init[stop_idx] == 1:
                    t_ms = i * dt_us / 1000.0
                    out.append((t_ms, val))
                    i = int(i + spb * 10)
                    continue
            i += 1
        if out:
            vals = [v for (t,v) in out]
            cnt = Counter(vals)
            ratio = len([v for v in vals if v not in (0x00, 0xFF, 0xFE)]) / max(1, len(vals))
            print('baud %5d: %3d bytes  ratio_nontrivial=%.2f' % (baud, len(out), ratio))
            print('  bytes:', ' '.join('%02X' % v for v in vals[:40]))
            print('  top5:', cnt.most_common(5))

if __name__ == '__main__':
    main()
