"""
_test_read.py -- teste rapido de leitura K-Line via AVR

Com a moto ligada deve receber:
  - idle: E0 / F0
  - rodando: FC 8C / 9C 8C / 20 8C (conforme osciloscópio)

Uso:  python _test_read.py [COM]
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ecm_scanner'))
from avr_interface import AvrTransport, InterfaceMode, AvrProtocolError

PORT  = sys.argv[1] if len(sys.argv) > 1 else 'COM7'
BAUD  = 10400
LOOPS = 80

avr = AvrTransport(PORT)
avr.connect()
info = avr.get_info()
print('AVR info:', info)

avr.set_mode(InterfaceMode.KLINE)
avr.kline_set_baud(BAUD)
print('Modo KLINE OK, baud=%d\n' % BAUD)

byte_stats = {}
size_stats = {}
total_bytes = 0

print('%-5s  %-5s  %-20s  %s' % ('frame', 'len', 'hex', 'binario'))
print('-' * 70)

for i in range(LOOPS):
    try:
        chunk = avr.kline_rx_bulk(first_timeout_ms=200, inter_timeout_ms=4, max_bytes=28)
    except AvrProtocolError:
        chunk = b''
    except Exception as e:
        print('[%03d]  ERR %s' % (i, e))
        chunk = b''

    if chunk:
        hex_s = ' '.join('%02X' % b for b in chunk)
        bin_s = ' '.join(format(b, '08b') for b in chunk)
        print('[%03d]  %-5d  %-20s  %s' % (i, len(chunk), hex_s, bin_s))
        for b in chunk:
            byte_stats[b] = byte_stats.get(b, 0) + 1
        size_stats[len(chunk)] = size_stats.get(len(chunk), 0) + 1
        total_bytes += len(chunk)

print()
print('TOTAL bytes: %d' % total_bytes)
if byte_stats:
    print('\nBYTES mais frequentes:')
    for bv, cnt in sorted(byte_stats.items(), key=lambda x: -x[1]):
        print('  0x%02X  %s  x%d' % (bv, format(bv, '08b'), cnt))
    print('\nTAMANHOS: ', sorted(size_stats.items()))
else:
    print('Nenhum dado -- moto desligada?')
