import csv
import os

LOGS = [
    r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp\can_log_20260123_160153.csv",
    r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp\can_log_20260123_160726.csv"
]

def analyze_actuators():
    for filepath in LOGS:
        print(f"Scanning {os.path.basename(filepath)} for Routine Control (31 01)...")
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            try: next(reader)
            except: pass
            
            for row in reader:
                if len(row) < 4: continue
                # Look for requests on 7E0 or 7B2 or similar
                can_id_hex = row[1]
                data = [int(x, 16) for x in row[3].strip().split()]
                
                # Check for Service 31 (Routine Control)
                if len(data) >= 4 and data[1] == 0x31 and data[2] == 0x01:
                    routine_id = (data[3] << 8) | data[4]
                    print(f"  [FOUND] Routine Start Request on ID {can_id_hex}")
                    print(f"    Routine ID: {hex(routine_id)} ({routine_id})")
                    print(f"    Full Payload: {row[3]}")
                    
                    # Look for response
                    # Usually 7E8 or 7BA sending 71 01 ...
                    
                # Check for IO Control (Service 2F)
                if len(data) >= 3 and data[1] == 0x2F:
                    did = (data[2] << 8) | data[3]
                    print(f"  [FOUND] IO Control (2F) on ID {can_id_hex}")
                    print(f"    DID: {hex(did)}")
                    print(f"    Full Payload: {row[3]}")

if __name__ == "__main__":
    analyze_actuators()
