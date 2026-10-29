"""
Analisa arquivo de osciloscópio Yamaha K-line
Decodifica canais e distribui valores para correlação com RPM

Uso:
  python kline_rpm_analysis.py [arquivo] [baud]      - analise completa
  python kline_rpm_analysis.py [arquivo] auto        - mede baud real a partir das bordas
"""
import sys
from collections import Counter

fname = sys.argv[1] if len(sys.argv) > 1 else "yamaha funcionando.txt"
baud_arg = sys.argv[2] if len(sys.argv) > 2 else "15625"
auto_detect = baud_arg.strip().lower() == "auto"
baud = 0 if auto_detect else int(baud_arg)

print(f"Carregando: {fname}")

with open(fname, 'r') as f:
    lines = f.readlines()

clock_s = None
size = None
header_end = 0
for i, line in enumerate(lines):
    s = line.strip()
    if s.startswith('#CLOCK='):
        clock_s = float(s.split('=')[1].split()[0])
    elif s.startswith('#SIZE='):
        size = int(s.split('=')[1])
    elif s and not s.startswith('#'):
        header_end = i
        break

sample_rate = size / clock_s
print(f"Fs={sample_rate:.0f} Hz  Duracao={clock_s}s  Amostras={size}")

# -----------------------------------------------------------------------
# Auto-detecção de baud rate a partir das bordas do sinal K-Line
# -----------------------------------------------------------------------
# K-Line é UART NRZ: cada byte = start(0) + 8 bits + stop(1).
# A menor janela possível entre duas transições = 1 bit-period.
# Coletamos todos os intervalos entre bordas, pegamos os mais curtos
# (que correspondem a 1 bit), e calculamos baud = Fs / bit_period.
def measure_baud_from_edges(d, fs, min_edge_gap=3):
    """Mede baud rate real medindo intervalos entre bordas de transição.

    Estratégia:
      1. Encontra todas as posições de transição (0→1 ou 1→0).
      2. Calcula os intervalos em amostras entre transições consecutivas.
      3. Agrupa por proximidade (histograma); o menor grupo não-trivial
         é 1 bit-period.
      4. Baud = Fs / bit_period_samples.

    Retorna (baud_estimado, bit_period_samples, confianca_pct).
    """
    edges = []
    for i in range(1, len(d)):
        if d[i] != d[i - 1]:
            edges.append(i)

    if len(edges) < 20:
        return None, None, 0.0

    gaps = [edges[i+1] - edges[i] for i in range(len(edges) - 1)]
    # Filtra gaps muito curtos (ruído) e muito longos (silêncio entre frames)
    max_gap = int(fs * 0.002)  # ignora silêncios > 2 ms (entre frames)
    gaps = [g for g in gaps if g >= min_edge_gap and g <= max_gap]

    if not gaps:
        return None, None, 0.0

    # Histograma de 1 amostra de resolução, suavizado por bucket de 3 amostras
    min_g, max_g = min(gaps), max(gaps)
    bucket = max(1, int(fs / 200000))  # ~5 µs de resolução
    hist = Counter(g // bucket for g in gaps)

    # O menor pico não-trivial é 1x bit-period
    # Procura o pico de menor índice com contagem relevante (>=5% do total)
    total_gaps = len(gaps)
    threshold = max(5, total_gaps * 0.03)
    sorted_buckets = sorted(hist.items())
    bit_bucket = None
    for bkt, cnt in sorted_buckets:
        if cnt >= threshold:
            bit_bucket = bkt
            break

    if bit_bucket is None:
        return None, None, 0.0

    # Refina: dentro do bucket vencedor, pega a mediana dos gaps próximos
    center = bit_bucket * bucket + bucket // 2
    nearby = [g for g in gaps if abs(g - center) <= bucket * 2]
    if not nearby:
        return None, None, 0.0

    nearby_sorted = sorted(nearby)
    bit_period = nearby_sorted[len(nearby_sorted) // 2]  # mediana
    if bit_period == 0:
        return None, None, 0.0

    baud_est = fs / bit_period
    confidence = len(nearby) / total_gaps * 100.0

    # Verifica se o bit_period é consistente com múltiplos inteiros
    # (gaps de 2, 3, 4 bits devem ser ~2x, 3x, 4x bit_period)
    multiples_ok = 0
    for n in range(2, 12):
        expected = bit_period * n
        window = bit_period * 0.12  # tolerância 12%
        count_mult = sum(1 for g in gaps if abs(g - expected) <= window)
        if count_mult >= 3:
            multiples_ok += 1

    return baud_est, bit_period, confidence, multiples_ok, len(edges)


if auto_detect:
    print("Modo: AUTO-DETECÇÃO de baud rate a partir das bordas")
else:
    print(f"Bit width @ {baud} baud: {sample_rate/baud:.2f} amostras")

data = []
for line in lines[header_end:]:
    s = line.strip()
    if s:
        try:
            data.append(float(s))
        except:
            pass

digital = [1 if v >= 2.0 else 0 for v in data]
bit_samples = sample_rate / baud

def decode_byte_at(d, start_idx):
    bits = []
    for b in range(8):
        sp = int(start_idx + (b + 1.5) * bit_samples)
        if sp >= len(d):
            return None, None
        bits.append(d[sp])
    stop_pos = int(start_idx + 9.5 * bit_samples)
    if stop_pos >= len(d):
        return None, None
    byte_val = 0
    for i, b in enumerate(bits):
        byte_val |= (b << i)
    return byte_val, d[stop_pos]

bytes_found = []
i = 1
while i < len(digital) - int(11 * bit_samples):
    if digital[i-1] == 1 and digital[i] == 0:
        bv, stop = decode_byte_at(digital, i)
        if bv is not None and stop == 1:
            bytes_found.append((i / sample_rate * 1000, bv))
            i += int(10 * bit_samples)
            continue
    i += 1

print(f"Bytes decodificados: {len(bytes_found)}")
print()

seq = bytes_found

# Coletar padrões F8 -> canal -> valor
channel_vals = {}  # canal -> [(t_ms, valor)]
all_channels = Counter()

for j in range(len(seq) - 2):
    if seq[j][1] == 0xF8:
        ch = seq[j+1][1]
        val = seq[j+2][1]
        if ch not in (0xF8, 0xFF):
            all_channels[ch] += 1
            if ch not in channel_vals:
                channel_vals[ch] = []
            channel_vals[ch].append((seq[j+2][0], val))

print("=== TODOS OS CANAIS DETECTADOS ===")
for ch, cnt in sorted(all_channels.items(), key=lambda x: -x[1]):
    vals = [v for _, v in channel_vals.get(ch, [])]
    if vals:
        print(f"  Canal 0x{ch:02X} ({ch:3d}): {cnt:4d}x  "
              f"min={min(vals)} max={max(vals)} media={sum(vals)/len(vals):.1f}")
    else:
        print(f"  Canal 0x{ch:02X} ({ch:3d}): {cnt:4d}x")

print()

# Análise detalhada por canal
for ch in sorted(channel_vals.keys()):
    entries = channel_vals[ch]
    vals = [v for _, v in entries]
    dist = Counter(vals)
    print(f"=== CANAL 0x{ch:02X} ({ch}) — {len(entries)} ocorrencias ===")
    print(f"  Min={min(vals)} (0x{min(vals):02X})  "
          f"Max={max(vals)} (0x{max(vals):02X})  "
          f"Media={sum(vals)/len(vals):.1f}")
    print("  Distribuicao de valores:")
    for v, cnt in sorted(dist.items()):
        bar = '#' * min(cnt, 60)
        pct = cnt / len(vals) * 100
        print(f"    0x{v:02X} = {v:3d}  x{cnt:4d} ({pct:5.1f}%)  {bar}")
    print()

# Se canal 0x1A existe, tentar estimar RPM
if 0x1A in channel_vals:
    print("=== HIPOTESE RPM PARA CANAL 0x1A ===")
    print("  Se 0x38=56 corresponde a ~1500rpm (lenta tipica Yamaha):")
    print(f"  Fator = 1500 / 56 = {1500/56:.1f} rpm/unidade")
    vals = [v for _, v in channel_vals[0x1A]]
    dist = Counter(vals)
    print()
    print("  Valor -> RPM estimado (assumindo 1500rpm @ 0x38=56):")
    factor = 1500 / 56
    for v, cnt in sorted(dist.items()):
        rpm = v * factor
        print(f"    0x{v:02X} = {v:3d} -> {rpm:.0f} rpm  x{cnt}")
    print()
    print("  Se 0x38=56 corresponde a ~1000rpm:")
    factor2 = 1000 / 56
    print("  Valor -> RPM estimado (@ 1000rpm):")
    for v, cnt in sorted(dist.items()):
        rpm = v * factor2
        print(f"    0x{v:02X} = {v:3d} -> {rpm:.0f} rpm  x{cnt}")
    print()
    print("  Se 0x38=56 corresponde a ~2000rpm:")
    factor3 = 2000 / 56
    print("  Valor -> RPM estimado (@ 2000rpm):")
    for v, cnt in sorted(dist.items()):
        rpm = v * factor3
        print(f"    0x{v:02X} = {v:3d} -> {rpm:.0f} rpm  x{cnt}")
