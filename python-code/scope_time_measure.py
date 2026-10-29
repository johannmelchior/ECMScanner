#!/usr/bin/env python3
"""Fast oscilloscope TXT viewer with two-click time measurement.

Usage:
  python scope_time_measure.py "capture.txt"
  python scope_time_measure.py "capture.txt" --max-points 80000 --threshold 6.0
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def resolve_input_path(raw_input: Path) -> Path:
    """Resolve capture file path across common workspace locations."""
    if raw_input.exists():
        return raw_input

    # If a relative name is provided from inside python-code, try parent folders.
    candidates = [
        Path.cwd() / raw_input,
        Path.cwd().parent / raw_input,
        Path(__file__).resolve().parent / raw_input,
        Path(__file__).resolve().parent.parent / raw_input,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Input file not found: {raw_input}")


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
        raise ValueError("No numeric samples found in file")

    y = np.asarray(samples, dtype=float)
    n = len(y)

    if clock_s and size and size > 0:
        sample_period_s = clock_s / float(size)
    elif clock_s:
        sample_period_s = clock_s / float(n)
    else:
        sample_period_s = 1.0 / 1_000_000.0

    fs_hz = 1.0 / sample_period_s
    return y, sample_period_s, units, n, fs_hz


def auto_threshold(y: np.ndarray) -> float:
    low = float(np.percentile(y, 5))
    high = float(np.percentile(y, 95))
    return (low + high) / 2.0


def decimate_for_speed(y: np.ndarray, sample_period_s: float, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(y)
    if n <= max_points:
        idx = np.arange(n)
    else:
        step = int(np.ceil(n / max_points))
        idx = np.arange(0, n, step)
    t_ms = idx * sample_period_s * 1e3
    return t_ms, y[idx]


def _slice_window(y_full: np.ndarray, sample_period_s: float, x0_ms: float, x1_ms: float, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (t_ms, y) decimated to max_points for the visible window [x0_ms, x1_ms]."""
    i0 = max(0, int(x0_ms * 1e-3 / sample_period_s))
    i1 = min(len(y_full), int(x1_ms * 1e-3 / sample_period_s) + 2)
    chunk = y_full[i0:i1]
    n_chunk = len(chunk)
    if n_chunk <= max_points:
        idx = np.arange(n_chunk)
    else:
        step = int(np.ceil(n_chunk / max_points))
        idx = np.arange(0, n_chunk, step)
    t_ms = (i0 + idx) * sample_period_s * 1e3
    return t_ms, chunk[idx]


