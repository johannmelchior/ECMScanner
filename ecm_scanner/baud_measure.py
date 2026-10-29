"""
Medição precisa do baud rate real da K-Line — varredura fina no hardware.

Conecta ao AVR, testa sistematicamente todos os bauds possíveis (derivados dos
registradores UBRR do AVR a 8 MHz) e mede a taxa de Framing Errors (FE) em
cada um. O baud com menor FE% É o baud real do barramento.

Como funciona:
  O UART do AVR (8 MHz) só aceita baud rates que derivam de:
    baud = 8_000_000 / (16 × (UBRR + 1))   [modo normal]
    baud = 8_000_000 / ( 8 × (UBRR + 1))   [modo U2X]

  Para cada UBRR de 0..511 geramos os dois modos → lista única de bauds reais
  entre 8000 e 50000. Testamos todos, 2 s cada.

  No baud correto:
    - FE% cai a ~0%  (stop bit amostrado como HIGH = OK)
    - Contagem de bytes sobe (ECM transmite regularmente)
    - Os valores recebidos são repetitivos / reconhecíveis

ATENÇÃO: feche o ECM Scanner GUI antes de rodar este script.
Requer firmware com CMD_KLINE_RX_BULK_RAW (proto >= 0x1C).

Uso:
  python baud_measure.py [porta] [--fine] [--range MIN MAX]

  --fine       varredura fina em torno do melhor candidato (±300 baud, passo 10)
  --range      limita a faixa testada, ex: --range 14000 18000

Exemplos:
  python baud_measure.py COM7
  python baud_measure.py COM7 --fine
  python baud_measure.py COM7 --range 14000 18000 --fine
"""
import sys
import time
import argparse
from collections import Counter

# Permite rodar de qualquer diretório
import os
sys.path.insert(0, os.path.dirname(__file__))
from avr_interface import AvrTransport, InterfaceMode

CPU_HZ   = 8_000_000
WINDOW_S = 2.0          # segundos por baud na varredura principal
FINE_WINDOW_S = 1.5     # segundos por baud na varredura fina


def avr_baud_list(baud_min=8000, baud_max=50000):
    """Gera todos os bauds reais do AVR 8 MHz para UBRR 0..511 (normal + U2X)."""
    bauds = set()
    for ubrr in range(512):
        for divisor in (16, 8):
            b = CPU_HZ // (divisor * (ubrr + 1))
            if baud_min <= b <= baud_max:
                bauds.add(b)
    return sorted(bauds)


def fine_sweep(near_baud, step=10, radius=400, baud_min=8000, baud_max=50000):
    """Lista de bauds para varredura fina em torno de near_baud."""
    bauds = set()
    for b in range(near_baud - radius, near_baud + radius + 1, step):
        if baud_min <= b <= baud_max:
            bauds.add(b)
    return sorted(bauds)


def sample_baud(transport: AvrTransport, baud: int, window_s: float):
    """
    Seta o baud no AVR, lê por window_s segundos via BULK_RAW.
    Retorna (raw_count, error_count, bytes_sample).
    """
    transport.kline_set_baud(baud)
    time.sleep(0.08)    # AVR precisa de ~1 frame para trocar UBRR

    end = time.monotonic() + window_s
    raw_total   = 0
    err_total   = 0
    buf_sample  = bytearray()

    while time.monotonic() < end:
        try:
            chunk, errs = transport.kline_rx_bulk_raw(
                first_timeout_ms=45,
                inter_timeout_ms=4,
                max_bytes=26,
            )
            raw_total  += len(chunk)
            err_total  += errs
            if len(buf_sample) < 64:
                buf_sample.extend(chunk)
        except TimeoutError:
            pass
        except Exception as exc:
            print(f"  [warn] baud={baud}: {exc}")
            break

    return raw_total, err_total, bytes(buf_sample)


def score(raw, errs):
    """Pontuação: premia alto raw E baixo erro.  0 = nenhum dado."""
    if raw == 0:
        return float('inf')
    fe_pct = errs / raw * 100.0
    # Penaliza FE exponencialmente; bonus por volume
    return fe_pct + 100.0 / max(raw, 1)


def print_bar(fe_pct, width=40):
    filled = int((100.0 - fe_pct) / 100.0 * width)
    filled = max(0, min(width, filled))
    return '█' * filled + '░' * (width - filled)


