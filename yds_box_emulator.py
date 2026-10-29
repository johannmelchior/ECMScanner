#!/usr/bin/env python3
"""Emula a caixa Yamaha no fim virtual do com0com, para o YDS falar com ela.

Como o `YDS.exe` descompilado mostra exactamente o que a caixa responde
(`FUN_004798f0` e `FUN_0047a120`), é possível completar a abertura sem
equipamento nenhum. A partir daí, **todos os bytes que o YDS envia** — os
comandos de DTC, actuação e monitor que faltam mapear — passam a ser visíveis.

Uso (com o par com0com criado, YDS em COM1 e emulador em COM2):

    python yds_box_emulator.py --port COM2 --log C:\\Temp\\yds_emu
    python yds_box_emulator.py --port COM2 --variant b      # 0xE5 -> 0xED
    python yds_box_emulator.py --port COM2 --no-echo        # transporte directo
    python yds_box_emulator.py --port COM2 --set 21=61 --set 30=70

O log sai no mesmo formato do `serial_bridge.py`, por isso
`yds_capture_decode.py` lê-o sem alterações.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("pyserial em falta: pip install pyserial", file=sys.stderr)
    raise SystemExit(2)

WAKE_BYTE = 0x1C
LADDER = (0xF0, 0xEF, 0xEE, 0xED, 0xEC, 0xE4, 0xE3, 0xE2, 0xE1, 0xE0)

# Respostas reconstruidas do descompilado (FUN_004798f0 / FUN_0047a120).
BASE_RESPONSES = {
    0x1C: None,   # wake-up: o YDS fecha e reabre, nao le resposta
    0xFD: 0x00,
    0xE5: 0xEF,   # variante A (0xED = variante B)
    0xFE: 0x11,
    0xFF: 0x22,
    0xF0: 0xAA,   # primeiro degrau da escada a responder
}


class BoxEmulator:
    def __init__(self, port, log_path, echo=True, responses=None,
                 default_response=0x00, quiet=False):
        self.port = port
        self.log_path = log_path
        self.echo = echo
        self.responses = dict(BASE_RESPONSES)
        if responses:
            self.responses.update(responses)
        self.default_response = default_response
        self.quiet = quiet
        self._stop = threading.Event()
        self.t_start = time.monotonic()
        self.counts = {}
        self._log = None

    # -- log ---------------------------------------------------------------
    def _open_log(self):
        if not self.log_path:
            return
        base = Path(self.log_path)
        base.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = base.with_name(f"{base.name}_{stamp}.txt")
        self._log = open(path, "w", encoding="utf-8")
        self.log_file = path

    def _write(self, direction, value):
        if self._log is None:
            return
        t = time.monotonic() - self.t_start
        self._log.write(f"[{t:09.3f}] {direction} [  1] {value:02X}  |.|\n")
        self._log.flush()

    def _say(self, text):
        if not self.quiet:
            print(text)

    # -- laco principal ----------------------------------------------------
    def run(self):
        self._open_log()
        self._say("=" * 68)
        self._say(f"  EMULADOR DE CAIXA YDS  porta {self.port}")
        self._say(f"  eco: {'sim' if self.echo else 'nao'}   "
                  f"resposta por omissao: 0x{self.default_response:02X}")
        if self._log is not None:
            self._say(f"  log: {self.log_file}")
        self._say("=" * 68)

        try:
            ser = serial.Serial(self.port, 9600, timeout=0.05)
        except Exception as exc:
            print(f"nao abriu {self.port}: {exc}", file=sys.stderr)
            return 1

        self._say("  a escutar... (Ctrl+C para terminar)")
        try:
            while not self._stop.is_set():
                try:
                    data = ser.read(64)
                except (serial.SerialException, OSError) as exc:
                    # O YDS fecha e reabre a porta depois do 0x1C; o nosso lado
                    # do par pode cair. Reabrir em vez de terminar.
                    self._say(f"  porta perdeu-se ({exc}); a reabrir...")
                    try:
                        ser.close()
                    except Exception:
                        pass
                    time.sleep(0.2)
                    try:
                        ser = serial.Serial(self.port, 9600, timeout=0.05)
                    except Exception:
                        continue
                    self._say("  porta reaberta")
                    continue
                if not data:
                    continue
                for value in data:
                    self._handle(ser, value)
        except KeyboardInterrupt:
            self._say("\n  terminado pelo utilizador")
        finally:
            ser.close()
            if self._log is not None:
                self._log.close()
            self._summary()
        return 0

    def _handle(self, ser, value):
        self.counts[value] = self.counts.get(value, 0) + 1
        self._write("TX", value)
        if not self.quiet:
            print(f"  << YDS 0x{value:02X}")

        if value == WAKE_BYTE:
            return

        try:
            if self.echo:
                ser.write(bytes([value]))
                self._write("RX", value)

            response = self.responses.get(value, self.default_response)
            if value in LADDER and value not in self.responses:
                response = None          # escada: so 0xF0 responde
            if response is None:
                return

            ser.write(bytes([response]))
            self._write("RX", response)
            if not self.quiet:
                print(f"  >> box 0x{response:02X}")
        except (serial.SerialException, OSError) as exc:
            self._say(f"  escrita falhou ({exc})")
            raise

    def _summary(self):
        if not self.counts:
            self._say("  nenhum byte recebido do YDS")
            return
        self._say("\n  bytes enviados pelo YDS nesta sessao:")
        for value in sorted(self.counts):
            self._say(f"    0x{value:02X}  x{self.counts[value]}")
        unknown = [v for v in sorted(self.counts)
                   if v not in BASE_RESPONSES and not (v in LADDER)]
        if unknown:
            self._say("  novos (candidatos a comando): "
                      + " ".join(f"{v:02X}" for v in unknown))


def parse_sets(values):
    table = {}
    for item in values or []:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"esperado XX=YY, recebido {item!r}")
        src, dst = item.split("=", 1)
        value = int(dst, 16)
        table[int(src, 16)] = value if value >= 0 else None
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="COM2",
                        help="Fim virtual do par com0com onde o YDS nao esta. Padrao: COM2")
    parser.add_argument("--log", default="C:\\Temp\\yds_emu",
                        help="Prefixo do log. Padrao: C:\\Temp\\yds_emu")
    parser.add_argument("--no-log", dest="log", action="store_const", const=None)
    parser.add_argument("--variant", choices=("a", "b"), default="a",
                        help="Variante: a => 0xE5 responde 0xEF; b => 0xED. Padrao: a")
    parser.add_argument("--no-echo", dest="echo", action="store_false", default=True,
                        help="Nao devolver o eco de cada byte")
    parser.add_argument("--set", dest="sets", action="append", metavar="XX=YY",
                        help="Resposta fixa para um byte (hex). Ex.: --set 21=61")
    parser.add_argument("--default-response", default="00",
                        help="Resposta para bytes desconhecidos (hex). Padrao: 00")
    parser.add_argument("--quiet", action="store_true",
                        help="Sem impressao byte a byte")
    args = parser.parse_args()

    responses = parse_sets(args.sets)
    responses[0xE5] = 0xEF if args.variant == "a" else 0xED

    emulator = BoxEmulator(
        port=args.port,
        log_path=args.log,
        echo=args.echo,
        responses=responses,
        default_response=int(args.default_response, 16),
        quiet=args.quiet,
    )
    return emulator.run()


if __name__ == "__main__":
    raise SystemExit(main())
