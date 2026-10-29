#!/usr/bin/env python3
"""
hantek_kline_capture.py — Captura K-Line via Hantek 6022 e decodifica em tempo real.

Compatível com o formato de arquivo do kline_visualizer.py.

Instalar dependências:
    pip install libusb1 numpy

Instalar driver Windows:
    1. Plugue o Hantek no USB
    2. Abra Zadig (https://zadig.akeo.ie/)
    3. Options → List All Devices → seleciona "Hantek 6022BE"
    4. Troca driver para WinUSB → Install Driver

Uso:
    python hantek_kline_capture.py                    # captura 5s, CH1
    python hantek_kline_capture.py -t 10              # captura 10s
    python hantek_kline_capture.py -ch 2              # usa CH2
    python hantek_kline_capture.py -b 10400           # baudrate K-line
    python hantek_kline_capture.py --visualizer       # abre visualizador depois
    python hantek_kline_capture.py --live             # modo monitor contínuo

Conexão física:
    K-Line (ISO 9141 / KWP2000):
        - K-Line (pino 7 OBD) → CH1 do osciloscópio (ponta com divisor 1:1)
        - GND do chassi        → GND do osciloscópio
        - Nível lógico: 12V idle HIGH, LOW = bit 0
        - Threshold recomendado: 6V (use divisor resistivo 10k/10k para reduzir a 6V→3V)

    Yamaha K-Line específico:
        - Mesmo esquema, idle HIGH (~5V ou 12V dependendo do circuito)
        - Baudrate padrão: 15625 bps
"""

import sys
import time
import struct
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    import numpy as np
except ImportError:
    print("ERRO: numpy não instalado. Execute: pip install numpy")
    sys.exit(1)

# --- Parâmetros de captura ---
DEFAULT_BAUD    = 15625   # Yamaha K-Line
DEFAULT_TIME    = 5.0     # segundos de captura
DEFAULT_CHANNEL = 1       # CH1
SAMPLE_RATE_KS  = 200     # 200 kS/s — suficiente para K-line (15625 bps = ~12x oversampling)
THRESHOLD_V     = 2.5     # limiar de tensão para bit HIGH (ajustar conforme divisor)

# Mapeamento PyHT6022
RATE_MAP = {
    20:  1,   # 20 kS/s
    32:  2,
    50:  3,
    64:  4,
    100: 5,
    128: 6,
    200: 7,   # 200 kS/s ← padrão usado aqui
}

VOLTAGE_MAP = {
    # divisão → código interno
    1:  1,   # ±1V
    2:  2,   # ±2V
    5:  5,   # ±5V
    10: 10,  # ±10V
}


# ---------------------------------------------------------------------------
# Funções de interface com o scope
# ---------------------------------------------------------------------------

def connect_scope():
    """Conecta ao Hantek 6022 via PyHT6022. Retorna objeto scope ou None."""
    try:
        from PyHT6022.LibUsbScope import Oscilloscope
    except ImportError:
        print("ERRO: PyHT6022 não instalado.")
        print("Execute: pip install git+https://github.com/Ho-Ro/Hantek6022API.git")
        print("         -- ou --")
        print("         pip install libusb1 && git clone https://github.com/Ho-Ro/Hantek6022API && pip install ./Hantek6022API")
        return None

    try:
        scope = Oscilloscope()
        scope.setup()
        scope.open_handle()
    except Exception as e:
        print(f"ERRO: Não conseguiu abrir o Hantek: {e}")
        print("Verifique: driver WinUSB instalado via Zadig?")
        return None

    if not scope.is_device_firmware_present:
        print("Fazendo upload do firmware custom... ", end="", flush=True)
        scope.flash_firmware()
        time.sleep(1.0)
        print("OK")
    else:
        print("Firmware já presente no scope.")

    return scope


def configure_scope(scope, channel: int = 1, voltage_range: int = 5):
    """Configura sample rate e faixa de tensão."""
    rate_code = RATE_MAP.get(SAMPLE_RATE_KS, 7)
    scope.set_sample_rate(rate_code)

    # Faixa ±5V é boa para K-line se usar divisor 10k/10k (reduz 12V→6V)
    v_code = VOLTAGE_MAP.get(voltage_range, 5)
    if channel == 1:
        scope.set_ch1_voltage_range(v_code)
    else:
        scope.set_ch2_voltage_range(v_code)

    print(f"Scope configurado: {SAMPLE_RATE_KS} kS/s, CH{channel}, ±{voltage_range}V")


