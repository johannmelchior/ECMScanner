#!/usr/bin/env python3
"""
Analisa sinal K-line capturado pelo osciloscópio.
Detecta handshake e decodifica bytes enviados pelo painel/ECM.
"""
import sys
import math

THRESHOLD = 2.0      # Volts para threshold digital
BAUD_10400 = 10400   # Padrão OBD K-line
BAUD_16040 = 16040   # Yamaha custom

def load_data(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    data = []
    for l in lines:
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        data.append(float(l))
    return data

def digitize(data, threshold=THRESHOLD):
    return [1 if v > threshold else 0 for v in data]

def find_transitions(bits, start, count):
    """Retorna lista de (index, nivel) para cada transição"""
    transitions = []
    i = start
    while i < len(bits) - 1 and len(transitions) < count:
        if bits[i] != bits[i+1]:
            transitions.append((i+1, bits[i+1]))
        i += 1
    return transitions

def decode_uart_byte(bits, start_sample, bit_width_samples, polarity_inverted=False):
    """
    Decoda um byte UART a partir do start bit.
    start_sample: index do inicio do start bit (falling edge)
    bit_width_samples: largura de um bit em amostras
    """
    byte_val = 0
    center_offset = int(bit_width_samples * 0.5)
    
    # Pular start bit, amostrar 8 bits de dados
    for bit_num in range(8):
        sample_idx = start_sample + int(bit_width_samples * (bit_num + 1)) + center_offset
        if sample_idx >= len(bits):
            return None
        bit_val = bits[sample_idx]
        if polarity_inverted:
            bit_val = 1 - bit_val
        byte_val |= (bit_val << bit_num)  # LSB first
    
    # Verificar stop bit
    stop_idx = start_sample + int(bit_width_samples * 9) + center_offset
    stop_val = bits[stop_idx] if stop_idx < len(bits) else 1
    
    return byte_val, stop_val

def analyze_gap(dur_us, baud):
    bit_us = 1e6 / baud
    n_bits = dur_us / bit_us
    return n_bits

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\johan\Documents\yam.txt"
    print(f"Carregando {path}...")
    data = load_data(path)
    T_us = 5e6 / len(data)  # microsegundos por amostra
    print(f"Total: {len(data)} amostras | Sample period: {T_us:.3f} us | Sample rate: {1e6/T_us:.0f} Hz")

    bits = digitize(data)

    # ────────────────────────────────────────────────────
    # 1. Localizar quando a ECM liga (sinal sobe de 0 para HIGH)
    # ────────────────────────────────────────────────────
    ecm_on_sample = None
    for i in range(1, len(bits) - 5):
        if bits[i-1] == 0 and all(bits[i+j] == 1 for j in range(5)):
            ecm_on_sample = i
            break
    
    print(f"\n{'='*60}")
    print(f"ECM LIGA: sample {ecm_on_sample} = t={ecm_on_sample*T_us/1000:.2f} ms")
    print(f"{'='*60}")

    # ────────────────────────────────────────────────────
    # 2. Mostrar todas as transições a partir da ECM ligada
    # ────────────────────────────────────────────────────
    transitions = find_transitions(bits, ecm_on_sample, 300)
    
    print(f"\n{'#':>4}  {'Sample':>9}  {'T (ms)':>9}  {'Nivel':>6}  {'Dur (us)':>10}  {'@10400':>8}  {'@16040':>8}  Nota")
    print("-" * 90)
    
    for k in range(min(80, len(transitions)-1)):
        idx, nivel = transitions[k]
        next_idx, _ = transitions[k+1]
        t_ms = idx * T_us / 1000
        dur_us = (next_idx - idx) * T_us
        bits_10400 = dur_us / (1e6/BAUD_10400)
        bits_16040 = dur_us / (1e6/BAUD_16040)
        nivel_str = "HIGH" if nivel else "LOW"
        
        # Interpretação
        nota = ""
        if dur_us > 20000:
            nota = f"<<< PAUSA LONGA {dur_us/1000:.1f}ms >>>"
        elif round(bits_10400) == 1 and abs(bits_10400 - 1) < 0.2:
            nota = "~1 bit 10400"
        elif round(bits_16040) == 1 and abs(bits_16040 - 1) < 0.2:
            nota = "~1 bit 16040"
        
        print(f"{k:>4}  {idx:>9}  {t_ms:>9.3f}  {nivel_str:>6}  {dur_us:>10.1f}  {bits_10400:>8.2f}  {bits_16040:>8.2f}  {nota}")

    # ────────────────────────────────────────────────────
    # 3. Tentar decodificar bytes em ambos baudrates
    # ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("TENTANDO DECODIFICAR BYTES")
    print(f"{'='*60}")
    
    for baud in [BAUD_10400, BAUD_16040]:
        bit_us = 1e6 / baud
        bit_samples = bit_us / T_us
        print(f"\n--- Baud: {baud} | bit_width: {bit_us:.1f} us = {bit_samples:.2f} amostras ---")
        
        # Encontrar start bits (falling edges a partir da ECM ligada)
        bytes_found = []
        search_start = ecm_on_sample
        i = search_start
        
        while i < min(len(bits) - 20, search_start + 600000):
            # Procurar falling edge (HIGH -> LOW)
            if bits[i-1] == 1 and bits[i] == 0:
                result = decode_uart_byte(bits, i, bit_samples)
                if result is not None:
                    byte_val, stop_bit = result
                    t_ms = i * T_us / 1000
                    # Avançar para depois do byte (10 bits)
                    bytes_found.append((i, t_ms, byte_val, stop_bit))
                    i += int(bit_samples * 10)
                    continue
            i += 1
        
        print(f"Bytes encontrados: {len(bytes_found)}")
        for idx_s, t_ms, b, stop in bytes_found[:80]:
            ch = chr(b) if 0x20 <= b <= 0x7e else '.'
            stop_ok = "OK" if stop == 1 else "ERR"
            print(f"  t={t_ms:8.2f}ms  0x{b:02X}  {b:3d}  '{ch}'  stop={stop_ok}")
        
        if len(bytes_found) > 0:
            # Mostrar como sequencia hex
            hex_seq = " ".join(f"{b:02X}" for _, _, b, _ in bytes_found[:40])
            print(f"\n  HEX: {hex_seq}")

if __name__ == "__main__":
    main()
