import csv
import json
import collections

log_path = r'logs/funcionamento completo.csv'
html_path = r'docs/full_spectrum_analysis.html'

# 1. Parse ALL signals
# structure: signals[id][byte] = [{'x': t, 'y': val}, ...]
signals = collections.defaultdict(lambda: collections.defaultdict(list))
rpm_data = []

start_time = None
found_timestamps = False

print(f"Parsing full log: {log_path} ...")
try:
    with open(log_path, 'r') as f:
        reader = csv.reader(f)
        # Try to find header
        header = next(reader, None)
        
        for row in reader:
            if len(row) < 4: continue
            
            ts = row[0].strip()
            # Parse Time with high precision support
            try:
                # Format: 09:56:26.667517
                if "." in ts:
                    dt_parts = ts.split(":")
                    if len(dt_parts) < 3: continue
                    h = float(dt_parts[0])
                    m = float(dt_parts[1])
                    s = float(dt_parts[2])
                    seconds = h*3600 + m*60 + s
                else:
                    # Fallback
                    h, m, s = map(float, ts.split(':'))
                    seconds = h*3600 + m*60 + s
            except: 
                continue

            if start_time is None: start_time = seconds
            t = round(seconds - start_time, 3)
            
            try:
                cid = int(row[1], 16)
                data_str = row[3].strip()
                # Handle space or no space
                if " " in data_str:
                    d = [int(x, 16) for x in data_str.split()]
                else:
                    # Try comma? Or just one byte?
                    # The log writer uses " ".join/
                    d = [int(x, 16) for x in data_str.split()]
            except: continue
            
            # Capture RPM for reference (Updated Formula / 4)
            if cid == 0x102 and len(d) >= 2:
                 raw_r = (d[0] << 8) | d[1]
                 r = raw_r / 4.0
                 rpm_data.append({'x': t, 'y': r})

            # Capture every byte of every ID
            for i, val in enumerate(d):
                signals[cid][i].append({'x': t, 'y': val})

except FileNotFoundError:
    print(f"Error: File {log_path} not found.")
    exit(1)

# 2. Filter? NO FILTER requested (mostly)
# User said "sem deixar nenhum id de fora". 
# However, showing 0x00 constant forever is truly useless?
# I will include EVERYTHING that is not constant.
# If the user wants constants, they can verify the ID list.
# Actually, let's include constants too but mark them? 
# No, let's stick to "changed at least once" OR "is important".
# The prompt says "without leaving any id out". 
# Maybe I should just reduce the threshold to rn >= 0? 
# If rn == 0 (constant), it's a flat line. I'll include it but maybe limit the points to 2 (start/end) to save JS memory?

print("Processing signals...")
filtered_signals = []

# Sort by ID
sorted_ids = sorted(signals.keys())

for cid in sorted_ids:
    for b in sorted(signals[cid].keys()):
        data = signals[cid][b]
        if not data: continue
        
        vals = [p['y'] for p in data]
        rn = max(vals) - min(vals)
        uni = len(set(vals))
        
        # New Rule: Include everything even if constant?
        # User request is explicit. Let's include everything.
        # But for constant signals, we don't need 10000 points.
        if rn == 0:
            # Optimize: just start and end
            opt_data = [data[0], data[-1]]
            label = f"ID {hex(cid)} B{b} (Const {vals[0]})"
        else:
            opt_data = data # Or decimate if huge?
            label = f"ID {hex(cid)} B{b}"

        # Decimation for high freq signals to prevent browser crash
        if len(opt_data) > 5000:
             # Simple skip
             step = len(opt_data) // 5000
             opt_data = opt_data[::step]

        filtered_signals.append({
            'label': label,
            'id': hex(cid),
            'byte': b,
            'is_const': (rn == 0),
            'unique_vals': uni,
            'data': opt_data
        })

print(f"Index contains {len(filtered_signals)} traces.")

