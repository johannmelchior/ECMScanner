import csv
import os

# Known Diagnostic IDs
DIAG_IDS = {
    0x7E0: "Engine-Req", 0x7E8: "Engine-Resp",
    0x7E1: "Cluster-Req", 0x7E9: "Cluster-Resp",
    0x7E2: "iBR-Req", 0x7EA: "iBR-Resp",
    0x7B2: "Tester-Req-new", 0x7BA: "Module-Resp-new",
    0x7BB: "Module-Resp-new2", 0x7B3: "Tester-Req-new2",
    0x712: "Something", 0x71A: "Something-Resp"
}

def analyze_diag_traffic(folder_path):
    print(f"Scanning {folder_path} for Diagnostic Traffic (19/59 or 18/58)...")
    
    for filename in os.listdir(folder_path):
        if not filename.endswith(".csv"): continue
        filepath = os.path.join(folder_path, filename)
        
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except: continue
            
            for row in reader:
                if len(row) < 4: continue
                try:
                    can_id = int(row[1], 16)
                    dlc = int(row[2])
                    data = [int(x, 16) for x in row[3].strip().split()]
                    
                    # Filter for known diagnostic IDs or similar (0x7XX)
                    if (can_id & 0x700) == 0x700:
                        # Check for UDS Response Service 0x59 (ReadDTC positive)
                        # Usually format: Len, Service, ...
                        # ISO-TP Single Frame: Byte0 = Len, Byte1 = Service
                        if len(data) > 2:
                            # Case 1: Single Frame (First byte is length)
                            if data[1] == 0x59: # Positive Response to 19
                                print(f"[{filename}] Found DTC Response (UDS) on ID {hex(can_id)}: {row[3]}")
                            if data[1] == 0x58: # Positive Response to 18 (KWP)
                                print(f"[{filename}] Found DTC Response (KWP) on ID {hex(can_id)}: {row[3]}")
                            
                            # Case 2: Multi-Frame (First byte is 1x, Second byte is len?)
                            # Not easy to spot single packet.
                            
                            # Check requests
                            if data[1] == 0x19:
                                print(f"[{filename}] Found DTC Request (UDS) on ID {hex(can_id)}: {row[3]}")
                            if data[1] == 0x18:
                                print(f"[{filename}] Found DTC Request (KWP) on ID {hex(can_id)}: {row[3]}")
                                
                except:
                    pass

if __name__ == "__main__":
    analyze_diag_traffic(r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp")
