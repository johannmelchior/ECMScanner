"""
kline_sniff_realtime.py -- Leitura em tempo real do protocolo K-Line Yamaha VX110

Uso:
    python kline_sniff_realtime.py [COM] [baud] [--csv arquivo.csv]

Exemplos:
    python kline_sniff_realtime.py COM7
    python kline_sniff_realtime.py COM7 10400
    python kline_sniff_realtime.py COM7 --csv kline_log.csv

Ctrl+C para parar.

Protocolo identificado (10400 baud, Yamaha VX110 sem init):
  - Frame tipico: 1-5 bytes
  - Bytes dominantes variam com estado da moto (RPM, carga)
  - Gap entre frames: ~5ms media (2-10ms)
  - Exemplos observados:
      idle: E0 E0 / E0 F0 ...
      rodando: FC 8C / 9C 8C / 20 8C ...
"""

import sys
import os
import time
import csv
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ecm_scanner'))
from avr_interface import AvrTransport, InterfaceMode, AvrProtocolError

# Configuracoes
BAUD_KLINE    = 10400
INTER_TIMEOUT = 4      # ms: AVR para de coletar apos este silencio (= separador de frame)
FIRST_TIMEOUT = 200    # ms: espera pelo 1o byte (mais alto = nao perde inicio)
MAX_BYTES     = 28


def connect(port, baud_kline):
    print('Conectando em %s ...' % port)
    avr = AvrTransport(port)
    avr.connect()
    info = avr.get_info()
    print('  AVR proto_version=%d  mode=%d' % (info.get('proto_version', 0), info.get('mode', 0)))
    avr.set_mode(InterfaceMode.KLINE)
    avr.kline_set_baud(baud_kline)
    print('  Modo KLINE  baud=%d' % baud_kline)
    return avr


def byte_bits(b):
    return format(b, '08b')


def sniff_loop(avr, csv_path=None):
    csv_file = None
    csv_writer = None
    if csv_path:
        csv_file = open(csv_path, 'w', newline='')
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['frame_idx', 't_ms', 'gap_ms', 'len', 'hex', 'bytes_dec'])
        print('  Gravando em: %s' % csv_path)

    print()
    print('=' * 72)
    print('  SNIFF K-LINE %d BAUD  --  Yamaha WaveRunner VX110' % BAUD_KLINE)
    print('  Ctrl+C para parar')
    print('  frame_idx  t_ms      gap_ms  len  bytes')
    print('-' * 72)

    frame_idx   = 0
    t_start     = time.monotonic()
    total_bytes = 0
    byte_stats  = {}
    size_stats  = {}
    last_t_ms   = None

    # Buffer acumulador: o AVR ja faz a separacao de frames pelo inter_timeout
    # Cada chamada kline_rx_bulk retorna UM frame (ou fragmento se muito longo)
    # Acumulamos aqui por seguranca
    frag_buf    = bytearray()
    t_frag_start = None

    try:
        while True:
            try:
                chunk = avr.kline_rx_bulk(
                    first_timeout_ms=FIRST_TIMEOUT,
                    inter_timeout_ms=INTER_TIMEOUT,
                    max_bytes=MAX_BYTES,
                )
            except AvrProtocolError as e:
                err = str(e)
                if len(err) > 3 and 'timeout' not in err.lower():
                    print('  [ERR] %s' % err)
                chunk = b''

            now     = time.monotonic()
            now_ms  = (now - t_start) * 1000.0

            if chunk:
                total_bytes += len(chunk)
                if not frag_buf:
                    t_frag_start = now_ms
                frag_buf.extend(chunk)

                # Se o AVR retornou menos que MAX_BYTES, o inter_timeout encerrou
                # o frame -- podemos fazer flush imediato
                if len(chunk) < MAX_BYTES:
                    _flush_frame(frag_buf, t_frag_start, frame_idx,
                                 last_t_ms, byte_stats, size_stats, csv_writer)
                    last_t_ms  = t_frag_start
                    frame_idx += 1
                    frag_buf.clear()
                    t_frag_start = None
            else:
                # Sem dados: flush qualquer fragmento pendente
                if frag_buf:
                    _flush_frame(frag_buf, t_frag_start, frame_idx,
                                 last_t_ms, byte_stats, size_stats, csv_writer)
                    last_t_ms  = t_frag_start
                    frame_idx += 1
                    frag_buf.clear()
                    t_frag_start = None

    except KeyboardInterrupt:
        # Flush final
        if frag_buf:
            _flush_frame(frag_buf, t_frag_start, frame_idx,
                         last_t_ms, byte_stats, size_stats, csv_writer)
            frame_idx += 1

        print()
        print('=' * 72)
        elapsed = time.monotonic() - t_start
        print('  PARADO  --  %d frames  %d bytes  %.1fs' % (frame_idx, total_bytes, elapsed))

        if byte_stats:
            print()
            print('  TOP 10 BYTES (valor : contagem : bits):')
            top = sorted(byte_stats.items(), key=lambda x: -x[1])[:10]
            for bv, cnt in top:
                pct = 100.0 * cnt / max(1, total_bytes)
                print('    0x%02X = %s : %4d  (%.1f%%)' % (bv, byte_bits(bv), cnt, pct))

        if size_stats:
            print()
            print('  TAMANHOS DE FRAME: %s' % sorted(size_stats.items()))

        print('=' * 72)

    finally:
        if csv_file:
            csv_file.close()
            print('  CSV salvo: %s' % csv_path)


def _flush_frame(buf, t_ms, idx, last_t_ms, byte_stats, size_stats, csv_writer):
    if not buf:
        return
    data   = bytes(buf)
    n      = len(data)
    hex_s  = ' '.join('%02X' % b for b in data)
    gap_ms = (t_ms - last_t_ms) if last_t_ms is not None else 0.0

    # Exibir na tela
    print('[%04d]  %8.1f  %6.1f  %3d  %s' % (idx, t_ms, gap_ms, n, hex_s))

    # CSV
    if csv_writer:
        dec_s = ' '.join(str(b) for b in data)
        csv_writer.writerow([idx, round(t_ms, 2), round(gap_ms, 2), n, hex_s, dec_s])

    # Estatisticas
    for b in data:
        byte_stats[b] = byte_stats.get(b, 0) + 1
    size_stats[n] = size_stats.get(n, 0) + 1


def main():
    args     = sys.argv[1:]
    port     = 'COM7'
    baud     = BAUD_KLINE
    csv_path = None

    i = 0
    while i < len(args):
        a = args[i]
        if a.upper().startswith('COM') or a.startswith('/dev/'):
            port = a
        elif a == '--csv' and i + 1 < len(args):
            csv_path = args[i + 1]
            i += 1
        else:
            try:
                baud = int(a)
            except ValueError:
                pass
        i += 1

    try:
        avr = connect(port, baud)
    except Exception as e:
        print('ERRO de conexao: %s' % e)
        sys.exit(1)

    sniff_loop(avr, csv_path=csv_path)


if __name__ == '__main__':
    main()

