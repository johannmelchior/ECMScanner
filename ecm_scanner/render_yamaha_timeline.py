import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


COLORS = {
    "88": "#e4572e",
    "02": "#4ca866",
    "18": "#3a86ff",
    "CD": "#a23b72",
    "9D": "#ffbe0b",
    "D6": "#6a4c93",
}


def parse_timestamp(text):
    return datetime.strptime(text, "%H:%M:%S.%f")


def row_tokens(row):
    return [token.upper() for token in row["Data"].split() if token.strip()]


def extract_pairs(tokens):
    pairs = []
  index = 0
  while index < len(tokens) - 1:
    if tokens[index] != "FC":
      index += 1
      continue

    if index + 3 < len(tokens) and tokens[index + 1] != "FC" and tokens[index + 2] == "FC" and tokens[index + 3] != "FC":
      pairs.append((tokens[index + 1], tokens[index + 3]))
      index += 4
      continue

    if index + 2 < len(tokens) and tokens[index + 1] != "FC" and tokens[index + 2] != "FC":
      pairs.append((tokens[index + 1], tokens[index + 2]))
      index += 3
      continue

    index += 1
    return pairs


def choose_ids(rows, top_n):
    counter = Counter()
    for row in rows:
        for ident, _ in extract_pairs(row_tokens(row)):
            counter[ident] += 1
    preferred = ["88", "02", "18", "CD", "9D", "D6"]
    ordered = []
    for ident in preferred:
        if ident in counter and ident not in ordered:
            ordered.append(ident)
    for ident, _ in counter.most_common(top_n):
        if ident not in ordered:
            ordered.append(ident)
    return ordered[:top_n]


def collect_series(rows, selected_ids):
    base_time = parse_timestamp(rows[0]["Timestamp"])
    series = defaultdict(list)
    for row_number, row in enumerate(rows, start=1):
        timestamp = parse_timestamp(row["Timestamp"])
        seconds = (timestamp - base_time).total_seconds()
        for ident, value_hex in extract_pairs(row_tokens(row)):
            if ident not in selected_ids:
                continue
            series[ident].append(
                {
                    "row": row_number,
                    "t": round(seconds, 6),
                    "value": int(value_hex, 16),
                    "hex": value_hex,
                }
            )
    return series


