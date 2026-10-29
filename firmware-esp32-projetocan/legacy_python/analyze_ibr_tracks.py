import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# File path
file_path = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-RXT-X-AS-2011-260hp\funcionamento completo.csv"

print(f"Loading {file_path}...")
try:
    df = pd.read_csv(file_path)
except Exception as e:
    print(f"Error loading: {e}")
    exit()

# Parse Timestamps
# Assumes H:M:S.f
df['dt'] = pd.to_datetime(df['Timestamp'], format='%H:%M:%S.%f', errors='coerce')
# If errors, try without microseconds
mask = df['dt'].isna()
if mask.any():
    df.loc[mask, 'dt'] = pd.to_datetime(df.loc[mask, 'Timestamp'], format='%H:%M:%S', errors='coerce')

df = df.dropna(subset=['dt'])

# Define Target Window
target_time_str = "09:57:00"
target_time = pd.to_datetime(target_time_str, format='%H:%M:%S').replace(year=df['dt'].iloc[0].year, month=df['dt'].iloc[0].month, day=df['dt'].iloc[0].day)

# Window: -2s to +5s
start_time = target_time - timedelta(seconds=2)
end_time = target_time + timedelta(seconds=5)

print(f"Analyzing window: {start_time.strftime('%H:%M:%S')} to {end_time.strftime('%H:%M:%S')}")

window = df[(df['dt'] >= start_time) & (df['dt'] <= end_time)].copy()

if window.empty:
    print("No data found in this time window.")
    exit()

# Parse IDs
window['ID_Int'] = window['ID'].apply(lambda x: int(x, 16) if isinstance(x, str) else int(x))

unique_ids = window['ID_Int'].unique()

print(f"IDs active in window: {[hex(i) for i in unique_ids]}")

def hex_to_bytes(s):
    try:
        return [int(x, 16) for x in s.split()]
    except:
        return []

candidates = []

for mid in unique_ids:
    subset = window[window['ID_Int'] == mid]
    if len(subset) < 5: continue
    
    data_list = subset['Data'].apply(hex_to_bytes).tolist()
    max_len = max(len(d) for d in data_list)
    
    # Store columns for correlation
    byte_cols = {}
    
    for i in range(max_len):
        vals = [d[i] if i < len(d) else 0 for d in data_list]
        byte_cols[i] = vals
        
        min_v = min(vals)
        max_v = max(vals)
        rng = max_v - min_v
        
        # We are looking for large changes (0->255 or 255->0)
        # Threshold: Range > 100
        if rng > 50:
            # Check trend
            start_v = np.mean(vals[:3])
            end_v = np.mean(vals[-3:])
            
            trend = "Stable"
            if end_v > start_v + 50: trend = "Rising"
            elif end_v < start_v - 50: trend = "Falling"
            elif mid > start_v + 50: trend = "Bump High"
            
            # Additional check for full range logic
            print(f"ID {hex(mid)} Byte {i}: Range {min_v}-{max_v} ({trend})")
            candidates.append({'id': mid, 'byte': i, 'type': trend, 'vals': vals})

# Check for Inverse Pairs (Track 1 & Track 2)
print("\n--- Potential Track 1 / Track 2 Pairs ---")
# Look for one Rising and one Falling in same ID or correlated
rising = [c for c in candidates if c['type'] == "Rising" or (c['type'] == "Bump High" and c['vals'][10] > c['vals'][0])]
falling = [c for c in candidates if c['type'] == "Falling" or (c['type'] == "Bump Low" and c['vals'][10] < c['vals'][0])]

for r in rising:
    for f in falling:
        if r['id'] == f['id']:
            # Same ID Inverse
            print(f"MATCH in ID {hex(r['id'])}: Byte {r['byte']} (Rise) vs Byte {f['byte']} (Fall)")
            
            # Check Sum (should be roughly constant ~255 or similar if complementary?)
            # Or just check visual correlation
            arr_r = np.array(r['vals'])
            arr_f = np.array(f['vals'])
            
            # If lengths differ (duplicate timestamps?), truncate
            min_l = min(len(arr_r), len(arr_f))
            arr_r = arr_r[:min_l]
            arr_f = arr_f[:min_l]
            
            corr = np.corrcoef(arr_r, arr_f)[0,1]
            print(f"  Correlation: {corr:.2f} (Expected near -1.0)")
            
            # Check Sum
            sums = arr_r + arr_f
            avg_sum = np.mean(sums)
            std_sum = np.std(sums)
            print(f"  Sum Avg: {avg_sum:.1f} (StdDev: {std_sum:.1f})")

