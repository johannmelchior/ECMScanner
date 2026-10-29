import csv
import collections

log_path = r'logs/funcionamento completo.csv'

# We know 0x230 Byte 5 is Trigger.
# We suspect 0x408 Byte 5 is Target.
# Candidate for Position: 0x204, 0x410?

# Let's count changes in all IDs to find active signals.
data_map = collections.defaultdict(list) # ID -> list of (time, payload)

start_time = None

with open(log_path, 'r') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if len(row) < 4: continue
        ts_str = row[0]
        try:
            h, m, s = ts_str.split(':')
            seconds = float(h)*3600 + float(m)*60 + float(s)
        except: continue
        
        if start_time is None: start_time = seconds
        t = seconds - start_time
        
        cid = int(row[1], 16)
        try:
            d = [int(x, 16) for x in row[3].split()]
        except: continue
        
        data_map[cid].append((t, d))

print(f"IDs found: {[hex(k) for k in sorted(data_map.keys())]}")

# Helper to get byte series
def get_byte_series(cid, byte_idx):
    if cid not in data_map: return []
    return [(t, row[byte_idx]) for t, row in data_map[cid] if len(row) > byte_idx]

# Get Trigger (0x230 B5)
trig_series = get_byte_series(0x230, 5)

# Calculate stats for all bytes of all IDs
print("\nAnalyzing potential Gate Position signals (0-255)...")
for cid in sorted(data_map.keys()):
    if cid == 0x102: continue # Engine
    
    # Check max payload len
    max_len = max(len(x[1]) for x in data_map[cid])
    
    for b in range(max_len):
        series = get_byte_series(cid, b)
        if not series: continue
        vals = [x[1] for x in series]
        min_v, max_v = min(vals), max(vals)
        unique = len(set(vals))
        
        # Filter for interesting analog-like signals
        if unique > 10 and (max_v - min_v) > 20: 
            # Check correlation with trigger? 
            # Just print range for visual inspection
            print(f"ID 0x{cid:X} Byte {b}: Range [{min_v}-{max_v}], Unique {unique}")
            
            # Print sample specific to "Reverse" event (Trigger usually happens early?)
            # Let's see if it goes High then Low.
            
            
