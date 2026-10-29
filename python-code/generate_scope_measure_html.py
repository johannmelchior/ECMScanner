#!/usr/bin/env python3
"""Generate an interactive HTML oscilloscope viewer with time measurement.

Features:
- Time-domain plot with zoom/pan (Plotly)
- Two-cursor measurement (click two points)
- Auto and manual threshold visualization
- Digital level overlay (LOW/HIGH)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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


def choose_threshold(y: np.ndarray, user_threshold: float | None) -> float:
    if user_threshold is not None:
        return float(user_threshold)
    low = float(np.percentile(y, 5))
    high = float(np.percentile(y, 95))
    return (low + high) / 2.0


def decimate(y: np.ndarray, sample_period_s: float, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(y)
    if n <= max_points:
        idx = np.arange(n)
    else:
        step = int(np.ceil(n / max_points))
        idx = np.arange(0, n, step)

    t_ms = idx * sample_period_s * 1e3
    return t_ms, y[idx]


def build_html(
    src_file: Path,
    t_ms: np.ndarray,
    y: np.ndarray,
    threshold: float,
    units: str,
    sample_period_s: float,
    fs_hz: float,
    total_samples: int,
) -> str:
    levels = (y >= threshold).astype(int)

    t_json = json.dumps(t_ms.tolist(), separators=(",", ":"))
    y_json = json.dumps(y.tolist(), separators=(",", ":"))
    d_json = json.dumps(levels.tolist(), separators=(",", ":"))

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Scope Time Measure - {src_file.name}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{
      margin: 0;
      font-family: Segoe UI, Tahoma, sans-serif;
      background: #0b1020;
      color: #e8ecff;
    }}
    .wrap {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 16px;
    }}
    .card {{
      background: linear-gradient(145deg, #111834, #0e142d);
      border: 1px solid #26325f;
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
    }}
    h1 {{ margin: 0 0 10px 0; font-size: 20px; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; color: #b8c2ea; }}
    .row {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 8px; }}
    button {{
      background: #1f316c;
      border: 1px solid #3b4d8d;
      color: #f0f4ff;
      border-radius: 8px;
      padding: 6px 10px;
      cursor: pointer;
    }}
    button:hover {{ background: #2a3f87; }}
    .measure {{
      font-size: 14px;
      font-weight: 600;
      color: #96ffd0;
      min-height: 22px;
    }}
    #plot {{ height: 72vh; min-height: 480px; }}
    .help {{ font-size: 13px; color: #b8c2ea; line-height: 1.45; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Visualizador com Medicao de Tempo</h1>
      <div class="meta">
        <div>Arquivo: {src_file.name}</div>
        <div>Amostras originais: {total_samples}</div>
        <div>Taxa amostragem: {fs_hz:.3f} Hz</div>
        <div>Periodo amostragem: {sample_period_s * 1e6:.6f} us</div>
        <div>Threshold: {threshold:.6f} {units}</div>
      </div>
      <div class="row">
        <button id="resetCursor">Limpar Cursores</button>
        <button id="toggleDigital">Mostrar/Ocultar Digital</button>
        <div class="measure" id="measureText">Clique em dois pontos do grafico para medir delta de tempo.</div>
      </div>
      <div class="help">
        Dica: use o zoom da barra do Plotly para aproximar pulsos. O delta sera mostrado em ms e us.
      </div>
    </div>
    <div class="card">
      <div id="plot"></div>
    </div>
  </div>

  <script>
    const tMs = {t_json};
    const signal = {y_json};
    const digital = {d_json};
    const threshold = {threshold};
    const units = {json.dumps(units)};

    const plotEl = document.getElementById('plot');
    const measureText = document.getElementById('measureText');
    const cursors = [];
    let showDigital = true;

    const traces = [
      {{
        x: tMs,
        y: signal,
        type: 'scattergl',
        mode: 'lines',
        name: 'Sinal',
        line: {{ color: '#6fb3ff', width: 1 }}
      }},
      {{
        x: [tMs[0], tMs[tMs.length - 1]],
        y: [threshold, threshold],
        type: 'scatter',
        mode: 'lines',
        name: 'Threshold',
        line: {{ color: '#ff7f6f', width: 1.2, dash: 'dash' }}
      }},
      {{
        x: tMs,
        y: digital,
        type: 'scattergl',
        mode: 'lines',
        name: 'Digital',
        line: {{ color: '#6dff9a', width: 1 }},
        yaxis: 'y2',
        visible: true
      }}
    ];

    const layout = {{
      paper_bgcolor: '#111834',
      plot_bgcolor: '#0f1735',
      font: {{ color: '#e8ecff' }},
      margin: {{ l: 70, r: 70, t: 30, b: 60 }},
      hovermode: 'closest',
      dragmode: 'zoom',
      xaxis: {{ title: 'Tempo (ms)', gridcolor: '#2d3b70' }},
      yaxis: {{ title: `Amplitude (${{units}})`, gridcolor: '#2d3b70' }},
      yaxis2: {{
        title: 'Digital',
        overlaying: 'y',
        side: 'right',
        range: [-0.2, 1.2],
        tickvals: [0, 1],
        ticktext: ['LOW', 'HIGH']
      }},
      shapes: []
    }};

    Plotly.newPlot(plotEl, traces, layout, {{ responsive: true }});

    function redrawCursors() {{
      const shapes = cursors.map((x) => ({{
        type: 'line',
        x0: x, x1: x,
        yref: 'paper',
        y0: 0, y1: 1,
        line: {{ color: '#f7d774', width: 1.5, dash: 'dot' }}
      }}));
      Plotly.relayout(plotEl, {{ shapes }});
    }}

    function updateMeasureText() {{
      if (cursors.length < 2) {{
        measureText.textContent = 'Clique em dois pontos do grafico para medir delta de tempo.';
        return;
      }}
      const t1 = cursors[cursors.length - 2];
      const t2 = cursors[cursors.length - 1];
      const dtMs = Math.abs(t2 - t1);
      const dtUs = dtMs * 1000.0;
      measureText.textContent = `t1=${{t1.toFixed(6)}} ms | t2=${{t2.toFixed(6)}} ms | dt=${{dtMs.toFixed(6)}} ms (${{dtUs.toFixed(3)}} us)`;
    }}

    plotEl.on('plotly_click', (ev) => {{
      const x = ev.points && ev.points[0] ? ev.points[0].x : null;
      if (x === null || x === undefined) return;
      cursors.push(Number(x));
      if (cursors.length > 8) cursors.shift();
      redrawCursors();
      updateMeasureText();
    }});

    document.getElementById('resetCursor').addEventListener('click', () => {{
      cursors.length = 0;
      redrawCursors();
      updateMeasureText();
    }});

    document.getElementById('toggleDigital').addEventListener('click', () => {{
      showDigital = !showDigital;
      Plotly.restyle(plotEl, {{ visible: showDigital }}, [2]);
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate interactive HTML oscilloscope viewer with time measurement")
    parser.add_argument("input", type=Path, help="Input oscilloscope TXT file")
    parser.add_argument("--out", type=Path, default=None, help="Output HTML file path")
    parser.add_argument("--threshold", type=float, default=None, help="Manual threshold")
    parser.add_argument("--max-points", type=int, default=180_000, help="Maximum points to embed in HTML")
    args = parser.parse_args()

    in_path = args.input
    out_path = args.out if args.out else in_path.with_name(f"{in_path.stem}_measure.html")

    y_full, sample_period_s, units, n, fs_hz = parse_scope_txt(in_path)
    threshold = choose_threshold(y_full, args.threshold)
    t_ms, y = decimate(y_full, sample_period_s, args.max_points)

    html = build_html(
        src_file=in_path,
        t_ms=t_ms,
        y=y,
        threshold=threshold,
        units=units,
        sample_period_s=sample_period_s,
        fs_hz=fs_hz,
        total_samples=n,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    print(f"Input: {in_path}")
    print(f"Samples (original): {n}")
    print(f"Samples (embedded): {len(y)}")
    print(f"Output HTML: {out_path}")


if __name__ == "__main__":
    main()