def capture_samples(scope, channel: int, duration_s: float) -> np.ndarray:
    """Captura amostras por 'duration_s' segundos. Retorna array de tensão."""
    n_samples = int(SAMPLE_RATE_KS * 1000 * duration_s)
    chunk     = 2048  # ler em blocos
    collected = []

    print(f"Capturando {n_samples} amostras ({duration_s}s)...", flush=True)
    t_start = time.monotonic()

    while len(collected) < n_samples:
        ch1, ch2 = scope.read_data(data_size=chunk, raw=False)
        data = ch1 if channel == 1 else ch2
        collected.extend(data)
        elapsed = time.monotonic() - t_start
        pct = 100 * len(collected) / n_samples
        print(f"\r  {pct:5.1f}%  ({elapsed:.1f}s)", end="", flush=True)

    print()
    return np.array(collected[:n_samples], dtype=float)


# ---------------------------------------------------------------------------
# Salva no formato do kline_visualizer.py
# ---------------------------------------------------------------------------

def save_capture(samples: np.ndarray, outpath: Path, baud: int):
    """Salva no formato compatível com kline_visualizer.py."""
    n = len(samples)
    period_us = 1e6 / (SAMPLE_RATE_KS * 1000)
    clock_s   = period_us * n / 1e6

    with open(outpath, "w") as f:
        f.write(f"#CLOCK={clock_s:.6f}\n")
        f.write(f"#SIZE={n}\n")
        f.write(f"#SAMPLERATE_KSS={SAMPLE_RATE_KS}\n")
        f.write(f"#BAUD={baud}\n")
        f.write(f"#THRESHOLD={THRESHOLD_V}\n")
        f.write(f"#CAPTURED={datetime.now().isoformat()}\n")
        for v in samples:
            f.write(f"{v:.4f}\n")

    print(f"Salvo: {outpath}  ({n} amostras, {clock_s:.2f}s)")


# ---------------------------------------------------------------------------
# Decodificação soft-UART inline
# ---------------------------------------------------------------------------

def decode_uart(samples: np.ndarray, baud: int) -> list[tuple[float, int, bool]]:
    """Decodifica UART a partir das amostras. Retorna lista de (time_ms, byte, stop_ok)."""
    period_us  = 1e6 / (SAMPLE_RATE_KS * 1000)
    bit_samples = (1e6 / baud) / period_us
    bits = (samples > THRESHOLD_V).astype(int)

    decoded = []
    idx = 1
    limit = len(bits) - int(10 * bit_samples) - 2

    while idx < limit:
        # Borda de descida (start bit)
        if bits[idx - 1] == 1 and bits[idx] == 0:
            byte_val = 0
            valid = True
            for bit_n in range(8):
                pos = int(idx + (bit_n + 1.5) * bit_samples)
                if pos >= len(bits):
                    valid = False
                    break
                byte_val |= bits[pos] << bit_n
            stop_pos = int(idx + 9.5 * bit_samples)
            stop_ok  = stop_pos < len(bits) and bits[stop_pos] == 1
            if valid:
                t_ms = idx * period_us / 1000.0
                decoded.append((t_ms, byte_val, stop_ok))
                idx = max(idx + 1, int(idx + 10 * bit_samples))
                continue
        idx += 1

    return decoded


# ---------------------------------------------------------------------------
# Extrai canais F8 (Yamaha específico)
# ---------------------------------------------------------------------------

def extract_f8(decoded: list) -> dict[int, list]:
    valid = [(t, b) for t, b, ok in decoded if ok]
    channels = defaultdict(list)
    for i in range(len(valid) - 2):
        t, b0 = valid[i]
        _, b1  = valid[i + 1]
        _, b2  = valid[i + 2]
        if b0 == 0xF8 and b1 not in (0xF8, 0xFF):
            channels[b1].append((t, b2))
    return dict(channels)


# ---------------------------------------------------------------------------
# Monitor contínuo (modo --live)
# ---------------------------------------------------------------------------

