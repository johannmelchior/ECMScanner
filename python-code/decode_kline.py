#!/usr/bin/env python3
"""
Decoder K-line preciso com filtragem de ruido/ringing.
Analisa wakeup pattern + dados do painel/ECM Yamaha.
"""
import sys

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

def debounce(bits, T_us, min_pulse_us=40.0):
    """Remove pulsos menores que min_pulse_us (ruido de ringing)."""
    result = list(bits)
    i = 0
    while i < len(result):
        if i == 0 or result[i] == result[i-1]:
            i += 1
            continue
        # Inicio de pulso, medir duracao
        j = i
        while j < len(result) and result[j] == result[i]:
            j += 1
        dur_us = (j - i) * T_us
        if dur_us < min_pulse_us:
            # Pulso curto: substituir pelo nivel anterior
            for k in range(i, j):
                result[k] = result[i-1]
        i = j
    return result

def get_edges(bits, start=0):
    """Retorna lista de (sample_idx, nivel_novo) para cada transicao."""
    edges = []
    for i in range(start + 1, len(bits)):
        if bits[i] != bits[i-1]:
            edges.append((i, bits[i]))
    return edges

def decode_uart_stream(bits, T_us, baud, start_sample, max_bytes=200):
    """
    Decodifica UART a partir de start_sample.
    Retorna lista de (t_ms, byte_val, stop_ok).
    """
    bit_us = 1e6 / baud
    bit_s = bit_us / T_us  # amostras por bit
    decoded = []
    i = start_sample

    while i < len(bits) - int(bit_s * 10) and len(decoded) < max_bytes:
        # Procurar falling edge (start bit)
        if bits[i-1] == 1 and bits[i] == 0:
            start = i
            byte_val = 0
            # Amostrar 8 bits de dados (centrado em cada bit)
            ok = True
            for bit_num in range(8):
                sample_pos = start + int(bit_s * (bit_num + 1.5))
                if sample_pos >= len(bits):
                    ok = False
                    break
                bit_val = bits[sample_pos]
                byte_val |= (bit_val << bit_num)  # LSB first

            if ok:
                # Verificar stop bit
                stop_pos = start + int(bit_s * 9.5)
                stop_ok = bits[stop_pos] == 1 if stop_pos < len(bits) else False
                t_ms = start * T_us / 1000
                decoded.append((t_ms, byte_val, stop_ok))
                # Avancar para depois do byte completo
                i = start + int(bit_s * 10)
                continue
        i += 1
    return decoded

