#!/usr/bin/env python3
"""
Analise profunda do protocolo K-line Yamaha.
- Visualiza waveform ascii nos primeiros ms
- Testa decodificacao UART normal e invertida
- Identifica estrutura de frames via bordas de silencio
"""
import sys
from collections import Counter

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


def ascii_waveform(bits, start_sample, end_sample, T_us, width=120):
    """Mostra waveform ASCII de um trecho do sinal."""
    total = end_sample - start_sample
    step = max(1, total // width)
    row = ""
    for i in range(start_sample, end_sample, step):
        val = bits[i]
        row += "H" if val else "_"
    t_start_ms = start_sample * T_us / 1000
    t_end_ms = end_sample * T_us / 1000
    print(f"  [{t_start_ms:.2f}ms - {t_end_ms:.2f}ms] {row}")


def center_sample_uart(bits, start_sample, n_bits, bit_samples, inverted=False):
    byte_val = 0
    for bn in range(n_bits):
        pos = int(start_sample + (bn + 1.5) * bit_samples)
        if pos >= len(bits):
            return None
        bit = bits[pos]
        if inverted:
            bit = 1 - bit
        byte_val |= (bit << bn)
    stop_pos = int(start_sample + (n_bits + 1.5) * bit_samples)
    if stop_pos >= len(bits):
        return None
    stop_val = bits[stop_pos]
    if inverted:
        stop_val = 1 - stop_val
    return byte_val, (stop_val == 1)


def decode_all(bits, T_us, baud, start=0, end=None, inverted=False):
    if end is None:
        end = len(bits)
    bit_samples = (1e6 / baud) / T_us
    decoded = []
    i = start + 1
    while i < end:
        # Falling edge no sinal REAL (HIGH->LOW) = start bit normal
        # Para sinal invertido: "falling edge" no sinal eh HIGH->LOW mas representa bit 1
        # O start bit em sinal invertido aparece como LOW->HIGH
        if not inverted:
            edge = (bits[i - 1] == 1 and bits[i] == 0)  # HIGH->LOW normal
        else:
            edge = (bits[i - 1] == 0 and bits[i] == 1)  # LOW->HIGH = start invertido
        
        if edge:
            result = center_sample_uart(bits, i, 8, bit_samples, inverted)
            if result is not None:
                byte_val, stop_ok = result
                t_ms = i * T_us / 1000
                decoded.append((t_ms, byte_val, stop_ok))
                i = max(i + 1, int(i + 10 * bit_samples))
                continue
        i += 1
    return decoded


def extract_messages(decoded, gap_thresh_ms=2.0, only_ok=True):
    """Agrupa bytes em mensagens separadas por silencio."""
    vals = [(t, b, s) for t, b, s in decoded if (not only_ok or s)]
    messages = []
    current = []
    for i, (t, b, s) in enumerate(vals):
        if i > 0 and t - vals[i - 1][0] > gap_thresh_ms:
            if current:
                messages.append(current)
            current = []
        current.append((t, b))
    if current:
        messages.append(current)
    return messages


def checksum_test(msg_bytes):
    """Testa varios tipos de checksum."""
    if len(msg_bytes) < 2:
        return {}
    results = {}
    data = msg_bytes[:-1]
    last = msg_bytes[-1]
    
    simple_sum = sum(data) & 0xFF
    results['sum&FF'] = (simple_sum == last)
    
    xor = 0
    for b in data:
        xor ^= b
    results['xor'] = (xor == last)
    
    crc = sum(data) % 256
    results['sum%256'] = (crc == last)
    
    two_complement = (~sum(data) + 1) & 0xFF
    results['2comp'] = (two_complement == last)
    
    return results


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\johan\Documents\yamaha funcionando.txt"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 15625

    print(f"Arquivo: {path}")
    print(f"Baud: {baud}")
    data = load_data(path)
    T_us = T_TOTAL_S * 1e6 / len(data)
    bits = digitize(data, THRESHOLD)

    # Encontrar inicio do sinal
    start_sample = 0
    for i in range(1, len(bits) - 10):
        if bits[i] == 1 and all(bits[i + j] == 1 for j in range(5)):
            start_sample = i
            break

    print(f"\nSinal ativo em: t={start_sample * T_us / 1000:.2f} ms")

    # === WAVEFORM ASCII dos primeiros 30ms apos inicio ===
    print("\n=== WAVEFORM ASCII (primeiros 30ms) ===")
    ms_30 = int(30 / T_us * 1000)
    end_wave = min(start_sample + ms_30, len(bits))
    for chunk_start in range(start_sample, end_wave, int(5 / T_us * 1000)):
        chunk_end = min(chunk_start + int(5 / T_us * 1000), end_wave)
        ascii_waveform(bits, chunk_start, chunk_end, T_us, width=100)

    # === Decoder normal + invertido ===
    for inv in [False, True]:
        label = "INVERTIDO" if inv else "NORMAL"
        decoded = decode_all(bits, T_us, baud, start=start_sample, inverted=inv)
        ok = sum(1 for _, _, s in decoded if s)
        pct = 100 * ok / len(decoded) if decoded else 0
        print(f"\n=== DECODIFICACAO {label} @ {baud} baud: {ok}/{len(decoded)} ({pct:.1f}%) ===")

        # Extrair mensagens
        msgs = extract_messages(decoded, gap_thresh_ms=2.0, only_ok=True)
        print(f"Mensagens separadas por >2ms: {len(msgs)}")

        # Histograma de tamanhos de mensagem
        sizes = Counter(len(m) for m in msgs)
        print("Tamanhos de mensagem:")
        for sz in sorted(sizes.keys())[:15]:
            bar = "#" * min(30, sizes[sz])
            print(f"  {sz:2d} bytes: {sizes[sz]:4d}  {bar}")

        # Mostrar primeiras 20 mensagens
        print("\nPrimeiras 20 mensagens:")
        for i, msg in enumerate(msgs[:20]):
            hex_str = " ".join(f"{b:02X}" for _, b in msg)
            t_start = msg[0][0]
            t_end = msg[-1][0]

            # Checksum
            mbytes = [b for _, b in msg]
            cs = checksum_test(mbytes)
            cs_ok = [k for k, v in cs.items() if v]
            cs_str = f"  [CS: {','.join(cs_ok)}]" if cs_ok else ""

            # Valor numerico dos bytes de dado
            if len(mbytes) >= 2:
                val16 = (mbytes[-2] << 8) | mbytes[-1] if len(mbytes) >= 2 else 0
                val8 = mbytes[-1]

            print(f"  [{i:3d}] t={t_start:7.2f}ms  len={len(msg):2d}  [{hex_str}]{cs_str}")

        if not msgs:
            continue

        # Analise dos bytes mais comuns
        all_bytes = [b for m in msgs for _, b in m]
        print(f"\nBytes mais frequentes (top 10):")
        cnt = Counter(all_bytes)
        for b, c in cnt.most_common(10):
            pct_b = 100 * c / len(all_bytes)
            print(f"  0x{b:02X} ({b:3d}): {c:5d} ({pct_b:.1f}%)")

        # Se mensagens de tamanho 3 sao dominantes, analisar estrutura
        if sizes.get(3, 0) > 10:
            msgs3 = [m for m in msgs if len(m) == 3]
            print(f"\n=== MENSAGENS DE 3 BYTES ({len(msgs3)}): ===")
            print(f"{'Byte0':>8}  {'Byte1':>8}  {'Byte2':>8}  {'Checksum?'}")
            cnt3 = Counter(tuple(b for _, b in m) for m in msgs3)
            for (b0, b1, b2), c in cnt3.most_common(15):
                cs = checksum_test([b0, b1, b2])
                cs_ok = [k for k, v in cs.items() if v]
                print(f"  0x{b0:02X}={b0:3d}  0x{b1:02X}={b1:3d}  0x{b2:02X}={b2:3d}  x{c}  {', '.join(cs_ok)}")

        # Se mensagens de tamanho 1-2 sao dominantes, mostrar sequencia
        elif max(sizes, key=sizes.get) <= 2:
            print(f"\n=== SEQUENCIA DE BYTES (mensagens curtas) ===")
            seq_bytes = [tuple(b for _, b in m) for m in msgs[:60]]
            # Pares sequenciais
            print("Primeira coluna e request, segunda e response?")
            for i in range(0, min(40, len(seq_bytes) - 1), 2):
                req = " ".join(f"{b:02X}" for b in seq_bytes[i])
                rsp = " ".join(f"{b:02X}" for b in seq_bytes[i + 1]) if i + 1 < len(seq_bytes) else "?"
                print(f"  req=[{req}]  rsp=[{rsp}]")


if __name__ == "__main__":
    main()