def live_monitor(scope, channel: int, baud: int):
    """Loop contínuo: captura 1s → decodifica → imprime bytes na tela."""
    print(f"\nModo LIVE — K-Line CH{channel} @ {baud} bps  (Ctrl+C para parar)\n")
    frame_buf = []

    try:
        while True:
            samples = capture_samples(scope, channel, duration_s=0.5)
            decoded = decode_uart(samples, baud)

            if not decoded:
                print("  [silêncio]")
                continue

            # Agrupa em frames por gap > 5ms
            frames = []
            cur_frame = []
            prev_t = decoded[0][0]
            for t, byte, ok in decoded:
                if t - prev_t > 5.0 and cur_frame:
                    frames.append(cur_frame)
                    cur_frame = []
                cur_frame.append((t, byte, ok))
                prev_t = t
            if cur_frame:
                frames.append(cur_frame)

            for frame in frames:
                hex_str  = " ".join(f"{b:02X}" for _, b, _ in frame)
                bad_stop = sum(1 for _, _, ok in frame if not ok)
                flag     = f"  [!{bad_stop} framing err]" if bad_stop else ""
                t0       = frame[0][0]
                print(f"  t={t0:8.1f}ms  {hex_str}{flag}")

            # Canais F8 Yamaha
            channels = extract_f8(decoded)
            if channels:
                line = "  F8: " + " | ".join(
                    f"CH{ch}=0x{vals[-1][1]:02X}({vals[-1][1]})"
                    for ch, vals in sorted(channels.items())
                )
                print(line)

    except KeyboardInterrupt:
        print("\nParado.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Captura K-Line via Hantek 6022")
    parser.add_argument("-t",  "--time",       type=float, default=DEFAULT_TIME,
                        help=f"Duração da captura em segundos (padrão: {DEFAULT_TIME})")
    parser.add_argument("-ch", "--channel",    type=int,   default=DEFAULT_CHANNEL,
                        choices=[1, 2], help="Canal do osciloscópio (1 ou 2)")
    parser.add_argument("-b",  "--baud",       type=int,   default=DEFAULT_BAUD,
                        help=f"Baudrate K-Line (padrão: {DEFAULT_BAUD})")
    parser.add_argument("-v",  "--voltage",    type=int,   default=5,
                        choices=[1, 2, 5, 10], help="Faixa de tensão ±V (padrão: 5)")
    parser.add_argument("-o",  "--output",     type=str,   default=None,
                        help="Arquivo de saída (padrão: kline_hantek_YYYYMMDD_HHMMSS.txt)")
    parser.add_argument("--live",              action="store_true",
                        help="Monitor contínuo em tempo real (não salva arquivo)")
    parser.add_argument("--visualizer",        action="store_true",
                        help="Abre kline_visualizer.py com o arquivo capturado")
    parser.add_argument("--decode-only",       action="store_true",
                        help="Só decodifica, não imprime hex completo")
    args = parser.parse_args()

    # Conecta
    scope = connect_scope()
    if scope is None:
        sys.exit(1)

    configure_scope(scope, channel=args.channel, voltage_range=args.voltage)
    print(f"Baudrate K-Line: {args.baud} bps  |  Threshold: {THRESHOLD_V}V\n")

    try:
        if args.live:
            live_monitor(scope, args.channel, args.baud)
            return

        # Captura única
        samples = capture_samples(scope, args.channel, args.time)

        # Salva arquivo
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        captures_dir = Path(__file__).parent / "captures"
        captures_dir.mkdir(exist_ok=True)
        outpath = Path(args.output) if args.output else captures_dir / f"kline_hantek_{ts}.txt"
        save_capture(samples, outpath, args.baud)

        # Decodifica inline
        print(f"\nDecodificando @ {args.baud} bps...")
        decoded = decode_uart(samples, args.baud)
        print(f"  {len(decoded)} bytes decodificados\n")

        if decoded:
            # Mostra hex
            print("=== Bytes capturados ===")
            prev_t = decoded[0][0]
            frame = []
            def flush(frame):
                if frame:
                    hex_str  = " ".join(f"{b:02X}" for _, b, _ in frame)
                    bad      = sum(1 for _, _, ok in frame if not ok)
                    flag     = f"  (!{bad} framing)" if bad else ""
                    print(f"  [{frame[0][0]:8.2f}ms]  {hex_str}{flag}")

            for t, byte, ok in decoded:
                if t - prev_t > 5.0 and frame:
                    flush(frame)
                    frame = []
                frame.append((t, byte, ok))
                prev_t = t
            flush(frame)

            # Canais F8
            channels = extract_f8(decoded)
            if channels:
                print(f"\n=== Canais F8 Yamaha detectados ({len(channels)} canais) ===")
                for ch_id, vals in sorted(channels.items()):
                    last_v = vals[-1][1]
                    print(f"  Canal 0x{ch_id:02X} ({ch_id:3d}): {len(vals):4d} amostras, "
                          f"último=0x{last_v:02X} ({last_v})")
            else:
                print("\n[Nenhum padrão F8 encontrado]")

        # Abre visualizador
        if args.visualizer:
            vis_path = Path(__file__).parent / "kline_visualizer.py"
            if vis_path.exists():
                print(f"\nAbrindo kline_visualizer.py com {outpath.name}...")
                subprocess.Popen([sys.executable, str(vis_path), str(outpath)])
            else:
                print(f"kline_visualizer.py não encontrado em {vis_path}")

    finally:
        scope.close_handle()
        print("\nScope fechado.")


if __name__ == "__main__":
    main()