def analyze_wakeup(edges, T_us):
    """Analisar o wakeup pattern antes dos dados."""
    print("\n=== WAKEUP PATTERN ===")
    print(f"{'#':>3}  {'T(ms)':>9}  {'Nivel':>6}  {'Dur(ms)':>9}")
    print("-" * 40)
    for k in range(min(20, len(edges)-1)):
        idx, nivel = edges[k]
        next_idx, _ = edges[k+1]
        t_ms = idx * T_us / 1000
        dur_ms = (next_idx - idx) * T_us / 1000
        nivel_str = "HIGH" if nivel else "LOW"
        marker = " <-- PAUSA" if dur_ms > 10 else ""
        print(f"{k:>3}  {t_ms:>9.3f}  {nivel_str:>6}  {dur_ms:>9.3f}{marker}")

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\johan\Documents\yam.txt"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 16040

    print(f"Carregando {path}...")
    data = load_data(path)
    T_us = T_TOTAL_S * 1e6 / len(data)
    print(f"Amostras: {len(data)} | T: {T_us:.3f} us | Fs: {1e6/T_us:.0f} Hz")

    raw_bits = digitize(data, THRESHOLD)

    # Filtrar ruido de ringing (pulsos < 40us)
    clean_bits = debounce(raw_bits, T_us, min_pulse_us=40.0)

    # ── Localizar quando ECM liga (sinal sobe e fica estavel) ──
    ecm_on = None
    for i in range(1, len(clean_bits) - 10):
        if clean_bits[i-1] == 0 and clean_bits[i] == 1:
            if all(clean_bits[i+j] == 1 for j in range(10)):
                ecm_on = i
                break

    print(f"\nECM LIGA: sample {ecm_on} = t={ecm_on*T_us/1000:.2f} ms")

    # ── Edges apos ECM ligar ──
    edges = get_edges(clean_bits, ecm_on)

    analyze_wakeup(edges, T_us)

    # ── Encontrar quando dados comecar (primeira sequencia rapida) ──
    # Procurar primeira transicao com duracao < 1ms depois de pausa longa
    data_start_sample = None
    long_pauses_found = 0
    for k in range(len(edges) - 1):
        idx, nivel = edges[k]
        next_idx, _ = edges[k+1]
        dur_ms = (next_idx - idx) * T_us / 1000
        if dur_ms > 10:
            long_pauses_found += 1
        if long_pauses_found >= 3 and dur_ms < 5:
            # Primeira transicao rapida apos 3 pausas longas
            data_start_sample = idx
            break

    if data_start_sample is None:
        # Fallback: usar primeira edge rapida apos ecm_on + 50ms
        min_sample = ecm_on + int(200000 / T_us)  # 200ms depois
        for k in range(len(edges) - 1):
            idx, nivel = edges[k]
            next_idx, _ = edges[k+1]
            if idx < min_sample:
                continue
            dur_ms = (next_idx - idx) * T_us / 1000
            if dur_ms < 1.0:
                data_start_sample = idx
                break

    print(f"\nDados UART iniciam em: sample {data_start_sample} = t={data_start_sample*T_us/1000:.2f} ms")

    # ── Decodificar usando baud especificado ──
    bit_us = 1e6 / baud
    print(f"\n=== DECODIFICANDO UART @ {baud} baud (bit={bit_us:.1f}us = {bit_us/T_us:.2f} amostras) ===")

    decoded = decode_uart_stream(clean_bits, T_us, baud, data_start_sample, max_bytes=300)

    if not decoded:
        print("Nenhum byte decodificado. Talvez ajustar baud rate.")
        return

    print(f"Total bytes decodificados: {len(decoded)}")
    print()
    print(f"{'Tempo(ms)':>10}  {'HEX':>4}  {'DEC':>4}  {'CHR':>4}  {'Stop':>5}  Analise")
    print("-" * 60)

    for i, (t_ms, bval, stop) in enumerate(decoded):
        ch = chr(bval) if 0x20 <= bval <= 0x7e else '.'
        stop_str = "OK" if stop else "ERR"
        # Analise de padroes
        nota = ""
        if i < 3 and bval == 0xFF:
            nota = "[idle: linha HIGH]"
        elif i < 5 and bval == 0x00:
            nota = "[wakeup LOW pulse]"
        print(f"{t_ms:>10.3f}  {bval:>02X}  {bval:>4d}  '{ch:>1}'  {stop_str:>5}  {nota}")
        if i >= 100:
            print(f"... ({len(decoded)-100} bytes adicionais)")
            break

    # ── Resumo HEX (primeiros 100 bytes validos) ──
    valid = [(t, b) for t, b, s in decoded if s]
    print(f"\n=== HEX VALIDOS (stop=OK): {len(valid)} bytes ===")
    print("  " + " ".join(f"{b:02X}" for _, b in valid[:80]))

    # ── Detectar padroes de frame ──
    print("\n=== ANALISE DE PADROES ===")
    byte_vals = [b for _, b, _ in decoded if _]  # apenas stop=OK
    # Tentar frames de 3, 4, 5, 6 bytes
    for frame_size in [3, 4, 5, 6]:
        frames = [byte_vals[i:i+frame_size] for i in range(0, min(len(byte_vals), 100), frame_size)]
        hex_frames = [" ".join(f"{b:02X}" for b in fr) for fr in frames[:15]]
        print(f"\n  Frames de {frame_size} bytes:")
        for fr in hex_frames:
            print(f"    [{fr}]")

if __name__ == "__main__":
    main()
