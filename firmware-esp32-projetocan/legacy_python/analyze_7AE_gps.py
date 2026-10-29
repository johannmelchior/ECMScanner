import csv
import os

LOG_DIR_ROOT = "logs"
TARGET_ID = "7AE"

def analyze_gps_candidates():
    print(f"--- Detailed Analysis of {TARGET_ID} (Possible GPS) ---")
    
    findings = []

    for root, dirs, files in os.walk(LOG_DIR_ROOT):
        for file in files:
            if not file.endswith(".csv"): continue
            
            path = os.path.join(root, file)
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                for i, row in enumerate(rows):
                    if len(row) < 4: continue
                    
                    can_id = row[1].strip()
                    if can_id != TARGET_ID: continue
                    
                    data_str = row[3].strip()
                    data_bytes = [int(b, 16) for b in data_str.split()]
                    
                    # Look for UDS Positive Response (0x62)
                    # Frame Format: [PCI, SID, DID_H, DID_L, D1, D2, D3, D4] usually
                    
                    if len(data_bytes) > 2 and data_bytes[1] == 0x62:
                         # Single Frame Response
                         did = (data_bytes[2] << 8) | data_bytes[3]
                         payload = data_bytes[4:]
                         
                         ascii_str = "".join([chr(b) if 0x20 <= b <= 0x7E else '.' for b in payload])
                         print(f"[{file}] Line {i} [SF] DID:{did:04X} Data:{data_str} ASCII:{ascii_str}")
                         
                    elif len(data_bytes) > 2 and (data_bytes[0] & 0xF0) == 0x10 and data_bytes[2] == 0x62:
                        # First Frame of Response
                        dlc = (data_bytes[0] & 0x0F) << 8 | data_bytes[1]
                        did = (data_bytes[3] << 8) | data_bytes[4]
                        payload = data_bytes[5:]
                        ascii_str = "".join([chr(b) if 0x20 <= b <= 0x7E else '.' for b in payload])
                        print(f"[{file}] Line {i} [FF] DID:{did:04X} Data:{data_str} ASCII:{ascii_str}")
                        
                        # Print subsequent CFs to see full message
                        payload_full = payload
                        expected_len = dlc - 3 # Minus SID and DID
                        
                        collected = len(payload)
                        cf_idx = 1
                        while collected < expected_len and (i + cf_idx < len(rows)):
                            next_row = rows[i + cf_idx]
                            if len(next_row) < 4 or next_row[1].strip() != TARGET_ID:
                                cf_idx += 1
                                continue
                                
                            next_data = [int(b, 16) for b in next_row[3].strip().split()]
                            if (next_data[0] & 0xF0) == 0x20:
                                cf_payload = next_data[1:]
                                payload_full.extend(cf_payload)
                                collected += len(cf_payload)
                                print(f"    [CF] Data:{next_row[3].strip()}")
                            cf_idx += 1
                            
                        full_ascii = "".join([chr(b) if 0x20 <= b <= 0x7E else '.' for b in payload_full])
                        print(f"    -> FULL ASCII: {full_ascii}")

if __name__ == "__main__":
    analyze_gps_candidates()
