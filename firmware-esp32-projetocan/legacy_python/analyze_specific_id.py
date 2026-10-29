import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# File path
file_path = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-RXT-X-AS-2011-260hp\funcionamento completo.csv"

# Load
try:
    df = pd.read_csv(file_path)
except Exception as e:
    exit()

# Parse Time
df['dt'] = pd.to_datetime(df['Timestamp'], format='%H:%M:%S.%f', errors='coerce')
mask = df['dt'].isna()
if mask.any():
    df.loc[mask, 'dt'] = pd.to_datetime(df.loc[mask, 'Timestamp'], format='%H:%M:%S', errors='coerce')
    
df = df.dropna(subset=['dt'])

# Window 09:57:00
target_time = pd.to_datetime("09:57:00", format='%H:%M:%S').replace(year=df['dt'].iloc[0].year, month=df['dt'].iloc[0].month, day=df['dt'].iloc[0].day)
start_time = target_time - timedelta(seconds=2)
end_time = target_time + timedelta(seconds=5)
window = df[(df['dt'] >= start_time) & (df['dt'] <= end_time)].copy()

# Helper
def hex_to_bytes(s):
    try: return [int(x, 16) for x in s.split()]
    except: return []

# Analyze ID 0x0A specifically (and 0x10 if exists)
# Check for '10' string or 'A' string or '0A'
print("--- Checking '10' or '0A' or 'A' ---")

candidates = ['10', '0A', 'A', 'a', '0a']
found_ids = window['ID'].unique()
print(f"IDs found: {found_ids}")

target_id = None
# Heuristic: Find the one that matches user expectation of IBR
for x in found_ids:
    if str(x).lower() == 'a' or str(x) == '10':
        target_id = x
        print(f"Analyzing ID: {target_id}")
        
        subset = window[window['ID'] == target_id]
        data_list = subset['Data'].apply(hex_to_bytes).tolist()
        
        if not data_list: continue
        
        for i in range(8):
            vals = [d[i] if i < len(d) else 0 for d in data_list]
            min_v = min(vals)
            max_v = max(vals)
            start_v = vals[0]
            end_v = vals[-1]
            
            print(f"Byte {i}: {min_v} -> {max_v} (Start: {start_v}, End: {end_v})")
            
            # Print 5 samples
            print(f"    Samples: {vals[::len(vals)//10]}")

