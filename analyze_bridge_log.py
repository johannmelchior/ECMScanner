#!/usr/bin/env python3
"""
analyze_bridge_log.py - Decodifica log da bridge serial (passthrough AVR)
==========================================================================
O AVR firmware roda em YAMAHA_PASSTHROUGH_BOOT=1:
    USB-TX -> K-Line TX  (YDS envia bytes diretamente para o barramento K-Line)
    K-Line RX -> USB-RX  (ECM responde, bytes chegam de volta ao YDS)

Formato do log:
    [timestamp.sss] TX/RX [  N]  HH HH ... |ASCII|

Para decodificar o protocolo K-Line Yamaha a partir dos bytes RX.
"""

import re
import sys
from pathlib import Path
from collections import Counter

LOG_FILE = r"C:\Temp\yds_bridge2_20260522_152859.txt"

# Regex para parsear linhas
LINE_RE = re.compile(
    r'^\[(\d+\.\d+)\]\s+(TX|RX)\s+\[\s*(\d+)\]\s+((?:[0-9A-Fa-f]{2}\s*)+)',
    re.MULTILINE
)

def parse_log(path: str):
    entries = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = LINE_RE.match(line.strip())
            if m:
                ts   = float(m.group(1))
                dirn = m.group(2)
                data = bytes.fromhex(m.group(4).replace(' ', ''))
                entries.append((ts, dirn, data))
    return entries

def extract_stream(entries, direction='RX'):
    """Concatena todos os bytes de uma direção em stream contínuo com timestamps."""
    out = []  # list of (timestamp, byte)
    for ts, dirn, data in entries:
        if dirn == direction:
            for b in data:
                out.append((ts, b))
    return out

def decode_syndat(byte_stream):
    """
    Hipótese de codificação Yamaha: byte = [6-bit valor | 2-bit código]
    SYN=0b11 (0x03), DAT=0b00 (0x00)
    Cada byte K-Line físico é precedido por um byte SYN com o mesmo valor alto.
    Retorna lista de (timestamp, kline_byte, has_framing_error) usando só os bytes DAT.
    """
    # Agrupar pares SYN+DAT
    decoded = []
    i = 0
    stream = list(byte_stream)
    while i < len(stream):
        ts, b = stream[i]
        code = b & 0x03
        val6 = b >> 2
        if code == 0x03:  # SYN
            if i + 1 < len(stream):
                ts2, b2 = stream[i+1]
                code2 = b2 & 0x03
                val6_2 = b2 >> 2
                if code2 == 0x00 and val6_2 == val6:
                    # par SYN+DAT valido
                    decoded.append((ts, b2, False))  # guarda o DAT byte
                    i += 2
                    continue
            # SYN sozinho ou sem par valido
            decoded.append((ts, b, True))
        else:
            decoded.append((ts, b, False))
        i += 1
    return decoded

def find_frame_boundaries(byte_stream, idle_gap_ms=50):
    """
    Encontra frames K-Line separados por gaps >= idle_gap_ms
    """
    frames = []
    current_frame = []
    prev_ts = None
    for ts, b in byte_stream:
        if prev_ts is not None and (ts - prev_ts) * 1000 >= idle_gap_ms:
            if current_frame:
                frames.append(current_frame)
                current_frame = []
        current_frame.append((ts, b))
        prev_ts = ts
    if current_frame:
        frames.append(current_frame)
    return frames

def decode_iso14230_frame(data: bytes):
    """Tenta decodificar como ISO 14230 (KWP2000)."""
    if len(data) < 3:
        return None
    fmt = data[0]
    fmt_type = (fmt >> 6) & 0x03
    addr_incl = (fmt >> 5) & 0x01
    length_in_fmt = fmt & 0x3F
    if fmt_type != 0x01 and fmt_type != 0x00:
        return None
    result = {'format_byte': fmt}
    offset = 1
    if addr_incl:
        if len(data) < 3:
            return None
        result['target'] = data[offset]
        result['source'] = data[offset+1]
        offset += 2
    if length_in_fmt == 0:
        if len(data) <= offset:
            return None
        length = data[offset]
        offset += 1
    else:
        length = length_in_fmt
    if len(data) < offset + length + 1:
        return None
    result['data'] = data[offset:offset+length]
    result['checksum_expected'] = data[offset+length]
    checksum_calc = sum(data[:offset+length]) & 0xFF
    result['checksum_ok'] = (checksum_calc == result['checksum_expected'])
    return result

