import json
from collections import Counter
from pathlib import Path


CAPTURE_DIR = Path(r"z:\projetoCAN\python-code\captures\kline")
OUTPUT_HTML = CAPTURE_DIR / "kline_stage_visualization.html"
TARGET_LABELS = [
    "etapa1_jet_desligado",
    "etapa2_motor_funcionando",
    "etapa3_pos_desligamento",
]


def latest_summary_for(label: str) -> Path:
    matches = sorted(CAPTURE_DIR.glob(f"*_{label}_summary.json"))
    if not matches:
        raise FileNotFoundError(f"Resumo nao encontrado para {label}")
    return matches[-1]


def load_stage(label: str) -> dict:
    summary_path = latest_summary_for(label)
    frames_path = Path(str(summary_path).replace("_summary.json", "_frames.jsonl"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    frames = []
    with frames_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("len") == 28:
                values = [int(part, 16) for part in row["hex"].split()]
                frames.append(values)

    if not frames:
        raise RuntimeError(f"Nenhum frame de 28 bytes em {frames_path}")

    per_position = []
    for pos in range(28):
        counter = Counter(frame[pos] for frame in frames)
        dominant, dominant_count = counter.most_common(1)[0]
        avg = sum(frame[pos] for frame in frames) / len(frames)
        per_position.append(
            {
                "pos": pos,
                "avg": round(avg, 2),
                "dominant": dominant,
                "dominant_pct": round(dominant_count * 100.0 / len(frames), 1),
                "unique": len(counter),
            }
        )

    return {
        "label": label,
        "summary": summary,
        "summary_path": str(summary_path),
        "frames_path": str(frames_path),
        "frames": frames,
        "frame_count": len(frames),
        "per_position": per_position,
        "sample_frames": frames[:48],
        "sample_frames_inverted": [[value ^ 0xFF for value in frame] for frame in frames[:48]],
    }


def compute_change_scores(stages: list[dict]) -> list[dict]:
    scores = []
    for pos in range(28):
        dists = []
        union = set()
        counters = []
        for stage in stages:
            counter = Counter(frame[pos] for frame in stage["frames"])
            counters.append(counter)
            union.update(counter)
        for counter, stage in zip(counters, stages):
            total = len(stage["frames"])
            dists.append({key: counter[key] / total for key in union})
        score = 0.0
        for left in range(len(dists)):
            for right in range(left + 1, len(dists)):
                score += sum(abs(dists[left][key] - dists[right][key]) for key in union)
        scores.append({"pos": pos, "score": round(score, 3)})
    return scores


def render_html(stages: list[dict], change_scores: list[dict]) -> str:
    payload = json.dumps({"stages": stages, "changeScores": change_scores}, ensure_ascii=True)
    return f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\">
  <title>K-Line Stage Visualization</title>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <style>
    :root {{
      --bg: #f3efe7;
      --panel: #fffaf2;
      --ink: #1f1f1f;
      --muted: #6f6a61;
      --grid: #d9d0c3;
      --accent: #8b3a2e;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Georgia, 'Times New Roman', serif; background: linear-gradient(180deg, #efe4d3 0%, var(--bg) 100%); color: var(--ink); }}
    .wrap {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    h1, h2, h3 {{ margin: 0 0 12px; font-weight: 600; }}
    p {{ margin: 0 0 12px; color: var(--muted); }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin: 18px 0 28px; }}
    .card, .panel {{ background: rgba(255,250,242,0.88); backdrop-filter: blur(8px); border: 1px solid rgba(139,58,46,0.14); border-radius: 18px; padding: 16px; box-shadow: 0 10px 30px rgba(66, 37, 20, 0.08); }}
    .card strong {{ display: block; font-size: 1.05rem; color: var(--accent); margin-bottom: 8px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; font-size: 0.94rem; }}
    .metric-label {{ color: var(--muted); }}
    .metric-value {{ font-weight: 700; }}
    .panel {{ margin-bottom: 18px; overflow: hidden; }}
    .table-wrap {{ overflow-x: auto; padding-bottom: 6px; }}
    table {{ border-collapse: collapse; min-width: 980px; width: 100%; }}
    th, td {{ border: 1px solid var(--grid); padding: 6px 8px; text-align: center; font-size: 12px; }}
    th.sticky, td.sticky {{ position: sticky; left: 0; background: #fff8ef; z-index: 2; text-align: left; }}
    th.sticky {{ z-index: 3; }}
    .legend {{ display: flex; gap: 10px; align-items: center; margin: 10px 0 14px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }}
    .swatch {{ width: 160px; height: 12px; border-radius: 999px; background: linear-gradient(90deg, rgb(18, 46, 92), rgb(33, 119, 181), rgb(245, 202, 89), rgb(157, 32, 38)); border: 1px solid rgba(0,0,0,0.12); }}
    .heat-grid {{ display: grid; gap: 2px; background: var(--grid); padding: 2px; border-radius: 12px; overflow-x: auto; }}
    .frame-strip {{ margin-bottom: 20px; }}
    .frame-title {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 8px; }}
    .frame-title small {{ color: var(--muted); }}
    .row {{ display: contents; }}
    .cell {{ width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font: 10px/1 Consolas, monospace; color: rgba(255,255,255,0.9); }}
    .row-label {{ width: 68px; height: 20px; padding: 0 6px; display: inline-flex; align-items: center; justify-content: flex-end; background: #fff8ef; color: var(--muted); font: 11px/1 Consolas, monospace; position: sticky; left: 0; z-index: 1; }}
    .header-cell {{ background: #fff2dd; color: var(--accent); font-weight: 700; }}
    .section-note {{ margin-bottom: 10px; }}
    .paths {{ font: 12px/1.4 Consolas, monospace; color: var(--muted); word-break: break-all; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Visualizacao das Leituras K-Line</h1>
    <p>Mapa visual das 3 etapas. Cada coluna e uma posicao do frame de 28 bytes. Cores mais quentes indicam byte mais alto; cores frias, byte mais baixo.</p>
    <div id=\"cards\" class=\"cards\"></div>

    <div class=\"panel\">
      <h2>Posicoes Que Mais Mudam</h2>
      <p class=\"section-note\">A linha abaixo resume onde o frame mais se altera entre etapas. Quanto maior o score, maior a mudanca de distribuicao naquela posicao.</p>
      <div class=\"table-wrap\" id=\"changeTable\"></div>
    </div>

    <div class=\"panel\">
      <h2>Media Por Posicao</h2>
      <p class=\"section-note\">Boa para ver tendencia geral por byte ao longo do frame.</p>
      <div class=\"legend\"><span>Byte baixo</span><div class=\"swatch\"></div><span>Byte alto</span></div>
      <div class=\"table-wrap\" id=\"avgTable\"></div>
    </div>

    <div class=\"panel\">
      <h2>Byte Dominante Por Posicao</h2>
      <p class=\"section-note\">Mostra o byte mais frequente em cada coluna do frame e a confianca dessa dominancia.</p>
      <div class=\"table-wrap\" id=\"domTable\"></div>
    </div>

    <div class=\"panel\">
      <h2>Heatmap Dos Frames</h2>
      <p class=\"section-note\">Primeiros 48 frames de cada etapa. O numero na margem esquerda e o indice do frame dentro da amostra.</p>
      <div class=\"legend\"><span>Original</span><div class=\"swatch\"></div><span>Invertido (byte ^ FF)</span></div>
      <div id=\"framePanels\"></div>
    </div>
  </div>

  <script>
    const data = {payload};

    function colorForByte(value) {{
      const hue = 220 - (value / 255) * 220;
      const lightness = 28 + (value / 255) * 28;
      return `hsl(${{hue}}, 72%, ${{lightness}}%)`;
    }}

    function textForByte(value) {{
      return value.toString(16).toUpperCase().padStart(2, '0');
    }}

    function buildCards() {{
      const host = document.getElementById('cards');
      data.stages.forEach(stage => {{
        const card = document.createElement('div');
        card.className = 'card';
        const metrics = `
          <strong>${{stage.label}}</strong>
          <div class=\"metrics\">
            <div class=\"metric-label\">frames</div><div class=\"metric-value\">${{stage.summary.frames}}</div>
            <div class=\"metric-label\">bytes</div><div class=\"metric-value\">${{stage.summary.bytes}}</div>
            <div class=\"metric-label\">bytes/s</div><div class=\"metric-value\">${{stage.summary.bytes_per_second}}</div>
            <div class=\"metric-label\">formas unicas</div><div class=\"metric-value\">${{stage.summary.unique_frame_shapes}}</div>
          </div>
          <p class=\"paths\">${{stage.summary_path}}<br>${{stage.frames_path}}</p>
        `;
        card.innerHTML = metrics;
        host.appendChild(card);
      }});
    }}

    function buildTable(containerId, valueGetter, labelGetter) {{
      const host = document.getElementById(containerId);
      const table = document.createElement('table');
      const thead = document.createElement('thead');
      const headRow = document.createElement('tr');
      const first = document.createElement('th');
      first.className = 'sticky';
      first.textContent = 'etapa';
      headRow.appendChild(first);
      for (let pos = 0; pos < 28; pos++) {{
        const th = document.createElement('th');
        th.textContent = pos;
        headRow.appendChild(th);
      }}
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      data.stages.forEach(stage => {{
        const tr = document.createElement('tr');
        const label = document.createElement('td');
        label.className = 'sticky';
        label.textContent = labelGetter(stage);
        tr.appendChild(label);
        stage.per_position.forEach(item => {{
          const td = document.createElement('td');
          const value = valueGetter(item);
          td.textContent = typeof value === 'number' ? (Number.isInteger(value) ? textForByte(value) : value.toFixed(1)) : value;
          td.style.background = colorForByte(Math.max(0, Math.min(255, Math.round(item.avg))));
          td.title = `pos=${{item.pos}} avg=${{item.avg}} dominant=${{textForByte(item.dominant)}} (${{item.dominant_pct}}%) unique=${{item.unique}}`;
          tr.appendChild(td);
        }});
        tbody.appendChild(tr);
      }});
      table.appendChild(tbody);
      host.appendChild(table);
    }}

    function buildChangeTable() {{
      const host = document.getElementById('changeTable');
      const table = document.createElement('table');
      const thead = document.createElement('thead');
      const trh = document.createElement('tr');
      ['pos', 'score', 'desligado', 'motor', 'pos_desligamento'].forEach(name => {{
        const th = document.createElement('th');
        th.textContent = name;
        trh.appendChild(th);
      }});
      thead.appendChild(trh);
      table.appendChild(thead);
      const tbody = document.createElement('tbody');
      data.changeScores.slice().sort((a, b) => b.score - a.score).forEach(row => {{
        const tr = document.createElement('tr');
        const details = new Map();
        data.stages.forEach(stage => {{
          details.set(stage.label, stage.per_position[row.pos]);
        }});
        const cells = [
          row.pos,
          row.score.toFixed(3),
          `${{textForByte(details.get('etapa1_jet_desligado').dominant)}} (${{details.get('etapa1_jet_desligado').dominant_pct}}%)`,
          `${{textForByte(details.get('etapa2_motor_funcionando').dominant)}} (${{details.get('etapa2_motor_funcionando').dominant_pct}}%)`,
          `${{textForByte(details.get('etapa3_pos_desligamento').dominant)}} (${{details.get('etapa3_pos_desligamento').dominant_pct}}%)`,
        ];
        cells.forEach(value => {{
          const td = document.createElement('td');
          td.textContent = value;
          tr.appendChild(td);
        }});
        tbody.appendChild(tr);
      }});
      table.appendChild(tbody);
      host.appendChild(table);
    }}

    function buildFramePanels() {{
      const host = document.getElementById('framePanels');
      data.stages.forEach(stage => {{
        const panel = document.createElement('div');
        panel.className = 'frame-strip';
        const title = document.createElement('div');
        title.className = 'frame-title';
        title.innerHTML = `<h3>${{stage.label}}</h3><small>${{stage.sample_frames.length}} frames originais + invertidos</small>`;
        panel.appendChild(title);

        const original = renderFrameGrid(stage.sample_frames, 'Original');
        const inverted = renderFrameGrid(stage.sample_frames_inverted, 'Invertido');
        panel.appendChild(original);
        panel.appendChild(inverted);
        host.appendChild(panel);
      }});
    }}

    function renderFrameGrid(frames, label) {{
      const wrapper = document.createElement('div');
      wrapper.style.marginBottom = '12px';
      const subtitle = document.createElement('div');
      subtitle.style.fontSize = '12px';
      subtitle.style.color = 'var(--muted)';
      subtitle.style.margin = '0 0 6px';
      subtitle.textContent = label;
      wrapper.appendChild(subtitle);

      const grid = document.createElement('div');
      grid.className = 'heat-grid';
      grid.style.gridTemplateColumns = '68px repeat(28, 20px)';

      const corner = document.createElement('div');
      corner.className = 'row-label header-cell';
      corner.textContent = '#';
      grid.appendChild(corner);
      for (let pos = 0; pos < 28; pos++) {{
        const head = document.createElement('div');
        head.className = 'cell header-cell';
        head.textContent = pos;
        grid.appendChild(head);
      }}

      frames.forEach((frame, index) => {{
        const rowLabel = document.createElement('div');
        rowLabel.className = 'row-label';
        rowLabel.textContent = index;
        grid.appendChild(rowLabel);
        frame.forEach((value, pos) => {{
          const cell = document.createElement('div');
          cell.className = 'cell';
          cell.style.background = colorForByte(value);
          cell.textContent = textForByte(value);
          cell.title = `frame=${{index}} pos=${{pos}} byte=${{textForByte(value)}}`;
          grid.appendChild(cell);
        }});
      }});

      wrapper.appendChild(grid);
      return wrapper;
    }}

    buildCards();
    buildChangeTable();
    buildTable('avgTable', item => item.avg, stage => stage.label);
    buildTable('domTable', item => item.dominant, stage => stage.label);
    buildFramePanels();
  </script>
</body>
</html>
"""


def main() -> int:
    stages = [load_stage(label) for label in TARGET_LABELS]
    change_scores = compute_change_scores(stages)
    OUTPUT_HTML.write_text(render_html(stages, change_scores), encoding="utf-8")
    print(f"html_file={OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())