"""Multi-baud passive K-Line scan — inclui leitura RAW (com FE) para diagnostico.

Run while Yamaha network is active. The baud with the most raw bytes AND the
lowest error rate is the true baud.  A high raw count + low valid count means
wrong baud (FE on almost every byte).

IMPORTANT: close/disconnect any GUI scanner or keepalive before running this
script. Simultaneous TX from a keepalive causes bus collisions → false FE on
ALL bauds and corrupts the measurement.

Requires firmware proto >= 0x1C (CMD_KLINE_RX_BULK_RAW support).

---
DIAGNÓSTICO DE INVERSÃO DE SINAL:
  Se os bytes 'valid' forem quase todos 0x00/0x01, o hardware K-Line pode estar
  invertendo o sinal. Nesse caso, os bytes 'FE' (com framing error) são na
  verdade o dado real — o sinal está invertido e o UART os lê como FE porque
  o "stop bit" chega LOW ao invés de HIGH.
  Verifique o circuito do driver K-Line (ISO 9141 / TJA1021 etc.).
---
"""
import time
from collections import Counter
from avr_interface import AvrTransport, InterfaceMode

BAUDS    = [15873, 15625, 16129, 10400, 15384, 16040, 9600, 19200, 4800]
PORT     = "COM7"
WINDOW_S = 3.0   # seconds per baud

print(f"Testando {WINDOW_S:.1f}s por baud. Mantenha a rede ATIVA durante todo o scan.")
print("=" * 80)
print(f"  {'baud':>7}  {'raw':>5}  {'valid':>5}  {'FE':>5}  {'FE%':>6}  "
      f"{'bytes válidos (head)':30}  bytes FE (head)")
print("=" * 80)

for baud in BAUDS:
    try:
        t = AvrTransport(PORT)
        t.connect()
        t.set_mode(InterfaceMode.KLINE)
        t.kline_set_baud(baud)
        time.sleep(0.15)

        end           = time.monotonic() + WINDOW_S
        raw_all       = bytearray()
        valid_bytes   = bytearray()   # bytes sem FE (kline_rx_bulk)
        fe_bytes_buf  = bytearray()   # bytes COM FE isolados
        total_errs    = 0

        while time.monotonic() < end:
            # Raw: tudo que chegou (válidos + FE juntos, sem separação)
            try:
                raw_chunk, errs = t.kline_rx_bulk_raw(first_timeout_ms=45,
                                                       inter_timeout_ms=4,
                                                       max_bytes=26)
                raw_all.extend(raw_chunk)
                total_errs += errs
            except (TimeoutError, Exception):
                pass

        # Segunda janela curta: lê apenas bytes válidos para comparar
        t.kline_set_baud(baud)
        time.sleep(0.08)
        end2 = time.monotonic() + 1.0
        while time.monotonic() < end2:
            try:
                chunk = t.kline_rx_bulk(first_timeout_ms=45, inter_timeout_ms=4,
                                        max_bytes=28)
                valid_bytes.extend(chunk)
            except (TimeoutError, Exception):
                pass

        t.close()
        time.sleep(0.3)

        err_pct      = (total_errs / max(len(raw_all), 1)) * 100.0
        raw_head     = ' '.join(f'{b:02X}' for b in raw_all[:12])
        valid_head   = ' '.join(f'{b:02X}' for b in valid_bytes[:12])
        valid_count  = len(raw_all) - total_errs

        print(f"  {baud:>7}  {len(raw_all):>5}  {valid_count:>5}  "
              f"{total_errs:>5}  {err_pct:>5.1f}%  "
              f"{valid_head:36}  {raw_head}")

        # Alerta de inversão: se valid_bytes contém só 0x00/0x01
        valid_unique = set(valid_bytes)
        if valid_unique and valid_unique <= {0x00, 0x01, 0xFF, 0xFE}:
            print(f"          *** SUSPEITA DE INVERSÃO: valid só tem {sorted(valid_unique)} ***")

    except Exception as e:
        print(f"  {baud:>7}  ERRO: {e}")

print("\n" + "=" * 80)
print("Interpretacao:")
print("  Baud correto = menor FE%  (idealmente <5%)")
print("  valid só com 0x00/0x01 = possível inversão de sinal no hardware")
print("  Se FE% alto em TODOS => baud errado OU inversão/qualidade do sinal")
print("=== FIM ===")
