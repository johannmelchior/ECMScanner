import csv
import os

LOG_DIR_ROOT = "logs"
TARGET_IDS = ["7BA", "7BD", "7BB", "7E8"]  # IBR Mod, IBR Mon, Cluster, ECM

def is_ascii(byte_val):
    return 0x20 <= byte_val <= 0x7E

def analyze_ibr_logs():
    print("--- Detailed Analysis of IBR (7BA/7BD) Info ---")
    
    findings = {id: [] for id in TARGET_IDS}

    for root, dirs, files in os.walk(LOG_DIR_ROOT):
        for file in files:
            if not file.endswith(".csv"): continue
            
            path = os.path.join(root, file)
            # print(f"Scanning {file}...")
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                header = next(reader, None) # Skip header if exists
                
                for row in reader:
                    if len(row) < 4: continue
                    
                    try:
                        ts = row[0]
                        can_id_hex = row[1].strip()
                        can_id = can_id_hex.upper().replace("0X", "")
                        
                        if can_id not in TARGET_IDS: continue
                        
                        data_str = row[3].strip()
                        data_bytes = [int(b, 16) for b in data_str.split()]
                        
                        if not data_bytes: continue
                        
                        # ISO-TP / KWP Parsing
                        pci = data_bytes[0]
                        frame_type = (pci & 0xF0) >> 4
                        
                        sid = -1
                        payload = []
                        
                        if frame_type == 0: # SIngle Frame
                            dlc = pci & 0x0F
                            if len(data_bytes) > 2:
                                sid = data_bytes[1]
                                payload = data_bytes[2:2+dlc-1] # -1 for SID
                                
                        elif frame_type == 1: # First Frame
                            dlc_high = pci & 0x0F
                            dlc_low = data_bytes[1]
                            dlc = (dlc_high << 8) | dlc_low
                            sid = data_bytes[2]
                            payload = data_bytes[3:]
                            
                        elif frame_type == 2: # Consecutive Frame
                            # Just capture raw data for now as reconstructing CFs without state is hard
                            # But we can look for ASCII in it
                            payload = data_bytes[1:]
                            sid = 0xCF # Artificial SID for CF

                        # Filter for Ident Responses
                        # KWP: 5A (Pos Resp to 1A)
                        # UDS: 62 (Pos Resp to 22), 61 (Alternative?)
                        
                        if sid in [0x5A, 0x62, 0x61] or sid == 0xCF:
                            ascii_str = ""
                            for b in payload:
                                if is_ascii(b):
                                    ascii_str += chr(b)
                            
                            if len(ascii_str) > 2: # Filter noise
                                finding = f"[{file}] SID:{sid:02X} ASCII:'{ascii_str}' RAW:{data_str}"
                                if finding not in findings[can_id]:
                                    findings[can_id].append(finding)

                    except Exception as e:
                        continue

    for can_id in TARGET_IDS:
        print(f"\nResults for ID {can_id}:")
        if not findings[can_id]:
            print("  No info found.")
        for item in findings[can_id]:
            print(f"  {item}")

if __name__ == "__main__":
    analyze_ibr_logs()
