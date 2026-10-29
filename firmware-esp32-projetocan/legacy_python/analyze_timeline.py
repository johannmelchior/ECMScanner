import csv
import matplotlib.pyplot as plt

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

print("ID 0x230 Byte 5:")
print(v_230[:20])
print("...")
print(v_230[-20:])

print("\nID 0x408 Byte 5:")
print(v_408[:20])
print("...")
print(v_408[-20:])
