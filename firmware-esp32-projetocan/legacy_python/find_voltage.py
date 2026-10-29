import csv
import os
import statistics

LOG_FILES = {
    "IgnitionOn": r"logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_153244.csv",
    "Running": r"logs/funcionamento completo.csv"
}

def scan_voltage_candidates():
    candidates = {} # Key: (ID, ByteIndex, Size), Value: [IgnitionAvg, RunningAvg]

    # We are looking for something that is ~12.0 in IgnitionOn
    # And ~13.5-14.5 in Running (or at least different/higher if charging)
    # Or just fixed 12.0 if it's a regulated value or engine wasn't running in "Running" log properly.
    
    # 1 byte candidates
    print("Scanning for Voltage Candidates...")
        
    for name, path in LOG_FILES.items():
        if not os.path.exists(path):
            print(f"Skipping {name}, path not found: {path}")
            continue
            
        print(f"Processing {name} ({path})...")
        
        # Dictionary to store all bytes for each ID
        id_data = {} 
        
        with open(path, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 4: continue
                try:
                    can_id = int(row[1].strip(), 16)
                    data = [int(x, 16) for x in row[3].strip().split()]
                    
                    if can_id not in id_data: id_data[can_id] = []
                    id_data[can_id].append(data)
                except: pass
        
        # Analyze means for this file causes
        for can_id, messages in id_data.items():
            if not messages: continue
            msg_len = len(messages[0])
            
            # Check 1-byte values (Raw, Raw/10, Raw/20)
            for i in range(msg_len):
                values = [m[i] for m in messages if len(m) > i]
                if not values: continue
                avg = statistics.mean(values)
                
                # Check for ~12V (11.5 - 12.5) or ~120 (115 - 125)
                # 12.0 approx
                if 11.0 <= avg <= 13.0:
                    key = (can_id, i, 1, "x1")
                    if key not in candidates: candidates[key] = {}
                    candidates[key][name] = avg
                
                # 120 approx (12.0V)
                if 110 <= avg <= 130:
                    key = (can_id, i, 1, "/10")
                    if key not in candidates: candidates[key] = {}
                    candidates[key][name] = avg/10.0
                    
                # 60 approx (12.0V * 5)
                if 55 <= avg <= 65:
                    key = (can_id, i, 1, "/5")
                    if key not in candidates: candidates[key] = {}
                    candidates[key][name] = avg/5.0
            
            # Check 2-byte values (Big Endian)
            for i in range(msg_len - 1):
                values = [(m[i] << 8) | m[i+1] for m in messages if len(m) > i+1]
                if not values: continue
                avg = statistics.mean(values)
                
                # 1200 approx (12.00 V)
                if 1100 <= avg <= 1300:
                    key = (can_id, i, 2, "/100")
                    if key not in candidates: candidates[key] = {}
                    candidates[key][name] = avg/100.0
                    
                # 12000 approx (12.000 V)
                if 11000 <= avg <= 13000:
                    key = (can_id, i, 2, "/1000")
                    if key not in candidates: candidates[key] = {}
                    candidates[key][name] = avg/1000.0

    print("\n--- Potential Battery Voltage Candidates ---")
    print(f"{'ID':<10} {'Offset':<8} {'Size':<6} {'Scale':<8} {'Ignition (V)':<15} {'Running (V)':<15}")
    
    for key, measurements in candidates.items():
        ign = measurements.get("IgnitionOn", 0)
        run = measurements.get("Running", 0)
        
        # Filter: Must be present in IgnitionOn (since user saw it there)
        if ign == 0: continue
        
        # If we have both, running should ideally be higher or equal
        valid_trend = True
        if run > 0 and run < 10: valid_trend = False # Dropped too low?
        
        if valid_trend:
            can_id_hex = f"{key[0]:X}"
            offset = key[1]
            size = key[2]
            scale = key[3]
            print(f"{can_id_hex:<10} {offset:<8} {size:<6} {scale:<8} {ign:<15.2f} {run:<15.2f}")

if __name__ == "__main__":
    scan_voltage_candidates()
