"""
_test_baud.py -- diagnostico de baud K-Line via kline_rx_bulk_raw

Le bytes RAW (inclusive com framing error) e mostra:
  - Taxa de erros: se 0% -> baud correto, E0 e dado real
  - Se alta -> baud errado, precisamos ajustar
  - Distribuicao de bytes e pares (bigrams)

Uso:  python _test_baud.py [COM] [baud]
      python _test_baud.py COM7 10400   (padrao)
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ecm_scanner'))
from avr_interface import AvrTransport, InterfaceMode, AvrProtocolError

PORT  = 'COM7'
BAUD  = 10400
LOOPS = 60

for arg in sys.argv[1:]:
    if arg.upper().startswith('COM') or arg.startswith('/dev/'):
        PORT = arg
    else:
        try:
            BAUD = int(arg)
        except ValueError:
            pass

avr = AvrTransport(PORT)
avr.connect()
info = avr.get_info()
print('AVR:', info)

avr.set_mode(InterfaceMode.KLINE)
avr.kline_set_baud(BAUD)
print('KLINE baud=%d\n' % BAUD)

total_bytes  = 0
total_errors = 0
byte_stats   = {}
last_byte    = None
bigram_stats = {}

print('%-5s  %-5s  %-5s  %-20s  nota' % ('iter', 'recv', 'FE', 'hex'))
print('-' * 65)

for i in range(LOOPS):
    try:
        raw, err_count = avr.kline_rx_bulk_raw(
            first_timeout_ms=200,
            inter_timeout_ms=4,
            max_bytes=26,
        )
    except AvrProtocolError as e:
        print('[%03d]  ERR: %s' % (i, e))
        raw, err_count = b'', 0

    n = len(raw)
    total_bytes  += n
    total_errors += err_count

    hex_s = ' '.join('%02X' % b for b in raw)
    note  = ('** %d FE **' % err_count) if err_count else 'OK'
    if n:
        print('[%03d]  %-5d  %-5d  %-20s  %s' % (i, n, err_count, hex_s, note))

    for b in raw:
        byte_stats[b] = byte_stats.get(b, 0) + 1
        if last_byte is not None:
            bg = (last_byte, b)
            bigram_stats[bg] = bigram_stats.get(bg, 0) + 1
        last_byte = b

print()
print('=' * 65)
print('TOTAL bytes  : %d' % total_bytes)
print('TOTAL FE     : %d' % total_errors)
if total_bytes:
    pct = 100.0 * total_errors / total_bytes
    print('Erro ratio   : %.1f%%' % pct)
    if pct < 5:
        print('=> BAUD CORRETO: %d baud confirmado, E0 = dado real da ECM' % BAUD)
    elif pct < 30:
        print('=> BAUD PROXIMO mas com erros -- tente 9600 ou 10000')
    else:
        print('=> BAUD ERRADO -- muitos erros de framing')

if byte_stats:
    print()
    print('TOP BYTES:')
    for bv, cnt in sorted(byte_stats.items(), key=lambda x: -x[1])[:10]:
        pct2 = 100.0 * cnt / total_bytes
        print('  0x%02X  %s  x%d  %.1f%%' % (bv, format(bv, '08b'), cnt, pct2))

if bigram_stats:
    print()
    print('TOP BIGRAMS (pares de bytes consecutivos):')
    for (a, b), cnt in sorted(bigram_stats.items(), key=lambda x: -x[1])[:10]:
        print('  %02X %02X  x%d' % (a, b, cnt))
