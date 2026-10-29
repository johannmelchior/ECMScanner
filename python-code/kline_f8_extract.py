#!/usr/bin/env python3
"""Extrai um resumo curto de sequencias Yamaha iniciadas por 0xF8.

Uso:
  python kline_f8_extract.py <arquivo1> [arquivo2 ...] [baud]
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path


THRESHOLD = 2.0
TOTAL_CAPTURE_S = 5.0
DEFAULT_BAUD = 15625
TOP_N = 8
PREVIEW_N = 10
PROGRESS_STEP = 250_000


class ProgressLog:
    def __init__(self, path: Path | None):
        self.path = path
        self.start_time = time.perf_counter()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def write(self, message: str) -> None:
        if self.path is None:
            return
        elapsed = time.perf_counter() - self.start_time
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{elapsed:8.3f}s] {message}\n")


def load_capture(path: Path, progress: ProgressLog) -> tuple[list[int], float]:
    progress.write(f"load_capture:start path={path}")
    samples: list[float] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        text = line.strip()
        if text and not text.startswith("#"):
            samples.append(float(text))
        if line_number % PROGRESS_STEP == 0:
            progress.write(f"load_capture:line={line_number} samples={len(samples)}")

    if not samples:
        raise ValueError(f"arquivo sem amostras: {path}")

    sample_period_us = TOTAL_CAPTURE_S * 1e6 / len(samples)
    bits = [1 if value > THRESHOLD else 0 for value in samples]
    progress.write(f"load_capture:done samples={len(samples)} sample_period_us={sample_period_us:.6f}")
    return bits, sample_period_us


def find_active_start(bits: list[int], progress: ProgressLog) -> int:
    progress.write(f"find_active_start:start bits={len(bits)}")
    for index in range(1, len(bits) - 10):
        if bits[index] == 1 and all(bits[index + offset] == 1 for offset in range(5)):
            progress.write(f"find_active_start:found index={index}")
            return index
        if index % PROGRESS_STEP == 0:
            progress.write(f"find_active_start:index={index}")
    progress.write("find_active_start:fallback index=0")
    return 0


def decode_uart(
    bits: list[int], sample_period_us: float, baud: int, start_index: int, progress: ProgressLog, max_bytes: int = 4000
) -> list[tuple[float, int, bool]]:
    progress.write(f"decode_uart:start baud={baud} start_index={start_index} max_bytes={max_bytes}")
    bit_samples = (1e6 / baud) / sample_period_us
    decoded: list[tuple[float, int, bool]] = []
    index = max(1, start_index)
    limit = len(bits) - int(10 * bit_samples) - 2
    progress.write(f"decode_uart:limit={limit} bit_samples={bit_samples:.3f}")

    while index < limit and len(decoded) < max_bytes:
        if bits[index - 1] == 1 and bits[index] == 0:
            byte_value = 0
            valid = True
            for bit_number in range(8):
                sample_pos = int(index + (bit_number + 1.5) * bit_samples)
                if sample_pos >= len(bits):
                    valid = False
                    break
                byte_value |= bits[sample_pos] << bit_number

            stop_pos = int(index + 9.5 * bit_samples)
            stop_ok = stop_pos < len(bits) and bits[stop_pos] == 1

            if valid:
                decoded.append((index * sample_period_us / 1000.0, byte_value, stop_ok))
                if len(decoded) % 500 == 0:
                    progress.write(f"decode_uart:decoded={len(decoded)} index={index} last_byte=0x{byte_value:02X} stop_ok={stop_ok}")
                index = max(index + 1, int(index + 10 * bit_samples))
                continue

        index += 1
        if index % PROGRESS_STEP == 0:
            progress.write(f"decode_uart:index={index} decoded={len(decoded)}")

    progress.write(f"decode_uart:done decoded={len(decoded)} final_index={index}")
    return decoded


def summarize_f8(decoded: list[tuple[float, int, bool]]) -> dict[str, object]:
    valid = [(timestamp_ms, byte_value) for timestamp_ms, byte_value, stop_ok in decoded if stop_ok]
    pairs: Counter[int] = Counter()
    triples: Counter[tuple[int, int]] = Counter()
    preview: list[tuple[float, int, int]] = []

    for idx in range(len(valid) - 1):
        if valid[idx][1] == 0xF8:
            pairs[valid[idx + 1][1]] += 1

    for idx in range(len(valid) - 2):
        if valid[idx][1] == 0xF8:
            byte1 = valid[idx + 1][1]
            byte2 = valid[idx + 2][1]
            triples[(byte1, byte2)] += 1
            if len(preview) < PREVIEW_N:
                preview.append((valid[idx][0], byte1, byte2))

    return {
        "valid_count": len(valid),
        "f8_count": sum(pairs.values()),
        "pairs": pairs.most_common(TOP_N),
        "triples": triples.most_common(TOP_N),
        "preview": preview,
    }


def print_summary(path: Path, baud: int, progress: ProgressLog) -> None:
    progress.write(f"print_summary:start path={path.name} baud={baud}")
    bits, sample_period_us = load_capture(path, progress)
    start_index = find_active_start(bits, progress)
    decoded = decode_uart(bits, sample_period_us, baud, start_index, progress)
    summary = summarize_f8(decoded)
    progress.write(
        f"print_summary:done valid_count={summary['valid_count']} f8_count={summary['f8_count']}"
    )

    print(f"=== {path.name} @ {baud} baud ===")
    print(f"inicio ativo: {start_index * sample_period_us / 1000.0:.3f} ms")
    print(f"bytes validos: {summary['valid_count']}")
    print(f"ocorrencias F8: {summary['f8_count']}")
    print("top F8 -> byte:")
    for value, count in summary["pairs"]:
        print(f"  F8 {value:02X} : {count}")
    print("top F8 -> byte1 -> byte2:")
    for (byte1, byte2), count in summary["triples"]:
        print(f"  F8 {byte1:02X} {byte2:02X} : {count}")
    print("primeiras sequencias:")
    for timestamp_ms, byte1, byte2 in summary["preview"]:
        print(f"  t={timestamp_ms:8.3f} ms  F8 {byte1:02X} {byte2:02X}")


def parse_args(argv: list[str]) -> tuple[list[Path], int, Path | None]:
    if not argv:
        raise SystemExit("uso: python kline_f8_extract.py <arquivo1> [arquivo2 ...] [baud] [--log caminho]")

    baud = DEFAULT_BAUD
    log_path: Path | None = None
    args: list[str] = []
    pending = list(argv)
    index = 0
    while index < len(pending):
        arg = pending[index]
        if arg == "--log":
            if index + 1 >= len(pending):
                raise SystemExit("faltou caminho apos --log")
            log_path = Path(pending[index + 1])
            index += 2
            continue
        args.append(arg)
        index += 1

    if args[-1].isdigit():
        baud = int(args.pop())

    paths = [Path(arg) for arg in args]
    if not paths:
        raise SystemExit("nenhum arquivo informado")

    return paths, baud, log_path


def main(argv: list[str]) -> int:
    paths, baud, log_path = parse_args(argv)
    progress = ProgressLog(log_path)
    progress.write(f"main:start files={len(paths)} baud={baud}")
    for index, path in enumerate(paths):
        if index:
            print()
        print_summary(path, baud, progress)
    progress.write("main:done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))