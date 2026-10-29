import csv
import json

log_path = r'logs/funcionamento completo.csv'
html_path = r'docs/full_run_chart.html'

data_time = []
data_rpm = []
data_tps = []
data_ibr_trig = []
data_gate_req = []

start_time = None

print("Parsing CSV...")
with open(log_path, 'r') as f:
    reader = csv.reader(f)
    next(reader) # header
    for row in reader:
        if len(row) < 4: continue
        
        # Time
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
        
        # 0x102: RPM, TPS
        if cid == 0x102 and len(d) >= 3:
            rpm = (d[0] << 8) | d[1]
            tps = d[2]
            
            # Align lists - simple method: just append point
            # For charts w/ different timestamps, we either normalize or use scatter.
            # Chart.js scatter is good, or line with x/y.
            data_rpm.append({'x': t, 'y': rpm})
            data_tps.append({'x': t, 'y': tps}) # Scale? TPS is 0-255. 
            
        # 0x230: IBR Trigger (Byte 5)
        elif cid == 0x230 and len(d) >= 6:
            val = d[5]
            data_ibr_trig.append({'x': t, 'y': val})
            
        # 0x408: Gate Request (Byte 5)
        elif cid == 0x408 and len(d) >= 6:
            val = d[5]
            data_gate_req.append({'x': t, 'y': val})

print(f"Points: RPM={len(data_rpm)}, IBR={len(data_ibr_trig)}")

# Generate HTML
html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>BRP Sea-Doo Log Analysis</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: sans-serif; background: #1e1e1e; color: #ccc; }}
        .chart-container {{ position: relative; height: 40vh; width: 90vw; margin: 20px auto; }}
    </style>
</head>
<body>
    <h2>Log Analysis: Full Run</h2>
    
    <div class="chart-container">
        <canvas id="rpmChart"></canvas>
    </div>
    
    <div class="chart-container">
        <canvas id="ibrChart"></canvas>
    </div>

    <script>
        const dataRPM = {json.dumps(data_rpm)};
        const dataTPS = {json.dumps(data_tps)};
        const dataIBR = {json.dumps(data_ibr_trig)};
        const dataGate = {json.dumps(data_gate_req)};

        // Chart 1: Engine
        new Chart(document.getElementById('rpmChart'), {{
            type: 'line',
            data: {{
                datasets: [
                    {{
                        label: 'RPM (0x102)',
                        data: dataRPM,
                        borderColor: 'cyan',
                        borderWidth: 1,
                        pointRadius: 0,
                        yAxisID: 'y'
                    }},
                    {{
                        label: 'TPS Raw (0x102)',
                        data: dataTPS,
                        borderColor: 'orange',
                        borderWidth: 1,
                        pointRadius: 0,
                        yAxisID: 'y1'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                interaction: {{ mode: 'index', intersect: false }},
                scales: {{
                    x: {{ type: 'linear', title: {{ display: true, text: 'Time (s)' }} }},
                    y: {{ position: 'left', title: {{ display: true, text: 'RPM' }} }},
                    y1: {{ position: 'right', title: {{ display: true, text: 'TPS (0-255)' }}, grid: {{ drawOnChartArea: false }} }}
                }},
                plugins: {{ title: {{ display: true, text: 'Engine Performance' }} }}
            }}
        }});

        // Chart 2: IBR System
        new Chart(document.getElementById('ibrChart'), {{
            type: 'line',
            data: {{
                datasets: [
                    {{
                        label: 'IBR Trigger (0x230 B5)',
                        data: dataIBR,
                        borderColor: '#ff66ff',
                        borderWidth: 2,
                        pointRadius: 0
                    }},
                    {{
                        label: 'Gate Target (0x408 B5)',
                        data: dataGate,
                        borderColor: '#00cc00',
                        borderWidth: 2,
                        pointRadius: 0
                    }}
                ]
            }},
            options: {{
                responsive: true,
                interaction: {{ mode: 'index', intersect: false }},
                scales: {{
                    x: {{ type: 'linear', title: {{ display: true, text: 'Time (s)' }} }},
                    y: {{ title: {{ display: true, text: 'Raw Value' }} }}
                }},
                plugins: {{ title: {{ display: true, text: 'IBR / Reverse System' }} }}
            }}
        }});
    </script>
</body>
</html>
"""

with open(html_path, 'w') as f:
    f.write(html_content)

print(f"Chart generated at: {html_path}")
