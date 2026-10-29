#!/usr/bin/env python3
"""Plot and timing analysis for oscilloscope TXT exports.

Expected input format:
    #CLOCK=<seconds> S
    #SIZE=<sample_count>
    #UNITS:<unit>
    <one sample value per line>
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_scope_txt(path: Path) -> tuple[np.ndarray, float, str, int, float]:
    clock_s = None
    size = None
    units = "V"
    samples: list[float] = []

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#CLOCK="):
            try:
                clock_s = float(line.split("=", 1)[1].split()[0])
            except Exception:
                clock_s = None
            continue
        if line.startswith("#SIZE="):
            try:
                size = int(line.split("=", 1)[1])
            except Exception:
                size = None
            continue
        if line.startswith("#UNITS:"):
            units = line.split(":", 1)[1].strip() or "V"
            continue
        if line.startswith("#"):
            continue
        try:
            samples.append(float(line))
        except ValueError:
            continue

    if not samples:
        raise ValueError("No numeric samples found in input file")

    arr = np.asarray(samples, dtype=float)
    n = len(arr)

    if clock_s and size and size > 0:
        sample_period_s = clock_s / float(size)
    elif clock_s:
        sample_period_s = clock_s / float(n)
    else:
        sample_period_s = 1.0 / 1_000_000.0

    fs_hz = 1.0 / sample_period_s
    return arr, sample_period_s, units, n, fs_hz


def choose_threshold(y: np.ndarray, user_threshold: float | None) -> float:
    if user_threshold is not None:
        return user_threshold
    low = float(np.percentile(y, 5))
    high = float(np.percentile(y, 95))
    return (low + high) / 2.0


def find_edges(levels: np.ndarray, sample_period_s: float) -> list[dict[str, float | int | str]]:
    edges: list[dict[str, float | int | str]] = []
    prev_time_s = None
    idx_edges = np.where(levels[1:] != levels[:-1])[0] + 1
    for edge_index, idx in enumerate(idx_edges, start=1):
        now_level = int(levels[idx])
        prev_level = int(levels[idx - 1])
        edge_type = "rising" if prev_level == 0 and now_level == 1 else "falling"
        t_s = idx * sample_period_s
        dt_prev_us = ""
        if prev_time_s is not None:
            dt_prev_us = (t_s - prev_time_s) * 1e6
        edges.append(
            {
                "edge_index": edge_index,
                "sample_index": int(idx),
                "time_s": t_s,
                "time_ms": t_s * 1e3,
                "edge": edge_type,
                "from_level": prev_level,
                "to_level": now_level,
                "dt_prev_us": dt_prev_us,
            }
        )
        prev_time_s = t_s
    return edges


def find_segments(levels: np.ndarray, sample_period_s: float) -> list[dict[str, float | int | str]]:
    segments: list[dict[str, float | int | str]] = []
    start = 0
    seg_index = 1
    for i in range(1, len(levels)):
        if levels[i] != levels[i - 1]:
            end = i - 1
            t0 = start * sample_period_s
            t1 = (end + 1) * sample_period_s
            segments.append(
                {
                    "segment_index": seg_index,
                    "level": int(levels[start]),
                    "start_sample": int(start),
                    "end_sample": int(end),
                    "start_s": t0,
                    "end_s": t1,
                    "duration_us": (t1 - t0) * 1e6,
                }
            )
            seg_index += 1
            start = i

    end = len(levels) - 1
    t0 = start * sample_period_s
    t1 = (end + 1) * sample_period_s
    segments.append(
        {
            "segment_index": seg_index,
            "level": int(levels[start]),
            "start_sample": int(start),
            "end_sample": int(end),
            "start_s": t0,
            "end_s": t1,
            "duration_us": (t1 - t0) * 1e6,
        }
    )
    return segments


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def decimate_for_plot(y: np.ndarray, max_points: int = 250_000) -> tuple[np.ndarray, np.ndarray]:
    n = len(y)
    if n <= max_points:
        return np.arange(n), y
    step = int(np.ceil(n / max_points))
    idx = np.arange(0, n, step)
    return idx, y[idx]


def make_plot(
    src_file: Path,
    y: np.ndarray,
    sample_period_s: float,
    units: str,
    threshold: float,
    levels: np.ndarray,
    edges: list[dict[str, object]],
    out_png: Path,
    show_interactive: bool,
) -> None:
    idx_plot, y_plot = decimate_for_plot(y)
    t_ms = idx_plot * sample_period_s * 1e3

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax1.plot(t_ms, y_plot, color="#1f77b4", linewidth=0.8, label="Signal")
    ax1.axhline(threshold, color="#d62728", linestyle="--", linewidth=1.0, label=f"Threshold {threshold:.4f}")

    if edges:
        edge_t_ms = [float(e["time_ms"]) for e in edges]
        ax1.vlines(edge_t_ms, ymin=float(np.min(y_plot)), ymax=float(np.max(y_plot)), color="#ff7f0e", alpha=0.15, linewidth=0.7)

    ax1.set_ylabel(f"Amplitude ({units})")
    ax1.set_title(f"{src_file.name} | zoom with toolbar to measure time")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right")

    levels_plot = levels[idx_plot]
    ax2.step(t_ms, levels_plot, where="post", color="#2ca02c", linewidth=0.8)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["LOW", "HIGH"])
    ax2.set_xlabel("Time (ms)")
    ax2.set_ylabel("Digital")
    ax2.grid(True, alpha=0.3)

    click_times: list[float] = []

    def on_click(event):
        if event.inaxes not in (ax1, ax2) or event.xdata is None:
            return
        t_ms_click = float(event.xdata)
        click_times.append(t_ms_click)

        for axis in (ax1, ax2):
            axis.axvline(t_ms_click, color="#9467bd", linestyle=":", linewidth=1.0, alpha=0.9)
        fig.canvas.draw_idle()

        if len(click_times) >= 2:
            t1, t2 = click_times[-2], click_times[-1]
            dt_ms = abs(t2 - t1)
            dt_us = dt_ms * 1000.0
            print(f"Measurement: t1={t1:.6f} ms | t2={t2:.6f} ms | dt={dt_ms:.6f} ms ({dt_us:.3f} us)")

    if show_interactive:
        fig.canvas.mpl_connect("button_press_event", on_click)

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)

    if show_interactive:
        print("Interactive mode enabled: click two points to measure delta time.")
        print("Use toolbar zoom/pan; close window to finish.")
        plt.show()
    else:
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot oscilloscope TXT and export timing tables")
    parser.add_argument("input", type=Path, help="Input oscilloscope TXT file")
    parser.add_argument("--threshold", type=float, default=None, help="Digital threshold (default: auto from 5th/95th percentiles)")
    parser.add_argument("--outdir", type=Path, default=None, help="Output folder (default: same folder as input)")
    parser.add_argument("--show", action="store_true", help="Open interactive window for manual time measurements")
    args = parser.parse_args()

    in_path = args.input
    outdir = args.outdir if args.outdir else in_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    y, sample_period_s, units, n, fs_hz = parse_scope_txt(in_path)
    threshold = choose_threshold(y, args.threshold)
    levels = (y >= threshold).astype(np.uint8)

    edges = find_edges(levels, sample_period_s)
    segments = find_segments(levels, sample_period_s)

    stem = in_path.stem
    edges_csv = outdir / f"{stem}_edges.csv"
    segments_csv = outdir / f"{stem}_segments.csv"
    png_file = outdir / f"{stem}_plot.png"

    write_csv(edges_csv, edges)
    write_csv(segments_csv, segments)
    make_plot(in_path, y, sample_period_s, units, threshold, levels, edges, png_file, args.show)

    duration_s = n * sample_period_s
    print(f"Input: {in_path}")
    print(f"Samples: {n}")
    print(f"Sample period: {sample_period_s * 1e6:.6f} us")
    print(f"Sampling rate: {fs_hz:.3f} Hz")
    print(f"Duration: {duration_s:.6f} s")
    print(f"Threshold: {threshold:.6f} {units}")
    print(f"Edges: {len(edges)} -> {edges_csv}")
    print(f"Segments: {len(segments)} -> {segments_csv}")
    print(f"Plot: {png_file}")


if __name__ == "__main__":
    main()
