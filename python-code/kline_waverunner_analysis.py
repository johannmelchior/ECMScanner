"""
Analise K-line para Yamaha WaveRunner (SEM assuncoes de protocolo de moto).
Identifica frame structure, timing, canais e valores brutos.
Usage: python kline_waverunner_analysis.py <arquivo.txt> [baud]
"""
import sys
from collections import Counter
from statistics import mean, median

def load_oscilloscope(fname):
    with open(fname, 'r') as f:
        lines = f.readlines()
    clock_s = size = None
    header_end = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('#CLOCK='): clock_s = float(s.split('=')[1].split()[0])
        elif s.startswith('#SIZE='): size = int(s.split('=')[1])
        elif s and not s.startswith('#'): header_end = i; break
    sample_rate = size / clock_s
    data = []
    for line in lines[header_end:]:
        s = line.strip()
        if s:
            try: data.append(float(s))
            except: pass
    digital = [1 if v >= 2.0 else 0 for v in data]
    print(f'Arquivo: {fname}')
    print(f'Amostras: {size}  Clock: {clock_s}s  Fs: {sample_rate:.0f} Hz  T: {1e6/sample_rate:.3f}us')
    return digital, sample_rate

def decode_uart(digital, sample_rate, baud):
    bit_samples = sample_rate / baud
    raw_bytes = []
    i = 1
    while i < len(digital) - int(11 * bit_samples):
        if digital[i-1] == 1 and digital[i] == 0:
            # Start bit detectado
            bits = []
            for b in range(8):
                sp = int(i + (b + 1.5) * bit_samples)
                if sp >= len(digital): break
                bits.append(digital[sp])
            stop_pos = int(i + 9.5 * bit_samples)
            if len(bits) == 8 and stop_pos < len(digital):
                byte_val = sum(bit << pos for pos, bit in enumerate(bits))
                stop_ok = digital[stop_pos]
                raw_bytes.append((i / sample_rate * 1000, byte_val, stop_ok))
            i += int(10 * bit_samples)
            continue
        i += 1
    return raw_bytes