def _slice_window_with_idx(
    y_full: np.ndarray,
    sample_period_s: float,
    x0_ms: float,
    x1_ms: float,
    max_points: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (idx_full, t_ms, y) decimated to max_points for visible window."""
    i0 = max(0, int(x0_ms * 1e-3 / sample_period_s))
    i1 = min(len(y_full), int(x1_ms * 1e-3 / sample_period_s) + 2)
    n_chunk = max(0, i1 - i0)
    if n_chunk <= max_points:
        idx_rel = np.arange(n_chunk)
    else:
        step = int(np.ceil(n_chunk / max_points))
        idx_rel = np.arange(0, n_chunk, step)
    idx_full = i0 + idx_rel
    t_ms = idx_full * sample_period_s * 1e3
    return idx_full, t_ms, y_full[idx_full]


def schmitt_levels(y: np.ndarray, low_thr: float, high_thr: float, init_high: bool = True) -> np.ndarray:
    """Convert analog signal to digital using hysteresis thresholds."""
    out = np.empty(len(y), dtype=np.uint8)
    state = 1 if init_high else 0
    for i, v in enumerate(y):
        if state == 1:
            if v <= low_thr:
                state = 0
        else:
            if v >= high_thr:
                state = 1
        out[i] = state
    return out


def decode_uart_bytes(levels: np.ndarray, sample_period_s: float, baud: float) -> list[dict[str, object]]:
    """Decode UART bytes from digital levels.

        Returns dicts with keys:
            start_ms, end_ms, value, stop_ok, centers_ms
    """
    bit_samples = (1.0 / baud) / sample_period_s
    decoded: list[dict[str, object]] = []

    i = 1
    limit = len(levels) - int(10 * bit_samples) - 2
    while i < limit:
        if levels[i - 1] == 1 and levels[i] == 0:
            # Start bit must still be LOW near its center.
            start_center = int(round(i + 0.5 * bit_samples))
            if start_center >= len(levels) or levels[start_center] != 0:
                i += 1
                continue

            # Keep starts only when line was HIGH for at least ~0.5 bit before falling edge.
            pre_start = int(round(i - 0.5 * bit_samples))
            if pre_start > 0 and np.any(levels[pre_start:i] == 0):
                i += 1
                continue

            byte_value = 0
            valid = True
            centers_idx: list[int] = []
            for bit in range(8):
                sample_pos = int(round(i + (1.5 + bit) * bit_samples))
                if sample_pos >= len(levels):
                    valid = False
                    break
                byte_value |= int(levels[sample_pos]) << bit
                centers_idx.append(sample_pos)

            stop_pos = int(round(i + 9.5 * bit_samples))
            stop_ok = stop_pos < len(levels) and levels[stop_pos] == 1

            if valid:
                start_ms = i * sample_period_s * 1e3
                end_ms = (i + 10 * bit_samples) * sample_period_s * 1e3
                centers_ms = [
                    (i + 0.5 * bit_samples) * sample_period_s * 1e3,
                    *[c * sample_period_s * 1e3 for c in centers_idx],
                    stop_pos * sample_period_s * 1e3,
                ]
                decoded.append(
                    {
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "value": byte_value,
                        "stop_ok": bool(stop_ok),
                        "centers_ms": centers_ms,
                    }
                )
                i = int(i + max(1.0, 9.8 * bit_samples))
                continue

        i += 1

    return decoded


def estimate_baud(
    levels: np.ndarray,
    sample_period_s: float,
    min_baud: int,
    max_baud: int,
) -> tuple[float, list[tuple[float, float, int, int, float]]]:
        """Estimate UART baud by maximizing robust decode quality.

        Returns (best_baud, top5_rows) where each row is:
            (score, baud, total, ok, ratio)
        """
        rows: list[tuple[float, float, int, int, float]] = []
        min_baud = max(1000, int(min_baud))
        max_baud = max(min_baud + 25, int(max_baud))

        # Use a representative prefix to keep search responsive.
        n_eval = min(len(levels), 320_000)
        eval_levels = levels[:n_eval]

        def score_one(baud: int) -> tuple[float, float, int, int, float]:
            dec = decode_uart_bytes(eval_levels, sample_period_s, float(baud))
            total = len(dec)
            ok = sum(1 for d in dec if bool(d["stop_ok"]))
            ratio = (ok / total) if total else 0.0
            score = ratio * np.log10(total + 10)
            return (score, float(baud), total, ok, ratio)

        # Coarse sweep first, then refine around top candidates.
        coarse_step = 200
        coarse = [score_one(b) for b in range(min_baud, max_baud + 1, coarse_step)]
        coarse.sort(reverse=True, key=lambda r: r[0])
        seeds = [int(r[1]) for r in coarse[:3]]

        fine_set: set[int] = set()
        for s in seeds:
            for b in range(max(min_baud, s - 350), min(max_baud, s + 350) + 1, 25):
                fine_set.add(b)

        for b in sorted(fine_set):
            rows.append(score_one(b))

        rows.sort(reverse=True, key=lambda r: r[0])
        best_baud = rows[0][1] if rows else 15625.0
        return best_baud, rows[:5]


def run_viewer(
    in_file: Path,
    max_points: int,
    threshold: float | None,
    baud: float,
    auto_baud: bool,
    auto_baud_min: int,
    auto_baud_max: int,
    show_bytes: bool,
    show_bits: bool,
) -> None:
    y_full, sample_period_s, units, n, fs_hz = parse_scope_txt(in_file)
    thr = float(threshold) if threshold is not None else auto_threshold(y_full)

    low_q = float(np.percentile(y_full, 5))
    high_q = float(np.percentile(y_full, 95))
    hyst = 0.15 * (high_q - low_q)
    low_thr = thr - 0.5 * hyst
    high_thr = thr + 0.5 * hyst

    t_ms_full = np.arange(n) * sample_period_s * 1e3
    x_full_min = float(t_ms_full[0])
    x_full_max = float(t_ms_full[-1])

    t_ms, y = decimate_for_speed(y_full, sample_period_s, max_points)
    _lvl_full = schmitt_levels(y_full, low_thr, high_thr, init_high=True)
    digital = _lvl_full[np.clip((t_ms / (sample_period_s * 1e3)).astype(int), 0, len(_lvl_full) - 1)]

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    (line_sig,) = ax1.plot(t_ms, y, color="#1f77b4", linewidth=0.8)
    ax1.axhline(thr, color="#d62728", linestyle="--", linewidth=1.0)
    ax1.set_ylabel(f"Amplitude ({units})")
    ax1.grid(True, alpha=0.3)

    (line_dig,) = ax2.plot([], [], color="#2ca02c", linewidth=0.8, drawstyle="steps-post")
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["LOW", "HIGH"])
    ax2.set_ylim(-0.2, 1.2)
    ax2.set_ylabel("Digital")
    ax2.set_xlabel("Time (ms)")
    ax2.grid(True, alpha=0.3)
    line_dig.set_data(t_ms, digital)

    res_text = ax1.text(
        0.99, 0.98, "", transform=ax1.transAxes, va="top", ha="right",
        fontsize=9, color="#aaaaaa",
    )

    fig.suptitle(
        f"{in_file.name} | samples={n} | Fs={fs_hz:.1f} Hz | Ts={sample_period_s*1e6:.3f} us"
    )

    def refresh_data(x0_ms: float, x1_ms: float) -> None:
        idx_w, t_w, y_w = _slice_window_with_idx(y_full, sample_period_s, x0_ms, x1_ms, max_points)
        d_w = _lvl_full[idx_w]
        line_sig.set_data(t_w, y_w)
        line_dig.set_data(t_w, d_w)
        draw_bytes_overlay(x0_ms, x1_ms)
        shown = len(t_w)
        window_us = (x1_ms - x0_ms) * 1000.0
        res_us = window_us / shown if shown > 1 else sample_period_s * 1e6
        res_text.set_text(f"shown={shown} | res={res_us:.3f} us/pt")

    measure_text = ax1.text(
        0.01,
        0.98,
        "Click two points to measure dt. Keys: r=reset, q=quit",
        transform=ax1.transAxes,
        va="top",
        fontsize=10,
        bbox={"facecolor": "black", "alpha": 0.35, "pad": 6},
        color="white",
    )

    clicks: list[float] = []
    lines = []
    y1_min = float(np.min(y_full))
    y1_max = float(np.max(y_full))
    pan_state = {
        "active": False,
        "press_x": None,
        "xlim": None,
    }

    def redraw_markers() -> None:
        for ln in lines:
            ln.remove()
        lines.clear()
        for x in clicks:
            lines.append(ax1.axvline(x, color="#9467bd", linestyle=":", linewidth=1.2))
            lines.append(ax2.axvline(x, color="#9467bd", linestyle=":", linewidth=1.2))
        fig.canvas.draw_idle()

    # Pre-compute all edge positions in ms for snap-to-edge
    _edge_t_ms = np.where(_lvl_full[1:] != _lvl_full[:-1])[0] * sample_period_s * 1e3

    if auto_baud:
        best_baud, top = estimate_baud(_lvl_full, sample_period_s, auto_baud_min, auto_baud_max)
        baud = float(best_baud)
        print(f"[auto-baud] Search range: {auto_baud_min}..{auto_baud_max}")
        print("[auto-baud] Top candidates:")
        for score, b, total, ok, ratio in top:
            print(f"  baud={int(b):5d} total={total:5d} ok={ok:5d} ratio={ratio:.3f} score={score:.4f}")
        print(f"[auto-baud] Selected baud={baud:g}")
    current_baud = float(baud)
    byte_artists = []
    bit_artists = []

    byte_info_text = ax1.text(
        0.01,
        0.90,
        "",
        transform=ax1.transAxes,
        va="top",
        fontsize=9,
        bbox={"facecolor": "black", "alpha": 0.25, "pad": 5},
        color="#f3d26c",
    )

    def clear_byte_artists() -> None:
        for art in byte_artists:
            art.remove()
        byte_artists.clear()

    def clear_bit_artists() -> None:
        for art in bit_artists:
            art.remove()
        bit_artists.clear()

    def draw_bytes_overlay(x0_ms: float, x1_ms: float) -> None:
        nonlocal current_baud
        clear_byte_artists()
        clear_bit_artists()
        if not show_bytes:
            byte_info_text.set_text("")
            return

        pad_ms = 1.5
        i0 = max(0, int((x0_ms - pad_ms) * 1e-3 / sample_period_s))
        i1 = min(len(_lvl_full), int((x1_ms + pad_ms) * 1e-3 / sample_period_s) + 2)
        if i1 <= i0 + 20:
            byte_info_text.set_text("")
            return

        local_levels = _lvl_full[i0:i1]
        local_offset_ms = i0 * sample_period_s * 1e3
        decode_baud = current_baud

        # Refine baud for current viewport when auto-baud is enabled.
        if auto_baud:
            w_ms = x1_ms - x0_ms
            if w_ms <= 120.0:
                bmin = max(auto_baud_min, int(current_baud - 2500))
                bmax = min(auto_baud_max, int(current_baud + 2500))
                if bmax <= bmin:
                    bmin, bmax = auto_baud_min, auto_baud_max
                local_best, _ = estimate_baud(local_levels, sample_period_s, bmin, bmax)
                decode_baud = float(local_best)
                current_baud = decode_baud

        visible_local = decode_uart_bytes(local_levels, sample_period_s, decode_baud)
        if len(visible_local) == 0:
            byte_info_text.set_text(f"baud={decode_baud:g} | bytes visiveis=0 | schmitt={low_thr:.2f}/{high_thr:.2f}V")
            return

        ok_count = sum(1 for d in visible_local if bool(d["stop_ok"]))
        ratio = ok_count / max(1, len(visible_local))
        # If UART confidence is low in this viewport, avoid drawing misleading overlays.
        if len(visible_local) < 3 or ratio < 0.75:
            byte_info_text.set_text(
                f"baud={decode_baud:g} | baixa confianca UART (n={len(visible_local)}, ok={ok_count}, ratio={ratio:.2f}) | schmitt={low_thr:.2f}/{high_thr:.2f}V"
            )
            return

        max_labels = 40
        y_text = y1_max - 0.08 * (y1_max - y1_min)
        shown = 0
        shown_bits = 0
        for dec in visible_local:
            start_ms = local_offset_ms + float(dec["start_ms"])
            end_ms = local_offset_ms + float(dec["end_ms"])
            value = int(dec["value"])
            stop_ok = bool(dec["stop_ok"])
            centers_ms = [local_offset_ms + float(v) for v in dec["centers_ms"]]
            if end_ms < x0_ms or start_ms > x1_ms:
                continue
            if shown >= max_labels:
                break

            color = "#ffbb66" if stop_ok else "#ff6666"
            alpha = 0.12 if stop_ok else 0.20
            byte_artists.append(ax1.axvspan(start_ms, end_ms, color=color, alpha=alpha, linewidth=0.0))
            byte_artists.append(ax1.axvline(start_ms, color="#66ff66", linestyle="--", linewidth=0.8, alpha=0.6))
            byte_artists.append(ax1.axvline(end_ms, color="#ff9966", linestyle="--", linewidth=0.8, alpha=0.6))
            byte_artists.append(
                ax1.text(
                    start_ms,
                    y_text,
                    f"0x{value:02X}",
                    fontsize=8,
                    color="#ffd27a",
                    va="top",
                    ha="left",
                    bbox={"facecolor": "black", "alpha": 0.25, "pad": 1},
                )
            )

            if show_bits and stop_ok and shown < 14:
                centers = centers_ms
                labels = ["S"] + [f"b{i}" for i in range(8)] + ["P"]
                y_bit = y1_max - 0.18 * (y1_max - y1_min)
                for c_ms, lbl in zip(centers, labels):
                    if c_ms < x0_ms or c_ms > x1_ms:
                        continue
                    bit_artists.append(ax1.axvline(c_ms, color="#6cc0ff", linestyle=":", linewidth=0.7, alpha=0.55))
                    bit_artists.append(
                        ax1.text(
                            c_ms,
                            y_bit,
                            lbl,
                            fontsize=7,
                            color="#8fd4ff",
                            va="top",
                            ha="center",
                        )
                    )
                    shown_bits += 1

            shown += 1

        byte_info_text.set_text(
            f"baud={decode_baud:g} | bytes visiveis={shown} (verde=inicio, laranja=fim) | bits={shown_bits} | ok={ok_count}/{len(visible_local)} | schmitt={low_thr:.2f}/{high_thr:.2f}V"
        )

    def snap_to_edge(x_ms: float, search_ms: float = 5.0) -> float:
        """Return the nearest edge time within search_ms, or original x_ms if none found."""
        lo = np.searchsorted(_edge_t_ms, x_ms - search_ms)
        hi = np.searchsorted(_edge_t_ms, x_ms + search_ms)
        candidates = _edge_t_ms[lo:hi]
        if len(candidates) == 0:
            return x_ms
        return float(candidates[np.argmin(np.abs(candidates - x_ms))])

    def on_click(event) -> None:
        if event.button != 1:
            return
        if event.inaxes not in (ax1, ax2) or event.xdata is None:
            return

        # Snap to nearest digital edge within current visible window / 10
        cur_window_ms = float(ax1.get_xlim()[1] - ax1.get_xlim()[0])
        snapped = snap_to_edge(float(event.xdata), search_ms=cur_window_ms / 8.0)

        # Keep exactly two measurement cursors.
        if len(clicks) < 2:
            clicks.append(snapped)
        else:
            clicks[0] = clicks[1]
            clicks[1] = snapped

        redraw_markers()

        if len(clicks) >= 2:
            t1, t2 = clicks[-2], clicks[-1]
            dt_ms = abs(t2 - t1)
            dt_us = dt_ms * 1000.0
            msg = f"t1={t1:.6f} ms | t2={t2:.6f} ms | dt={dt_ms:.6f} ms ({dt_us:.3f} us)  [snap]"
            measure_text.set_text(msg)
        else:
            measure_text.set_text("Click one more point to measure dt")

        fig.canvas.draw_idle()

    def on_key(event) -> None:
        nonlocal show_bytes, show_bits
        if event.key == "r":
            clicks.clear()
            redraw_markers()
            measure_text.set_text("Markers reset. Click two points to measure dt")
            fig.canvas.draw_idle()
        elif event.key == "a":
            ax1.set_xlim(x_full_min, x_full_max)
            ax1.set_ylim(y1_min, y1_max)
            ax2.set_ylim(-0.2, 1.2)
            refresh_data(x_full_min, x_full_max)
            fig.canvas.draw_idle()
        elif event.key == "b":
            show_bytes = not show_bytes
            x0, x1 = ax1.get_xlim()
            refresh_data(float(x0), float(x1))
            fig.canvas.draw_idle()
        elif event.key == "v":
            show_bits = not show_bits
            x0, x1 = ax1.get_xlim()
            refresh_data(float(x0), float(x1))
            fig.canvas.draw_idle()
        elif event.key == "q":
            plt.close(fig)

    def on_button_press(event) -> None:
        if event.button != 3:
            return
        if event.inaxes not in (ax1, ax2) or event.xdata is None:
            return
        pan_state["active"] = True
        pan_state["press_x"] = float(event.xdata)
        pan_state["xlim"] = ax1.get_xlim()

    def on_button_release(event) -> None:
        if event.button == 3:
            pan_state["active"] = False
            pan_state["press_x"] = None
            pan_state["xlim"] = None

    def on_motion(event) -> None:
        if not pan_state["active"]:
            return
        if event.inaxes not in (ax1, ax2) or event.xdata is None:
            return

        press_x = pan_state["press_x"]
        xlim0 = pan_state["xlim"]
        if press_x is None or xlim0 is None:
            return

        dx = press_x - float(event.xdata)
        new_x0 = xlim0[0] + dx
        new_x1 = xlim0[1] + dx
        window = new_x1 - new_x0

        if new_x0 < x_full_min:
            new_x0 = x_full_min
            new_x1 = new_x0 + window
        if new_x1 > x_full_max:
            new_x1 = x_full_max
            new_x0 = new_x1 - window

        if new_x1 > new_x0:
            ax1.set_xlim(new_x0, new_x1)
            refresh_data(new_x0, new_x1)
            fig.canvas.draw_idle()

    def on_scroll(event) -> None:
        if event.inaxes not in (ax1, ax2) or event.xdata is None:
            return

        base_scale = 1.25
        scale = 1.0 / base_scale if event.button == "up" else base_scale

        cur_xlim = ax1.get_xlim()
        xdata = float(event.xdata)
        new_w = (cur_xlim[1] - cur_xlim[0]) * scale

        left_frac = (xdata - cur_xlim[0]) / (cur_xlim[1] - cur_xlim[0]) if cur_xlim[1] != cur_xlim[0] else 0.5
        new_x0 = xdata - left_frac * new_w
        new_x1 = new_x0 + new_w

        min_window_ms = 0.005
        if (new_x1 - new_x0) < min_window_ms:
            return

        new_x0 = max(x_full_min, new_x0)
        new_x1 = min(x_full_max, new_x1)
        if new_x1 <= new_x0:
            return

        ax1.set_xlim(new_x0, new_x1)
        refresh_data(new_x0, new_x1)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("button_press_event", on_button_press)
    fig.canvas.mpl_connect("button_release_event", on_button_release)
    fig.canvas.mpl_connect("motion_notify_event", on_motion)
    fig.canvas.mpl_connect("key_press_event", on_key)
    fig.canvas.mpl_connect("scroll_event", on_scroll)

    refresh_data(x_full_min, x_full_max)
    measure_text.set_text("Left click: measure | Wheel: zoom X | Right-drag: pan X | r: reset markers | a: reset view | b: bytes on/off | v: bits on/off | q: quit")

    plt.tight_layout()
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast Python oscilloscope viewer with dt measurement")
    parser.add_argument("input", type=Path, help="Oscilloscope TXT file")
    parser.add_argument("--max-points", type=int, default=120_000, help="Max points displayed for speed")
    parser.add_argument("--threshold", type=float, default=None, help="Manual threshold")
    parser.add_argument("--baud", type=float, default=15625.0, help="UART baud used for byte overlay")
    parser.add_argument("--auto-baud", action="store_true", help="Auto-detect baud from capture")
    parser.add_argument("--auto-baud-min", type=int, default=9000, help="Lower limit for auto-baud search")
    parser.add_argument("--auto-baud-max", type=int, default=20000, help="Upper limit for auto-baud search")
    parser.add_argument("--no-bytes", action="store_true", help="Disable byte overlay at startup")
    parser.add_argument("--no-bits", action="store_true", help="Disable bit overlay at startup")
    args = parser.parse_args()

    input_path = resolve_input_path(args.input)

    run_viewer(
        input_path,
        args.max_points,
        args.threshold,
        args.baud,
        args.auto_baud,
        args.auto_baud_min,
        args.auto_baud_max,
        not args.no_bytes,
        not args.no_bits,
    )


if __name__ == "__main__":
    main()