def run_sweep(transport, bauds, window_s, label="varredura"):
    print(f"\n{'─'*72}")
    print(f"  {label}  ({len(bauds)} bauds × {window_s:.1f}s = "
          f"~{len(bauds)*window_s/60:.1f} min)")
    print(f"{'─'*72}")
    print(f"  {'baud':>7}  {'raw':>5}  {'FE':>5}  {'FE%':>6}  barra(OK%)   bytes")
    print(f"{'─'*72}")

    results = []
    for baud in bauds:
        raw, errs, sample = sample_baud(transport, baud, window_s)
        fe_pct = (errs / max(raw, 1)) * 100.0
        s      = score(raw, errs)
        common = ' '.join(f'{b:02X}' for b in Counter(sample).keys()
                          if sample.count(b) > 1)[:24]
        bar    = print_bar(fe_pct)
        print(f"  {baud:>7}  {raw:>5}  {errs:>5}  {fe_pct:>5.1f}%  {bar}  {common}")
        results.append((baud, raw, errs, fe_pct, sample))

    return results


def best_candidates(results, n=5):
    """Retorna os n melhores bauds (menor FE%, desempate pelo maior raw)."""
    # Só considera bauds que receberam pelo menos 5 bytes
    valid = [(b, r, e, fp, s) for (b, r, e, fp, s) in results if r >= 5]
    if not valid:
        return []
    valid.sort(key=lambda x: (x[3], -x[1]))   # FE% asc, raw desc
    return valid[:n]


# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("port", nargs="?", default="COM7", help="Porta COM do AVR")
    parser.add_argument("--fine", action="store_true",
                        help="Varredura fina em torno do melhor candidato")
    parser.add_argument("--range", nargs=2, type=int, metavar=("MIN", "MAX"),
                        default=[8000, 30000],
                        help="Faixa de bauds a testar (default: 8000-30000)")
    args = parser.parse_args()

    baud_min, baud_max = args.range
    all_avr_bauds = avr_baud_list(baud_min, baud_max)

    print("=" * 72)
    print("  AVR K-Line Baud Rate Meter")
    print(f"  CPU: {CPU_HZ/1e6:.0f} MHz  Faixa: {baud_min}–{baud_max} baud")
    print(f"  Bauds AVR disponíveis nessa faixa: {len(all_avr_bauds)}")
    print(f"  Porta: {args.port}")
    print("=" * 72)
    print("ATENÇÃO: mantenha o motor/ignição LIGADO e feche o GUI Scanner.")
    input("  Pressione ENTER para iniciar a varredura...")

    t = AvrTransport(args.port)
    try:
        t.connect()
        t.set_mode(InterfaceMode.KLINE)

        # ── Fase 1: varredura principal ──────────────────────────────────────
        results = run_sweep(t, all_avr_bauds, WINDOW_S, "Fase 1 — varredura principal")

        best = best_candidates(results, n=5)

        print(f"\n{'═'*72}")
        print("  TOP-5 candidatos (menor FE%):")
        for rank, (baud, raw, errs, fe_pct, sample) in enumerate(best, 1):
            head = ' '.join(f'{b:02X}' for b in sample[:20])
            print(f"  #{rank}  baud={baud:>7}  raw={raw:>4}  FE={errs:>4} ({fe_pct:5.1f}%)  "
                  f"bytes: {head}")

        if not best:
            print("  Nenhum dado recebido. Verifique fiação e ignição.")
            return

        winner = best[0]
        print(f"\n  ► Melhor candidato: {winner[0]} baud  (FE={winner[3]:.1f}%)")

        # ── Fase 2: varredura fina (opcional) ───────────────────────────────
        if args.fine:
            fine_bauds = fine_sweep(winner[0], step=10, radius=400,
                                    baud_min=baud_min, baud_max=baud_max)
            fine_results = run_sweep(t, fine_bauds, FINE_WINDOW_S,
                                     f"Fase 2 — varredura fina ±400 em torno de {winner[0]}")

            fine_best = best_candidates(fine_results, n=3)
            print(f"\n{'═'*72}")
            print("  Resultado FINO — TOP-3:")
            for rank, (baud, raw, errs, fe_pct, sample) in enumerate(fine_best, 1):
                head = ' '.join(f'{b:02X}' for b in sample[:20])
                bit_period_us = 1_000_000 / baud
                print(f"  #{rank}  baud={baud:>7}  FE={fe_pct:5.1f}%  "
                      f"bit={bit_period_us:.2f}µs  bytes: {head}")

            if fine_best:
                final = fine_best[0]
                print(f"\n  ► Baud REAL estimado: {final[0]} baud")
                print(f"     Bit period: {1_000_000/final[0]:.2f} µs")
                print(f"     FE na janela de confirmação: {final[3]:.1f}%")
        else:
            print(f"\n  Dica: rode com --fine para refinar em torno de {winner[0]}")

        print(f"\n{'='*72}")

    finally:
        try:
            t.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