def build_html(title, series, selected_ids, markers):
    data_lines = []
    for ident in selected_ids:
        points = series.get(ident, [])
        color = COLORS.get(ident, "#888888")
        data_lines.append(
            f'"{ident}": {{"color": "{color}", "points": {points}}}'
        )
    data_blob = "{\n" + ",\n".join(data_lines) + "\n}"

    marker_lines = []
    for label, row_number, color in markers:
        marker_lines.append(
            f'{{"label": "{label}", "row": {row_number}, "color": "{color}"}}'
        )
    marker_blob = "[" + ", ".join(marker_lines) + "]"

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      background: #111315;
      color: #eceff4;
      font: 14px/1.4 Consolas, 'SFMono-Regular', monospace;
    }}
    .wrap {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 20px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 24px;
    }}
    p {{
      margin: 0 0 14px;
      color: #b5bcc8;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      margin: 16px 0 18px;
      padding: 12px 14px;
      border: 1px solid #2a2f35;
      border-radius: 10px;
      background: #171b20;
    }}
    label {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
    }}
    input[type=checkbox] {{
      accent-color: #3a86ff;
    }}
    .chip {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }}
    .chart-box {{
      border: 1px solid #2a2f35;
      border-radius: 12px;
      background: #171b20;
      overflow: hidden;
    }}
    svg {{
      display: block;
      width: 100%;
      height: auto;
      background: linear-gradient(180deg, #171b20 0%, #12161b 100%);
    }}
    .legend {{
      margin-top: 12px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
    }}
    .legend-item {{
      padding: 10px 12px;
      border: 1px solid #2a2f35;
      border-radius: 10px;
      background: #12161b;
    }}
    .legend-item strong {{
      display: inline-block;
      min-width: 34px;
    }}
    .muted {{
      color: #9aa3b2;
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>{title}</h1>
    <p>Grafico do barramento Yamaha K-Line extraido de pares <code>FC ID VALOR</code>. Marcadores: partida na linha 80 e desligamento na linha 160.</p>
    <div id=\"controls\" class=\"controls\"></div>
    <div class=\"chart-box\">
      <svg id=\"chart\" viewBox=\"0 0 1320 720\" preserveAspectRatio=\"xMidYMid meet\"></svg>
    </div>
    <div id=\"legend\" class=\"legend\"></div>
  </div>

  <script>
    const dataset = {data_blob};
    const markers = {marker_blob};

    const svg = document.getElementById('chart');
    const controls = document.getElementById('controls');
    const legend = document.getElementById('legend');
    const width = 1320;
    const height = 720;
    const margin = {{ left: 72, right: 26, top: 26, bottom: 50 }};
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const ids = Object.keys(dataset);
    const enabled = new Set(ids);

    function formatHex(num) {{
      return '0x' + num.toString(16).toUpperCase().padStart(2, '0');
    }}

    function collectAllPoints() {{
      return ids.filter(id => enabled.has(id)).flatMap(id => dataset[id].points.map(p => ({{...p, id}})));
    }}

    function xScale(value, maxTime) {{
      return margin.left + (value / Math.max(maxTime, 0.001)) * innerWidth;
    }}

    function yScale(value, maxValue) {{
      return margin.top + innerHeight - (value / Math.max(maxValue, 1)) * innerHeight;
    }}

    function rowToTime(row) {{
      for (const id of ids) {{
        const found = dataset[id].points.find(point => point.row >= row);
        if (found) return found.t;
      }}
      return null;
    }}

    function polyline(points, color) {{
      const ns = 'http://www.w3.org/2000/svg';
      const el = document.createElementNS(ns, 'polyline');
      el.setAttribute('fill', 'none');
      el.setAttribute('stroke', color);
      el.setAttribute('stroke-width', '2');
      el.setAttribute('stroke-linejoin', 'round');
      el.setAttribute('stroke-linecap', 'round');
      el.setAttribute('points', points.map(p => `${{p.x}},${{p.y}}`).join(' '));
      return el;
    }}

    function line(x1, y1, x2, y2, stroke, dash = '') {{
      const ns = 'http://www.w3.org/2000/svg';
      const el = document.createElementNS(ns, 'line');
      el.setAttribute('x1', x1);
      el.setAttribute('y1', y1);
      el.setAttribute('x2', x2);
      el.setAttribute('y2', y2);
      el.setAttribute('stroke', stroke);
      el.setAttribute('stroke-width', '1');
      if (dash) el.setAttribute('stroke-dasharray', dash);
      return el;
    }}

    function text(x, y, value, color = '#d8dee9', anchor = 'start') {{
      const ns = 'http://www.w3.org/2000/svg';
      const el = document.createElementNS(ns, 'text');
      el.setAttribute('x', x);
      el.setAttribute('y', y);
      el.setAttribute('fill', color);
      el.setAttribute('font-size', '12');
      el.setAttribute('text-anchor', anchor);
      el.textContent = value;
      return el;
    }}

    function renderLegend(activePoints) {{
      legend.innerHTML = '';
      ids.forEach(id => {{
        const points = dataset[id].points;
        const values = points.map(p => p.value);
        const min = values.length ? Math.min(...values) : 0;
        const max = values.length ? Math.max(...values) : 0;
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `
          <div><span class="chip" style="background:${{dataset[id].color}}"></span> <strong>${{id}}</strong></div>
          <div class="muted">points=${{points.length}} range=${{formatHex(min)}}..${{formatHex(max)}}</div>
        `;
        legend.appendChild(item);
      }});
    }}

    function render() {{
      svg.innerHTML = '';
      const allPoints = collectAllPoints();
      if (!allPoints.length) return;

      const maxTime = Math.max(...allPoints.map(p => p.t));
      const maxValue = Math.max(...allPoints.map(p => p.value), 255);

      for (let i = 0; i <= 8; i++) {{
        const value = (maxValue / 8) * i;
        const y = yScale(value, maxValue);
        svg.appendChild(line(margin.left, y, width - margin.right, y, '#27313a', '4 6'));
        svg.appendChild(text(margin.left - 8, y + 4, formatHex(Math.round(value)), '#8f9aaa', 'end'));
      }}

      for (let i = 0; i <= 10; i++) {{
        const value = (maxTime / 10) * i;
        const x = xScale(value, maxTime);
        svg.appendChild(line(x, margin.top, x, height - margin.bottom, '#20272e', '4 6'));
        svg.appendChild(text(x, height - 18, value.toFixed(1) + 's', '#8f9aaa', 'middle'));
      }}

      svg.appendChild(line(margin.left, margin.top, margin.left, height - margin.bottom, '#d8dee9'));
      svg.appendChild(line(margin.left, height - margin.bottom, width - margin.right, height - margin.bottom, '#d8dee9'));

      ids.forEach(id => {{
        if (!enabled.has(id)) return;
        const points = dataset[id].points.map(point => ({{
          x: xScale(point.t, maxTime),
          y: yScale(point.value, maxValue),
        }}));
        if (points.length >= 2) {{
          svg.appendChild(polyline(points, dataset[id].color));
        }}
      }});

      markers.forEach(marker => {{
        const markerTime = rowToTime(marker.row);
        if (markerTime === null) return;
        const x = xScale(markerTime, maxTime);
        svg.appendChild(line(x, margin.top, x, height - margin.bottom, marker.color, '8 6'));
        svg.appendChild(text(x + 6, margin.top + 18, `${{marker.label}} (row ${{marker.row}})`, marker.color));
      }});

      svg.appendChild(text(margin.left, 18, 'valor', '#d8dee9'));
      svg.appendChild(text(width - margin.right, height - 18, 'tempo relativo', '#d8dee9', 'end'));
      renderLegend(allPoints);
    }}

    ids.forEach(id => {{
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = true;
      checkbox.addEventListener('change', () => {{
        if (checkbox.checked) enabled.add(id);
        else enabled.delete(id);
        render();
      }});
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.style.background = dataset[id].color;
      label.appendChild(checkbox);
      label.appendChild(chip);
      label.appendChild(document.createTextNode(`ID ${{id}}`));
      controls.appendChild(label);
    }});

    render();
  </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Render Yamaha FC-id-value timeline to HTML")
    parser.add_argument("csv_path", help="Path to Yamaha CSV log")
    parser.add_argument("output_html", help="Output HTML file")
    parser.add_argument("--top", type=int, default=6, help="How many IDs to plot")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    selected_ids = choose_ids(rows, args.top)
    series = collect_series(rows, selected_ids)
    html = build_html(
        title=f"Yamaha K-Line Timeline - {csv_path.name}",
        series=series,
        selected_ids=selected_ids,
        markers=[("Partida", 80, "#ff6b6b"), ("Desligamento", 160, "#4dd0e1")],
    )
    Path(args.output_html).write_text(html, encoding="utf-8")
    print(f"wrote {args.output_html}")


if __name__ == "__main__":
    main()