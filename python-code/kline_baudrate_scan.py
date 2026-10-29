#!/usr/bin/env python3
"""
Analise profunda do wakeup pattern e baud rate automatico.
"""
import sys
from collections import Counter
import math

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

def digitize(data, thr):
    return [1 if v > thr else 0 for v in data]

def get_pulses(bits, T_us, start=0, end=None):
    """Retorna lista de (nivel, duracao_us, start_sample)."""
    if end is None:
        end = len(bits)
    pulses = []
    i = start
    while i < end:
        nivel = bits[i]
        j = i
        while j < end and bits[j] == nivel:
            j += 1
        dur_us = (j - i) * T_us
        pulses.append((nivel, dur_us, i))
        i = j
    return pulses

def find_bit_period(pulses, min_dur=50.0, max_dur=500.0):
    """
    Estima o periodo de bit por GCD das duracoes de pulso.
    """
    durations = [d for _, d, _ in pulses if min_dur <= d <= max_dur]
    if not durations:
        return None
    # Quantiza em multiplos de 5µs e busca menor duracao (= 1 bit)
    durations_sorted = sorted(set(round(d/5)*5 for d in durations))
    if not durations_sorted:
        return None
    return durations_sorted[0]

def decode_uart_from_pulses(pulses, bit_us, T_us, max_bytes=300):
    """
    Decode UART a partir de lista de pulsos (nivel, dur_us, start).
    Handles variable-length runs by counting bits per run.
    """
    decoded = []
    current_bits = []  # lista de bits (0/1)
    
    for nivel, dur_us, start_s in pulses:
        n_bits = max(1, round(dur_us / bit_us))
        current_bits.extend([nivel] * n_bits)
    
    # Parse UART: start(0) + 8 data bits (LSB) + stop(1)
    i = 0
    while i < len(current_bits) - 10:
        # Procurar start bit (0 precedido de 1)
        if i > 0 and current_bits[i-1] == 1 and current_bits[i] == 0:
            # Possivelmente start bit
            byte_val = 0
            for bit_num in range(8):
                pos = i + 1 + bit_num
                if pos >= len(current_bits):
                    byte_val = None
                    break
                byte_val |= (current_bits[pos] << bit_num)
            
            if byte_val is not None:
                stop_pos = i + 9
                stop_ok = current_bits[stop_pos] == 1 if stop_pos < len(current_bits) else False
                
                # Calcular tempo aproximado
                t_ms = start_s * T_us / 1000 if hasattr(start_s, '__float__') else 0
                decoded.append((byte_val, stop_ok))
                i += 10  # Avançar pelo byte completo
                continue
        i += 1
    
    return decoded

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\johan\Documents\yam.txt"

    print(f"Carregando {path}...")
    data = load_data(path)
    T_us = T_TOTAL_S * 1e6 / len(data)
    print(f"T: {T_us:.3f} us | Fs: {1e6/T_us:.0f} Hz")

    bits = digitize(data, THRESHOLD)

    # Localizar quando ECM liga
    ecm_on = None
    for i in range(1, len(bits) - 10):
        if bits[i-1] == 0 and bits[i] == 1:
            if all(bits[i+j] == 1 for j in range(10)):
                ecm_on = i
                break
    print(f"ECM LIGA: t={ecm_on*T_us/1000:.2f} ms")

    # Pegar pulsos a partir da ECM ligada
    all_pulses = get_pulses(bits, T_us, start=ecm_on)

    # ── Mostrar wakeup (primeiros 10 pulsos longos) ──
    print("\n=== WAKEUP PATTERN (pulsos > 1ms) ===")
    long_pulses = [(n, d, s) for n, d, s in all_pulses if d > 1000][:15]
    for i, (n, d, s) in enumerate(long_pulses):
        t = s * T_us / 1000
        print(f"  [{i}] t={t:8.2f}ms  {'HIGH' if n else 'LOW ':4}  dur={d/1000:7.3f}ms")

    # ── Histograma de durações curtas (pulsos de dados) ──
    data_pulses = [(n, d, s) for n, d, s in all_pulses if 30.0 < d < 600.0]
    print(f"\n=== HISTOGRAMA PAUSAS DE DADOS ({len(data_pulses)} pulsos 30-600us) ===")
    hist = Counter(round(d/5)*5 for _, d, _ in data_pulses)
    print("Duracao(us)  Contagem  Barra")
    for dur in sorted(hist.keys()):
        bar = "█" * min(40, hist[dur])
        print(f"  {dur:5.0f}us     {hist[dur]:5d}   {bar}")

    # ── Tentar TODOS os baud rates candidatos ──
    print("\n=== TESTE DE BAUD RATES ===")
    
    # Encontrar duracao minima dos pulsos de dados (provavelmente = 1 bit)
    min_dur = min(d for _, d, _ in data_pulses) if data_pulses else 0
    print(f"Duracao minima: {min_dur:.1f} us → baud estimado: {1e6/min_dur:.0f}")

    candidates = [1200, 2400, 4800, 9600, 10400, 14400, 15625, 16040, 19200, 38400]
    
    # Localizar inicio dos dados (apos wakeup)
    data_start = None
    for i, (n, d, s) in enumerate(all_pulses):
        if d > 5000 and i > 2:  # pausa longa apos wakeup
            # Proximo pulso eh inicio dos dados
            if i+1 < len(all_pulses):
                data_start = all_pulses[i+1][2]  # sample do inicio
                break
    
    if data_start is None:
        print("Nao encontrei inicio de dados.")
        return
    
    print(f"\nInicio dos dados: t={data_start*T_us/1000:.2f} ms")
    
    # Para cada baud, reconstroi bits e tenta UART
    for baud in candidates:
        bit_us = 1e6 / baud
        # Pegar pulsos da zona de dados
        zone_pulses = [(n, d, s) for n, d, s in all_pulses if s >= data_start and d < 10000][:500]
        
        # Reconstrói sequencia de bits
        bit_stream = []
        for nivel, dur_us, _ in zone_pulses:
            n = max(1, round(dur_us / bit_us))
            bit_stream.extend([nivel] * n)
        
        # Decode UART
        ok_total = 0
        err_total = 0
        i = 1
        while i < len(bit_stream) - 10:
            if bit_stream[i-1] == 1 and bit_stream[i] == 0:
                byte_val = 0
                for bn in range(8):
                    pos = i + 1 + bn
                    if pos < len(bit_stream):
                        byte_val |= (bit_stream[pos] << bn)
                stop_pos = i + 9
                if stop_pos < len(bit_stream):
                    if bit_stream[stop_pos] == 1:
                        ok_total += 1
                    else:
                        err_total += 1
                i += 10
                continue
            i += 1
        
        total = ok_total + err_total
        pct = 100*ok_total/total if total > 0 else 0
        print(f"  {baud:6d} baud: {ok_total:4d} OK, {err_total:4d} ERR → {pct:5.1f}% corretos  {'<<< MELHOR' if pct > 80 else ''}")

    # ── Decodificar com melhor baud rate ──
    best_baud = 16040  # ajustar baseado no resultado acima
    if len(sys.argv) > 2:
        best_baud = int(sys.argv[2])
    
    bit_us = 1e6 / best_baud
    zone_pulses = [(n, d, s) for n, d, s in all_pulses if s >= data_start and d < 10000][:500]
    
    bit_stream = []
    ref_sample = zone_pulses[0][2] if zone_pulses else 0
    for nivel, dur_us, _ in zone_pulses:
        n = max(1, round(dur_us / bit_us))
        bit_stream.extend([nivel] * n)
    
    print(f"\n=== BYTES DECODIFICADOS @ {best_baud} baud ===")
    bytes_ok = []
    i = 1
    while i < len(bit_stream) - 10:
        if bit_stream[i-1] == 1 and bit_stream[i] == 0:
            byte_val = 0
            for bn in range(8):
                pos = i + 1 + bn
                if pos < len(bit_stream):
                    byte_val |= (bit_stream[pos] << bn)
            stop_pos = i + 9
            stop_ok = (bit_stream[stop_pos] == 1) if stop_pos < len(bit_stream) else False
            if stop_ok:
                bytes_ok.append(byte_val)
            i += 10
            continue
        i += 1
    
    print(f"Bytes validos (stop=OK): {len(bytes_ok)}")
    hex_str = " ".join(f"{b:02X}" for b in bytes_ok[:100])
    print(f"HEX: {hex_str}")
    
    # Tentar identificar frames
    print("\n--- Primeiros 60 bytes em grupos de 3,4,5 ---")
    for gs in [3, 4, 5]:
        frames = [bytes_ok[i:i+gs] for i in range(0, min(60, len(bytes_ok)), gs)]
        frms_hex = ["  ".join(f"{b:02X}" for b in f) for f in frames[:15]]
        print(f"\n  Frame size {gs}: " + " | ".join(frms_hex[:10]))

if __name__ == "__main__":
    main()
