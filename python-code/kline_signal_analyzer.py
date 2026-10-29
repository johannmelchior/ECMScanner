#!/usr/bin/env python3
"""
kline_signal_analyzer.py

Analisador de trafego serial bruto para interface K-Line em modo passthrough.

Objetivo:
- Ler bytes crus da COM (sem interpretar protocolo)
- Separar rajadas por gap de tempo
- Exibir estatisticas de frequencia e timing para entender o comportamento da linha

Exemplo:
  python python-code/kline_signal_analyzer.py --port COM1 --baud 1000000
  python python-code/kline_signal_analyzer.py --port COM1 --baud 500000 --gap-ms 4 --summary-every 5
  python python-code/kline_signal_analyzer.py --port COM1 --baud 1000000 --csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional

import serial


@dataclass
class Frame:
    start_s: float
    end_s: float
    gap_before_ms: float
    data: bytes


class StreamAnalyzer:
    def __init__(
        self,
        gap_ms: float,
        show_empty: bool,
        show_ascii: bool,
        max_print_len: int,
    ) -> None:
        self.gap_s = max(0.0001, gap_ms / 1000.0)
        self.show_empty = show_empty
        self.show_ascii = show_ascii
        self.max_print_len = max(8, max_print_len)

        self.frames: List[Frame] = []
        self.current = bytearray()
        self.current_start_s: Optional[float] = None
        self.last_byte_s: Optional[float] = None

        self.byte_counter = Counter()
        self.frame_len_counter = Counter()
        self.gap_counter_ms = Counter()
        self.total_bytes = 0
        self.start_s = time.monotonic()

    def _ascii_preview(self, data: bytes) -> str:
        out = []
        for b in data:
            if 32 <= b <= 126:
                out.append(chr(b))
            else:
                out.append(".")
        return "".join(out)

    def _format_hex(self, data: bytes) -> str:
        if len(data) <= self.max_print_len:
            return " ".join(f"{b:02X}" for b in data)
        head = " ".join(f"{b:02X}" for b in data[: self.max_print_len])
        return f"{head} ... (+{len(data) - self.max_print_len} bytes)"

    def _close_frame(self, now_s: float, gap_before_ms: float) -> None:
        if not self.current:
            return
        frame_data = bytes(self.current)
        frame = Frame(
            start_s=self.current_start_s if self.current_start_s is not None else now_s,
            end_s=now_s,
            gap_before_ms=gap_before_ms,
            data=frame_data,
        )
        self.frames.append(frame)
        self.frame_len_counter[len(frame_data)] += 1
        self.gap_counter_ms[round(gap_before_ms, 1)] += 1

        rel_t = frame.start_s - self.start_s
        dur_ms = (frame.end_s - frame.start_s) * 1000.0
        line = (
            f"[{rel_t:8.3f}s] gap={gap_before_ms:7.3f} ms "
            f"len={len(frame_data):3d} dur={dur_ms:6.2f} ms  "
            f"{self._format_hex(frame_data)}"
        )
        if self.show_ascii:
            line += f"  |{self._ascii_preview(frame_data[: self.max_print_len])}|"
        print(line)

        self.current.clear()
        self.current_start_s = None

    def ingest(self, data: bytes, now_s: float) -> None:
        if not data:
            return

        for b in data:
            byte_time_s = now_s
            if self.last_byte_s is None:
                self.current_start_s = byte_time_s
            else:
                gap_s = byte_time_s - self.last_byte_s
                if gap_s >= self.gap_s:
                    self._close_frame(byte_time_s, gap_s * 1000.0)
                    self.current_start_s = byte_time_s

            self.current.append(b)
            self.byte_counter[b] += 1
            self.total_bytes += 1
            self.last_byte_s = byte_time_s

    def flush_on_idle(self, now_s: float) -> None:
        if not self.current or self.last_byte_s is None:
            return
        idle_s = now_s - self.last_byte_s
        if idle_s >= self.gap_s:
            self._close_frame(now_s, idle_s * 1000.0)

    def print_summary(self) -> None:
        elapsed = max(0.001, time.monotonic() - self.start_s)
        bps = self.total_bytes / elapsed
        print("\n=== RESUMO ===")
        print(f"tempo: {elapsed:.2f}s")
        print(f"bytes totais: {self.total_bytes}")
        print(f"taxa media: {bps:.1f} B/s")
        print(f"frames detectados: {len(self.frames)}")

        if self.byte_counter:
            print("top bytes:")
            for value, count in self.byte_counter.most_common(12):
                print(f"  0x{value:02X}: {count}")

        if self.frame_len_counter:
            print("tamanho de frames (top):")
            for flen, count in self.frame_len_counter.most_common(12):
                print(f"  len={flen}: {count}")

        if self.gap_counter_ms:
            print("gaps entre frames (ms, top):")
            for gap_ms, count in self.gap_counter_ms.most_common(12):
                print(f"  {gap_ms:>6}: {count}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analisador serial bruto para K-Line passthrough")
    p.add_argument("--port", required=True, help="Porta serial, ex.: COM1")
    p.add_argument("--baud", type=int, default=1_000_000, help="Baud da COM host<->interface")
    p.add_argument("--gap-ms", type=float, default=3.5, help="Gap para separar frames")
    p.add_argument("--timeout", type=float, default=0.02, help="Timeout de leitura serial (s)")
    p.add_argument("--summary-every", type=float, default=10.0, help="Intervalo de resumo periodico (s)")
    p.add_argument("--max-print-len", type=int, default=32, help="Max de bytes exibidos por frame")
    p.add_argument("--ascii", action="store_true", help="Mostra preview ASCII")
    p.add_argument("--show-empty", action="store_true", help="Reservado para debug")
    p.add_argument("--csv", default="", help="Arquivo CSV para log (opcional)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    analyzer = StreamAnalyzer(
        gap_ms=args.gap_ms,
        show_empty=args.show_empty,
        show_ascii=args.ascii,
        max_print_len=args.max_print_len,
    )

    csv_file = None
    csv_writer = None
    if args.csv:
        csv_file = open(args.csv, "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["t_s", "len", "gap_before_ms", "hex"])

    print(
        f"Abrindo {args.port} @ {args.baud} 8N1, gap={args.gap_ms} ms. "
        "Ctrl+C para encerrar."
    )

    next_summary = time.monotonic() + max(0.5, args.summary_every)

    try:
        with serial.Serial(args.port, args.baud, timeout=args.timeout) as ser:
            ser.reset_input_buffer()
            while True:
                chunk = ser.read(512)
                now_s = time.monotonic()
                if chunk:
                    analyzer.ingest(chunk, now_s)
                else:
                    analyzer.flush_on_idle(now_s)

                if csv_writer is not None and analyzer.frames:
                    while analyzer.frames:
                        fr = analyzer.frames.pop(0)
                        rel_t = fr.start_s - analyzer.start_s
                        csv_writer.writerow([
                            f"{rel_t:.6f}",
                            len(fr.data),
                            f"{fr.gap_before_ms:.3f}",
                            " ".join(f"{b:02X}" for b in fr.data),
                        ])

                if now_s >= next_summary:
                    analyzer.print_summary()
                    next_summary = now_s + max(0.5, args.summary_every)

    except KeyboardInterrupt:
        print("\nInterrompido pelo usuario.")
    except serial.SerialException as exc:
        print(f"Erro serial: {exc}")
        return 2
    finally:
        analyzer.flush_on_idle(time.monotonic())
        analyzer.print_summary()
        if csv_file is not None:
            csv_file.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
