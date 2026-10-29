import csv

log_path = r'c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\apertar gatilho ibr.csv'

# Lists to store time and values
t_230 = []
v_230 = [] # Byte 5

t_408 = []
v_408 = [] # Byte 5

start_time = None

with open(log_path, 'r') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if len(row) < 4: continue
        
        # Parse Time 09:51:51.955470
        ts_str = row[0]
        h, m, s = ts_str.split(':')
        seconds = float(h)*3600 + float(m)*60 + float(s)
        
        if start_time is None: start_time = seconds
        rel_time = seconds - start_time
        
        cid = int(row[1], 16)
        payload = [int(x, 16) for x in row[3].split()]
        
        if cid == 0x230:
            if len(payload) > 5:
                t_230.append(rel_time)
                v_230.append(payload[5])
                
        if cid == 0x408:
            if len(payload) > 5:
                t_408.append(rel_time)
                v_408.append(payload[5])

# Detect "Press" pattern (Low -> High -> Low) or similar
def analyze_sequence(seq, name):
    if not seq: return
    low = min(seq)
    high = max(seq)
    print(f"\nAnalysis {name}: Min={low} (0x{low:X}), Max={high} (0x{high:X})")
    
    # Simple ASCII Plot
    if high > low:
        scale = 20.0 / (high - low)
    else:
        scale = 0
        
    print("ASCII Plot (Subsample every 5th):")
    for i, val in enumerate(seq):
        if i % 5 == 0:
            stars = int((val - low) * scale)
            print(f"{i:4d} {val:3d} |" + "*" * stars)
            if i > 300: break # Limiter

analyze_sequence(v_230, "0x230 Byte 5")
analyze_sequence(v_408, "0x408 Byte 5")