def yamaha_kline_decode(raw_bytes: bytes):
    """
    O ECM Yamaha usa codificação especial: cada byte lógico é enviado como
    (val | SYN) seguido de (val | DAT). Primeiro par SYN+DAT é o byte real.
    """
    out = []
    i = 0
    while i < len(raw_bytes):
        b = raw_bytes[i]
        code = b & 0x03
        val6 = b >> 2
        if code == 0x03:  # SYN byte
            if i + 1 < len(raw_bytes):
                b2 = raw_bytes[i+1]
                code2 = b2 & 0x03
                val6_2 = b2 >> 2
                if code2 == 0x00 and val6_2 == val6:
                    out.append(b2)  # byte DAT
                    i += 2
                    continue
        out.append(b)
        i += 1
    return bytes(out)

def main():
    print("=" * 72)
    print(f"Análise do log: {LOG_FILE}")
    print("=" * 72)

    entries = parse_log(LOG_FILE)
    print(f"\nTotal de pacotes: {len(entries)}")

    tx_count = sum(1 for _, d, _ in entries if d == 'TX')
    rx_count = sum(1 for _, d, _ in entries if d == 'RX')
    tx_bytes = sum(len(b) for _, d, b in entries if d == 'TX')
    rx_bytes = sum(len(b) for _, d, b in entries if d == 'RX')
    print(f"TX: {tx_count} pacotes, {tx_bytes} bytes (YDS→AVR→K-Line)")
    print(f"RX: {rx_count} pacotes, {rx_bytes} bytes (K-Line→AVR→YDS)")

    # --- TX stream decode
    print("\n" + "=" * 72)
    print("BYTES TX (YDS → K-Line):")
    tx_stream = extract_stream(entries, 'TX')
    tx_bytes_only = bytes(b for _, b in tx_stream)
    print(f"  Hex: {tx_bytes_only.hex()}")
    print(f"  Sequência TX: {' '.join(['%02X'%b for b in tx_bytes_only])}")

    # --- RX stream
    rx_stream = extract_stream(entries, 'RX')
    rx_raw = bytes(b for _, b in rx_stream)

    # Estatísticas de bytes RX
    print("\n" + "=" * 72)
    print("BYTES RX (K-Line/ECM → YDS) - frequência:")
    counter = Counter(rx_raw)
    most_common = counter.most_common(20)
    for b, cnt in most_common:
        code = b & 0x03
        val = b >> 2
        code_str = "SYN" if code == 3 else ("DAT" if code == 0 else f"c{code}")
        pct = 100 * cnt / len(rx_raw)
        bar = '█' * int(pct / 2)
        print(f"  0x{b:02X} ({b:08b}) val={val:3d} [{code_str}] : {cnt:5d} ({pct:5.1f}%) {bar}")

    print(f"\nTotal bytes RX únicos: {len(counter)}")
    print(f"Bytes exclusivos: {sorted(['0x%02X'%b for b in counter.keys()])}")

    # --- Decode pares SYN+DAT
    print("\n" + "=" * 72)
    print("DECODIFICAÇÃO SYN+DAT (hipótese Yamaha K-Line):")
    decoded_stream = decode_syndat(rx_stream)
    decoded_bytes = bytes(b for _, b, _ in decoded_stream)
    errors = sum(1 for _, _, e in decoded_stream if e)
    valid_pairs = len(decoded_stream) - errors

    print(f"  Bytes originais RX: {len(rx_raw)}")
    print(f"  Após decodificação SYN+DAT: {len(decoded_bytes)} bytes")
    print(f"  Pares SYN+DAT válidos: {valid_pairs}, bytes sem par: {errors}")

    # Frequência pós-decod
    print("\n  Frequência após decode:")
    counter2 = Counter(decoded_bytes)
    for b, cnt in counter2.most_common(16):
        pct = 100 * cnt / len(decoded_bytes) if decoded_bytes else 0
        print(f"    0x{b:02X} ({b:<3d}) : {cnt:5d} ({pct:5.1f}%)")

    # --- Separar por frames (gaps >50ms)
    print("\n" + "=" * 72)
    print("FRAMES K-LINE (separados por gap > 50ms):")
    frames_raw = find_frame_boundaries(rx_stream, idle_gap_ms=50)
    print(f"  Total de frames: {len(frames_raw)}")
    for i, frame in enumerate(frames_raw[:20]):
        frame_bytes = bytes(b for _, b in frame)
        t_start = frame[0][0]
        t_end   = frame[-1][0]
        print(f"\n  Frame #{i+1} t=[{t_start:.3f}..{t_end:.3f}] ({len(frame_bytes)} bytes):")
        hex_str = ' '.join('%02X' % b for b in frame_bytes[:48])
        if len(frame_bytes) > 48:
            hex_str += f' ... (+{len(frame_bytes)-48} bytes)'
        print(f"    RAW: {hex_str}")
        # SYN+DAT decode do frame
        decoded_frame = yamaha_kline_decode(frame_bytes)
        hex_dec = ' '.join('%02X' % b for b in decoded_frame[:48])
        if len(decoded_frame) > 48:
            hex_dec += f' ... (+{len(decoded_frame)-48} bytes)'
        print(f"    DEC: {hex_dec}")

    # --- Tentar decodificar como ISO14230 (frames longos)
    print("\n" + "=" * 72)
    print("TENTATIVA ISO 14230 (KWP2000) nos frames decodificados:")
    for i, frame in enumerate(frames_raw):
        frame_bytes = bytes(b for _, b in frame)
        decoded_frame = yamaha_kline_decode(frame_bytes)
        if len(decoded_frame) >= 4:
            result = decode_iso14230_frame(decoded_frame)
            if result and result.get('checksum_ok'):
                print(f"  Frame #{i+1}: OK → {result}")

    # --- Sequência RX completa (primeiros 512 bytes)
    print("\n" + "=" * 72)
    print("PRIMEIROS 512 BYTES RX BRUTOS (hex):")
    idx = 0
    for i in range(0, min(512, len(rx_raw)), 16):
        chunk = rx_raw[i:i+16]
        hex_s = ' '.join('%02X' % b for b in chunk)
        ascii_s = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"  {i:04X}: {hex_s:<48} |{ascii_s}|")

    # --- Tentar decodificar como stream de nibbles
    print("\n" + "=" * 72)
    print("BYTES DAT (código=00) extraídos em sequência:")
    dat_bytes = bytes(b for b in rx_raw if (b & 0x03) == 0x00)
    print(f"  Total DAT: {len(dat_bytes)}")
    for i in range(0, min(256, len(dat_bytes)), 16):
        chunk = dat_bytes[i:i+16]
        print(f"  {i:04X}: {' '.join('%02X'%b for b in chunk)}")

    # --- Mostrar sequência TX vs RX com timing
    print("\n" + "=" * 72)
    print("TIMELINE TX/RX (todos os eventos):")
    for ts, dirn, data in entries:
        arrow = "→" if dirn == 'TX' else "←"
        hex_s = ' '.join('%02X' % b for b in data[:16])
        if len(data) > 16:
            hex_s += f'...'
        print(f"  [{ts:010.3f}] {arrow}{dirn} [{len(data):3d}] {hex_s}")

if __name__ == '__main__':
    main()
