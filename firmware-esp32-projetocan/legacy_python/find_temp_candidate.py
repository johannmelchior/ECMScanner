import csv
import math

# FILE = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-RXT-X-AS-2011-260hp\funcionamento completo.csv"
# Using relative path for the tool
FILE = "logs/BRP-SEADOO-RXT-X-AS-2011-260hp/funcionamento completo.csv"

def get_signal(target_id, byte_idx):
    timestamps = []
    values = []
    with open(FILE, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        start_t = None
        for row in reader:
            if not row or len(row) < 4: continue
            try:
                cid = int(row[1], 16)
                if cid == target_id:
                    d = [int(x, 16) for x in row[3].split()]
                    if byte_idx < len(d):
                        t_str = row[0]
                        # simplified time parsing from HH:MM:SS.ffffff
                        h, m, s = t_str.split(':')
                        s, ms = s.split('.')
                        t = int(h)*3600 + int(m)*60 + int(s) + float("0."+ms)
                        if start_t is None: start_t = t
                        timestamps.append(t - start_t)
                        values.append(d[byte_idx])
            except: pass
    return timestamps, values

def analyze():
    # Get Baseline: Engine Temp (0x102 Byte 3)
    t_eng, v_eng = get_signal(0x102, 3)
    
    if not v_eng:
        print("No Engine Temp data found")
        return

    # Normalize baseline comparison removed since no numpy
    
    print(f"Engine Temp (0x102 B3): Start={v_eng[0]}, End={v_eng[-1]}, Min={min(v_eng)}, Max={max(v_eng)}")

    # Scan all other bytes for similar positive correlation
    candidates = []
    
    # helper to get all IDs
    all_ids = set()
    with open(FILE, 'r') as f:
        for row in csv.reader(f):
            if len(row)>1: 
                try: all_ids.add(int(row[1], 16))
                except: pass
    
    print(f"Scanning {len(all_ids)} IDs for correlation...")
    
    for cid in all_ids:
        for b_idx in range(8):
            if cid == 0x102 and b_idx == 3: continue # Skip self
            
            t_cand, v_cand = get_signal(cid, b_idx)
            if len(v_cand) < 100: continue
            
            # Simple check: does it rise?
            delta = v_cand[-1] - v_cand[0]
            if delta <= 0: continue # User said "altera pra cima" (changes up)
            
            # Range check - Exhaust temp should be hotter than engine? Or user just says "similar behavior"
            # Engine temp went from 91 to 97 (Raw) -> roughly 30C to 32C. 
            # Wait, 91/3 = 30C. 97/3 = 32C. It rose slightly.
            # We are looking for something that matches this slight rise strictly?
            # Or something that rises more?
            
            # Let's verify correlation if lengths match strictly? No, sampling rates differ.
            # Just look for signals that increase monotonically or smooth.
            
            start = v_cand[0]
            end = v_cand[-1]
            diff = end - start
            
            # Check unique values (is it analog?)
            uniq = len(set(v_cand))
            if uniq < 3: continue
            
            candidates.append((cid, b_idx, start, end, diff, uniq))
            
    candidates.sort(key=lambda x: x[4], reverse=True) # Sort by delta
    
    print(f"{'ID':<6} | {'B':<2} | {'Start':<5} | {'End':<5} | {'Diff':<5} | {'Uniq':<5}")
    print("-" * 45)
    for c in candidates[:20]:
         print(f"{hex(c[0]):<6} | {c[1]:<2} | {c[2]:<5} | {c[3]:<5} | {c[4]:<5} | {c[5]:<5}")

if __name__ == "__main__":
    analyze()
