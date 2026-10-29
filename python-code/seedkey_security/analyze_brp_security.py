import csv
import os

# Findings from manual analysis:
# Valid Exchange 1 (Message 155256.csv): Seed 0x466E -> Key 0x3B32
# Valid Exchange 2 (Message 155628.csv): Seed 0xBD9E -> Key 0x0639

def analyze_security_logs(folder_path):
    print(f"Scanning folder: {folder_path} for Security Access (Service 0x27)...")
    
    security_exchanges = []

    for filename in os.listdir(folder_path):
        if not filename.endswith(".csv"): continue
        
        filepath = os.path.join(folder_path, filename)
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                continue
            
            rows = list(reader)
            for i, row in enumerate(rows):
                if len(row) < 4: continue
                # format: time, id, dlc, data...
                try:
                    can_id_hex = row[1]
                    can_id = int(can_id_hex, 16)
                    data_str = row[3]
                    data = [int(x, 16) for x in data_str.strip().split()]
                    
                    # Check for Seed Response (0x67 01 ...)
                    if len(data) >= 3 and data[1] == 0x67 and data[2] == 0x01:
                        # Found a SEED
                        seed_bytes = data[3:5] if len(data) >= 5 else []
                        if len(seed_bytes) == 2:
                            seed_val = (seed_bytes[0] << 8) | seed_bytes[1]
                            print(f"\n[FOUND] Seed Response in {filename} line {i+2}")
                            print(f"  ID: {can_id_hex}, Data: {data_str}")
                            print(f"  Seed: 0x{seed_val:04X}")

                            # Look ahead for Key (0x27 02 ...)
                            # Usually from a paired ID (e.g. 7BA -> response to 7B2)
                            # We look for ANY '27 02' nearby
                            for j in range(i, min(i+50, len(rows))):
                                r_next = rows[j]
                                d_next = [int(x, 16) for x in r_next[3].strip().split()]
                                if len(d_next) >= 4 and d_next[1] == 0x27 and d_next[2] == 0x02:
                                    key_bytes = d_next[3:5]
                                    key_val = (key_bytes[0] << 8) | key_bytes[1]
                                    print(f"  -> Key Sent at line {j+2} (ID {r_next[1]}): 0x{key_val:04X}")
                                    break
                except:
                    pass

if __name__ == "__main__":
    # Point to the 2022 logs
    log_dir = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp"
    analyze_security_logs(log_dir)
