import csv
import collections

log_path = r'c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\apertar gatilho ibr.csv'

# Storage: { ID: { ByteIndex: [values] } }
data_map = collections.defaultdict(lambda: collections.defaultdict(list))

try:
    with open(log_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader) # Skip header
        
        for row in reader:
            if len(row) < 4: continue
            
            can_id_hex = row[1]
            try:
                can_id = int(can_id_hex, 16)
            except:
                continue
                
            data_str = row[3]
            try:
                bytes_val = [int(x, 16) for x in data_str.split()]
            except:
                continue
                
            for i, val in enumerate(bytes_val):
                data_map[can_id][i].append(val)

    print(f"Analyzed {len(data_map)} unique IDs.")
    print("-" * 60)

    # Analyze for changes
    for can_id in sorted(data_map.keys()):
        id_hex = f"{can_id:X}"
        printed_id = False
        
        for i in range(8):
            vals = data_map[can_id][i]
            if not vals: continue
            
            unique_vals = set(vals)
            min_v = min(vals)
            max_v = max(vals)
            
            # Filter criteria:
            # 1. More than 1 unique value (it changes)
            # 2. Ignore likely counters (monotonic increase 0-15 or 0-255 wrapping)? 
            #    Hard to detect purely simply, but let's just see "Range".
            
            if len(unique_vals) > 1:
                if not printed_id:
                    print(f"ID: 0x{id_hex}")
                    printed_id = True
                
                # Check for "analog" behavior - varying across a range
                is_counter = False
                # Simple heuristc for 4-bit counter: 0,1,2,3,4...
                if len(unique_vals) == 16 and max_v == 15: is_counter = True
                
                print(f"  Byte {i}: Range [{min_v:3} - {max_v:3}] | Unique: {len(unique_vals):3} | Samples: {str(vals[:5])}...")

except Exception as e:
    print(f"Error: {e}")