def analyze(fname, baud=15625):
    digital, sample_rate = load_oscilloscope(fname)
    bit_us = 1e6 / baud
    byte_us = 10 * bit_us

    print(f'\nBaud: {baud}  bit={bit_us:.1f}us  byte={byte_us:.0f}us')

    raw_bytes = decode_uart(digital, sample_rate, baud)
    ok = sum(1 for _,_,s in raw_bytes if s == 1)
    err = sum(1 for _,_,s in raw_bytes if s != 1)
    print(f'Bytes: {len(raw_bytes)} total  OK={ok} ({100*ok/max(1,len(raw_bytes)):.1f}%)  ERR={err}')

    # ----------------------------------------------------------------
    # 1. Analise de timing: gaps apos 0xF8
    # ----------------------------------------------------------------
    print('\n=== TIMING APOS BYTE F8 (DASH -> ECU delay) ===')
    gaps_after_req = []
    for j in range(1, len(raw_bytes)):
        t0, b0, _ = raw_bytes[j-1]
        t1, b1, _ = raw_bytes[j]
        gap_us = (t1 - t0) * 1000
        if b0 == 0xF8:
            gaps_after_req.append(gap_us)

    if gaps_after_req:
        print(f'  Amostras: {len(gaps_after_req)}')
        print(f'  Media: {mean(gaps_after_req):.0f}us = {mean(gaps_after_req)/bit_us:.1f} bit-times')
        print(f'  Mediana: {median(gaps_after_req):.0f}us')
        print(f'  Min: {min(gaps_after_req):.0f}us  Max: {max(gaps_after_req):.0f}us')
        rounded = Counter(round(g/200)*200 for g in gaps_after_req)
        print('  Distribuicao (arredondado 200us):')
        for g, cnt in sorted(rounded.items())[:10]:
            bar = '#' * min(cnt, 50)
            print(f'    {g:6.0f}us | {cnt:4d} | {bar}')

    # ----------------------------------------------------------------
    # 2. Todos os bytes que seguem 0xF8 (resposta ECU)
    # ----------------------------------------------------------------
    print('\n=== BYTES APOS 0xF8 (primeiros bytes da resposta ECU) ===')
    first_after_req = []
    for j in range(1, len(raw_bytes)):
        t0, b0, _ = raw_bytes[j-1]
        t1, b1, _ = raw_bytes[j]
        gap_us = (t1 - t0) * 1000
        if b0 == 0xF8 and gap_us < 10000:
            first_after_req.append(b1)
    dist = Counter(first_after_req)
    for v, cnt in sorted(dist.items(), key=lambda x: -x[1])[:15]:
        b7 = (v >> 7) & 1
        base = v & 0x7F
        bar = '#' * min(cnt, 50)
        print(f'  0x{v:02X} = {v:3d}  bit7={b7} base=0x{base:02X}({base:2d})  {cnt:4d}x | {bar}')

    # ----------------------------------------------------------------
    # 3. Estrutura de transacoes: F8 -> XX -> YY
    # ----------------------------------------------------------------
    print('\n=== TRIPLAS: F8 -> byte1 -> byte2 (transacao completa) ===')
    triplas = Counter()
    for j in range(len(raw_bytes)-2):
        t0, b0, _ = raw_bytes[j]
        t1, b1, _ = raw_bytes[j+1]
        t2, b2, _ = raw_bytes[j+2]
        g1 = (t1-t0)*1000  # us
        g2 = (t2-t1)*1000  # us
        if b0 == 0xF8 and g1 < 10000 and g2 < 5000 and b1 != 0xF8:
            triplas[(b1, b2)] += 1

    print('  chan  val   bit7  base   count')
    for (b1, b2), cnt in sorted(triplas.items(), key=lambda x: -x[1])[:20]:
        b7 = (b2 >> 7) & 1
        base = b2 & 0x7F
        print(f'  0x{b1:02X}  0x{b2:02X}  [{b7}]   0x{base:02X}={base:3d}   {cnt}x')

    # ----------------------------------------------------------------
    # 4. Analise de canais conhecidos
    # ----------------------------------------------------------------
    print('\n=== CANAIS DETECTADOS E SEUS VALORES ===')
    channels = {}
    for j in range(len(raw_bytes)-1):
        t0, b0, _ = raw_bytes[j]
        t1, b1, _ = raw_bytes[j+1]
        gap_us = (t1-t0)*1000
        # Se b0 nao e F8 nem FF (canal) e b1 e o valor
        if b0 not in (0xF8, 0xFF) and gap_us < 3000:
            if b0 not in channels:
                channels[b0] = []
            channels[b0].append(b1 & 0x7F)  # remover bit7

    for ch in sorted(channels.keys()):
        vals = channels[ch]
        dist = Counter(vals)
        dominant = dist.most_common(1)[0]
        print(f'  Canal 0x{ch:02X} ({ch:3d}): {len(vals):4d} ocorrencias  dom=0x{dominant[0]:02X}({dominant[0]:3d}) [{dominant[1]}x]  range=[{min(vals)},{max(vals)}]')

    # ----------------------------------------------------------------
    # 5. RESUMo: hipoteses para RPM (sem assumir protocolo de moto)
    # ----------------------------------------------------------------
    print('\n=== HIPOTESES PARA DECODIFICACAO (WaveRunner) ===')
    # Valor dominante do canal principal
    if 0x1A in channels:
        vals_1a = channels[0x1A]
        dom = Counter(vals_1a).most_common(1)[0][0]
        print(f'  Canal 0x1A valor dominante: {dom} (0x{dom:02X})')
        print(f'  Se unit = RPM/25:  {dom*25} rpm (WaveRunner idle tipico: 1000-1500 rpm)')
        print(f'  Se unit = RPM/20:  {dom*20} rpm')
        print(f'  Se unit = RPM/30:  {dom*30} rpm')
        print(f'  Se unit = RPM/50:  {dom*50} rpm (formula moto - pode NAO se aplicar)')
        print(f'  NOTA: WaveRunner precisa calibracao com RPM conhecido para confirmar formula')
    else:
        chan_list = sorted(channels.keys())
        print(f'  Canal 0x1A nao encontrado. Canais disponiveis: {[hex(c) for c in chan_list]}')

    # ----------------------------------------------------------------
    # 6. Verificar arquivo yam.txt (motor desligando/ligando)
    # ----------------------------------------------------------------
    print('\n=== DONE ===')

if __name__ == '__main__':
    fname = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\johan\Documents\yamaha funcionando.txt'
    baud  = int(sys.argv[2]) if len(sys.argv) > 2 else 15625
    analyze(fname, baud)