# 3. Generate HTML
datasets_js = json.dumps(filtered_signals)
rpm_js = json.dumps(rpm_data)

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Full Spectrum Analysis - {log_path}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom"></script>
    <style>
        body {{ background: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI', sans-serif; display: flex; flex-direction: column; height: 100vh; margin: 0; overflow: hidden; }}
        header {{ padding: 10px 20px; background: #252526; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }}
        h2 {{ margin: 0; font-size: 18px; color: #007acc; }}
        
        #main-container {{ display: flex; flex: 1; overflow: hidden; }}
        
        #sidebar {{ width: 300px; background: #252526; border-right: 1px solid #333; display: flex; flex-direction: column; }}
        #filter-box {{ padding: 10px; border-bottom: 1px solid #333; }}
        #filter-input {{ width: 100%; padding: 5px; background: #3c3c3c; border: 1px solid #555; color: white; }}
        
        #signal-list {{ flex: 1; overflow-y: auto; padding: 5px; }}
        .signal-item {{ 
            padding: 6px 10px; cursor: pointer; border-bottom: 1px solid #333; font-size: 13px; display: flex; justify-content: space-between;
        }}
        .signal-item:hover {{ background: #2a2d2e; }}
        .signal-item.active {{ background: #094771; color: white; }}
        .const-sig {{ color: #666; font-style: italic; }}
        
        #chart-area {{ flex: 1; position: relative; padding: 10px; background: #1e1e1e; }}
    </style>
</head>
<body>
    <header>
        <h2>CAN Log Analysis - Full Spectrum</h2>
        <div style="font-size: 12px; color: #aaa">Scroll to Zoom | Drag to Pan</div>
    </header>
    
    <div id="main-container">
        <div id="sidebar">
            <div id="filter-box">
                <input type="text" id="filter-input" placeholder="Filter ID (e.g. 0x102)..." onkeyup="filterList()">
                <div style="margin-top: 5px; font-size: 11px;">
                    <label><input type="checkbox" id="hideConst" onchange="filterList()"> Hide Constant</label>
                    <button onclick="clearChart()" style="float: right; font-size: 10px; cursor: pointer;">Clear Chart</button>
                </div>
            </div>
            <div id="signal-list">
                <!-- List Items -->
            </div>
        </div>
        
        <div id="chart-area">
            <canvas id="myChart"></canvas>
        </div>
    </div>

    <script>
        const signals = {datasets_js};
        const rpmData = {rpm_js};
        
        // Init Chart
        const ctx = document.getElementById('myChart').getContext('2d');
        let chart = new Chart(ctx, {{
            type: 'line',
            data: {{
                datasets: [
                    {{
                        label: 'RPM (Reference)',
                        data: rpmData,
                        borderColor: '#444444',
                        borderWidth: 2,
                        pointRadius: 0,
                        borderDash: [5, 5],
                        yAxisID: 'y_rpm',
                        order: 99
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: {{ mode: 'nearest', axis: 'x', intersect: false }},
                scales: {{
                    x: {{ 
                        type: 'linear', 
                        position: 'bottom',
                        title: {{ display: true, text: 'Time (s)' }}
                    }},
                    y: {{
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {{ display: true, text: 'Byte Value' }}
                    }},
                    y_rpm: {{
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: {{ drawOnChartArea: false }},
                        title: {{ display: true, text: 'RPM' }}
                    }}
                }},
                plugins: {{
                    zoom: {{
                        zoom: {{
                            wheel: {{ enabled: true }},
                            pinch: {{ enabled: true }},
                            mode: 'x',
                        }},
                        pan: {{
                            enabled: true,
                            mode: 'x',
                        }}
                    }},
                    legend: {{
                        labels: {{ color: '#ccc' }}
                    }}
                }}
            }}
        }});

        const listEl = document.getElementById('signal-list');

        function renderList(filterText, hideConst) {{
            listEl.innerHTML = '';
            
            signals.forEach((sig, index) => {{
                if (hideConst && sig.is_const) return;
                if (filterText && !sig.label.toLowerCase().includes(filterText.toLowerCase())) return;
                
                const div = document.createElement('div');
                div.className = 'signal-item' + (sig.is_const ? ' const-sig' : '');
                div.innerHTML = `<span>${{sig.label}}</span> <span style="font-size:10px; opacity:0.7">${{sig.unique_vals}} vals</span>`;
                div.onclick = () => toggleSignal(index, div);
                
                // Check if already active
                const isInData = chart.data.datasets.some(d => d._sigIndex === index);
                if (isInData) div.classList.add('active');
                
                listEl.appendChild(div);
            }});
        }}

        function toggleSignal(index, btn) {{
            const sig = signals[index];
            const existingIdx = chart.data.datasets.findIndex(d => d._sigIndex === index);
            
            if (existingIdx !== -1) {{
                // Remove
                chart.data.datasets.splice(existingIdx, 1);
                btn.classList.remove('active');
            }} else {{
                // Add
                // Pick a color based on ID
                const hue = (parseInt(sig.id, 16) * 37) % 360;
                const color = `hsl(${{hue}}, 70%, 60%)`;
                
                chart.data.datasets.push({{
                    label: sig.label,
                    data: sig.data,
                    borderColor: color,
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.1,
                    _sigIndex: index
                }});
                btn.classList.add('active');
            }}
            chart.update();
        }}
        
        function clearChart() {{
            // Keep RPM
            chart.data.datasets = [chart.data.datasets[0]]; 
            renderList(document.getElementById('filter-input').value, document.getElementById('hideConst').checked);
            chart.update();
        }}

        function filterList() {{
            const txt = document.getElementById('filter-input').value;
            const hc = document.getElementById('hideConst').checked;
            renderList(txt, hc);
        }}

        // Initial Render
        renderList('', false);

    </script>
</body>
</html>
"""

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"Done. Open {html_path} in your browser.")
