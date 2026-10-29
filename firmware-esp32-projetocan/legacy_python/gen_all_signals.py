import csv
import json
import collections

log_path = r'logs/funcionamento completo.csv'
html_path = r'docs/all_signals_explorer.html'

# 1. Parse ALL signals
# structure: signals[id][byte] = [{'x': t, 'y': val}, ...]
signals = collections.defaultdict(lambda: collections.defaultdict(list))
rpm_data = []

start_time = None

print("Parsing full log...")
with open(log_path, 'r') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if len(row) < 4: continue
        ts = row[0]
        try:
            h, m, s = ts.split(':')
            seconds = float(h)*3600 + float(m)*60 + float(s)
        except: continue
        if start_time is None: start_time = seconds
        t = round(seconds - start_time, 2)
        
        cid = int(row[1], 16)
        try:
            d = [int(x, 16) for x in row[3].split()]
        except: continue
        
        # Capture RPM for reference
        if cid == 0x102:
             r = (d[0] << 8) | d[1]
             rpm_data.append({'x': t, 'y': r})

        # Capture every byte of every ID
        for i, val in enumerate(d):
            signals[cid][i].append({'x': t, 'y': val})

# 2. Filter constant signals (boring)
print("Filtering signals...")
filtered_signals = []

for cid in signals:
    for b in signals[cid]:
        data = signals[cid][b]
        vals = [p['y'] for p in data]
        if not vals: continue
        
        # Criteria: Must have some variance, but not be pure noise/counter
        uni = len(set(vals))
        rn = max(vals) - min(vals)
        
        # We want signals that move significantly (like a position sensor)
        # OR signals that match the binary states (Neutral -> Fwd -> Rev)
        if uni > 2 and rn > 0:
            label = f"ID {hex(cid)} B{b}"
            filtered_signals.append({
                'label': label,
                'data': data
            })

print(f"Found {len(filtered_signals)} interesting signals.")

# 3. Generate HTML with a selector
datasets_js = json.dumps(filtered_signals)
rpm_js = json.dumps(rpm_data)

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>BRP All Signals Explorer</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background: #222; color: #ddd; font-family: sans-serif; display: flex; flex-direction: column; height: 100vh; margin: 0; }}
        #controls {{ padding: 10px; background: #333; display: flex; flex-wrap: wrap; gap: 10px; overflow-y: auto; max-height: 20vh; }}
        .signal-btn {{ padding: 5px 10px; cursor: pointer; background: #444; border: 1px solid #555; color: #eee; font-size: 12px; }}
        .signal-btn.active {{ background: #00aaff; border-color: #00aaff; color: white; }}
        #chart-wrapper {{ flex: 1; position: relative; width: 100%; }}
    </style>
</head>
<body>
    <div id="controls">
        <button onclick="clearAll()" style="background:red">Clear All</button>
        <!-- Buttons will be injected here -->
    </div>
    <div id="chart-wrapper">
        <canvas id="c"></canvas>
    </div>

    <script>
        const allSignals = {datasets_js};
        const rpmData = {rpm_js};
        
        // Setup Chart
        const ctx = document.getElementById('c').getContext('2d');
        let chart = new Chart(ctx, {{
            type: 'line',
            data: {{
                datasets: [
                    {{
                        label: 'RPM (Ref)',
                        data: rpmData,
                        borderColor: 'white',
                        borderWidth: 2,
                        pointRadius: 0,
                        yAxisID: 'y_rpm',
                        order: 999
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{ mode: 'nearest', intersect: false, axis: 'x' }},
                scales: {{
                    x: {{ type: 'linear', title: {{ display: true, text: 'Time (s)' }} }},
                    y: {{ position: 'left', title: {{ display: true, text: 'Signal Value' }} }},
                    y_rpm: {{ position: 'right', title: {{ display: true, text: 'RPM' }}, grid: {{ drawOnChartArea: false }} }}
                }},
                plugins: {{
                    tooltip: {{ enabled: true }} 
                }}
            }}
        }});
        
        // Generate Buttons
        const controls = document.getElementById('controls');
        
        // Sort signals by label
        allSignals.sort((a,b) => a.label.localeCompare(b.label));
        
        allSignals.forEach((sig, idx) => {{
            const btn = document.createElement('button');
            btn.className = 'signal-btn';
            btn.innerText = sig.label;
            btn.onclick = () => toggleSignal(idx, btn);
            controls.appendChild(btn);
        }});
        
        function toggleSignal(idx, btn) {{
            const sig = allSignals[idx];
            const datasetIndex = chart.data.datasets.findIndex(d => d.label === sig.label);
            
            if (datasetIndex > -1) {{
                // Remove
                chart.data.datasets.splice(datasetIndex, 1);
                btn.classList.remove('active');
            }} else {{
                // Add
                // Pick a random color
                const color = `hsl(${{Math.random() * 360}}, 70%, 50%)`;
                chart.data.datasets.push({{
                    label: sig.label,
                    data: sig.data,
                    borderColor: color,
                    borderWidth: 1,
                    pointRadius: 0,
                    yAxisID: 'y'
                }});
                btn.classList.add('active');
            }}
            chart.update();
        }}
        
        function clearAll() {{
            // Keep only RPM
            chart.data.datasets = chart.data.datasets.filter(d => d.label === 'RPM (Ref)');
            document.querySelectorAll('.signal-btn').forEach(b => b.classList.remove('active'));
            chart.update();
        }}
    </script>
</body>
</html>
"""

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"Explorer generated at: {html_path}")
