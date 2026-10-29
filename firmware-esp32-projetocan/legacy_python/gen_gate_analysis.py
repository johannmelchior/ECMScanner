import csv
import json

log_path = r'logs/funcionamento completo.csv'
html_path = r'docs/full_analysis_gate_candidates.html'

# Candidates to plot:
# Trigger: 0x230 B5
# Target: 0x408 B5
# Candidate 1: 0x300 B1 (Range 37-251) - Large range, typically position?
# Candidate 2: 0x300 B5 (Range 30-100)
# Candidate 3: 0x110 B3 (Range 17-88) - Speed or something?
# Candidate 4: 0x12 B4 (0-181)

data_trig = []
data_target = []
data_c1 = [] # 300 B1
data_c2 = [] # 300 B5
data_c3 = [] # 408 B5
data_c4 = [] # 408 B0 ? Just full 408
data_c5 = [] # 516 (204) B0/B1
data_rpm = []
data_tps = []

start_time = None

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
        
        if cid == 0x230:
            data_trig.append({'x': t, 'y': d[5]})
        elif cid == 0x408:
            data_target.append({'x': t, 'y': d[5]})
        elif cid == 0x300:
            if len(d) > 1: data_c1.append({'x': t, 'y': d[1]})
            if len(d) > 5: data_c2.append({'x': t, 'y': d[5]})
        elif cid == 0x516: # 0x204
             if len(d) > 1: data_c5.append({'x': t, 'y': d[1]})
        elif cid == 0x102 and len(d) >= 3:
            rpm = (d[0] << 8) | d[1]
            tps = d[2]
            data_rpm.append({'x': t, 'y': rpm})
            data_tps.append({'x': t, 'y': tps})

# Generate HTML
html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>BRP Gate Position Analysis</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>body {{ background: #222; color: #ddd; }} .chart {{ height: 60vh; width: 90vw; margin: auto; }}</style>
</head>
<body>
    <h2>Gate Position Candidate Search</h2>
    <div class="chart"><canvas id="c"></canvas></div>
    <script>
        new Chart(document.getElementById('c'), {{
            type: 'line',
            data: {{
                datasets: [
                    {{ label: 'RPM', data: {json.dumps(data_rpm)}, borderColor: 'white', borderWidth: 1, pointRadius: 0, yAxisID: 'y_rpm' }},
                    {{ label: 'TPS', data: {json.dumps(data_tps)}, borderColor: 'gray', borderWidth: 1, pointRadius: 0, yAxisID: 'y' }},
                    {{ label: 'Trigger (0x230 B5)', data: {json.dumps(data_trig)}, borderColor: 'magenta', borderWidth: 2, pointRadius: 0, yAxisID: 'y' }},
                    {{ label: 'Target (0x408 B5)', data: {json.dumps(data_target)}, borderColor: 'lime', borderWidth: 2, pointRadius: 0, yAxisID: 'y' }},
                    {{ label: 'Cand 0x300 B1', data: {json.dumps(data_c1)}, borderColor: 'yellow', borderWidth: 1, pointRadius: 0, yAxisID: 'y' }},
                    {{ label: 'Cand 0x300 B5', data: {json.dumps(data_c2)}, borderColor: 'orange', borderWidth: 1, pointRadius: 0, yAxisID: 'y' }},
                    {{ label: 'Cand 0x204 (516) B1', data: {json.dumps(data_c5)}, borderColor: 'cyan', borderWidth: 1, pointRadius: 0, yAxisID: 'y' }}
                ]
            }},
            options: {{
                responsive: true,
                interaction: {{ mode: 'index', intersect: false }},
                scales: {{
                    x: {{ type: 'linear' }},
                    y: {{ position: 'left', title: {{ display: true, text: 'Byte Value (0-255)' }} }},
                    y_rpm: {{ position: 'right', title: {{ display: true, text: 'RPM' }}, grid: {{ drawOnChartArea: false }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
with open(html_path, 'w') as f:
    f.write(html_content)
print(html_path)
