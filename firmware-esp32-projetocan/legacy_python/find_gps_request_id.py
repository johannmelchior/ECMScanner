import csv
import os

LOG_DIR_ROOT = "logs"
TARGET_RESP_ID = "7AE"

def find_request_for_7ae():
    print(f"--- Finding Request ID for {TARGET_RESP_ID} ---")

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
                    if can_id != TARGET_RESP_ID: continue
                    
                    data_str = row[3].strip()
                    data_bytes = [int(b, 16) for b in data_str.split()]
                    
                    # 7AE is Response (0x62)
                    # We are looking for the corresponding Request (0x22)
                    if len(data_bytes) > 2 and (data_bytes[1] == 0x62 or (data_bytes[0] & 0xF0 == 0x10 and data_bytes[2] == 0x62)):
                        
                        # Look explicitly backwards for a 0x22 (ReadDataByIdentifier)
                        did = 0
                        
                        if data_bytes[1] == 0x62: # SF
                            did = (data_bytes[2] << 8) | data_bytes[3]
                        elif data_bytes[2] == 0x62: # FF
                            did = (data_bytes[3] << 8) | data_bytes[4]

                        # Look back up to 20 lines
                        for j in range(1, 20):
                            if i - j < 0: break
                            prev_row = rows[i-j]
                            if len(prev_row) < 4: continue
                            
                            p_id = prev_row[1].strip()
                            p_data = [int(b, 16) for b in prev_row[3].strip().split()]
                            
                            # Check for 0x22 SID and matching DID
                            if len(p_data) >= 3 and p_data[1] == 0x22 and p_data[2] == (did >> 8) and p_data[3] == (did & 0xFF):
                                print(f"MATCH FOUND in {file}!")
                                print(f"  Req Line {i-j}: ID:{p_id} Data:{prev_row[3]} (Read DID {did:04X})")
                                print(f"  Res Line {i}: ID:{can_id} Data:{data_str}")
                                return # Found it, we likely only need one confirmation
                            
                            # Also check Single Frame format 0x03 22 ...
                            if len(p_data) >= 4 and p_data[0] == 0x03 and p_data[1] == 0x22 and p_data[2] == (did >> 8) and p_data[3] == (did & 0xFF):
                                print(f"MATCH FOUND in {file}!")
                                print(f"  Req Line {i-j}: ID:{p_id} Data:{prev_row[3]} (Read DID {did:04X})")
                                print(f"  Res Line {i}: ID:{can_id} Data:{data_str}")
                                return

if __name__ == "__main__":
    find_request_for_7ae()
