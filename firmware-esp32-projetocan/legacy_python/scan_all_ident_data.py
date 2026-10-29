import csv
import os

LOG_DIR_ROOT = r"logs"

def scan_all_logs():
    print("--- Scanning ALL logs for ECU Identification ---")
    
    unique_findings = {} # Key: ID-SID-Data, Value: LogFile
    
    for root, dirs, files in os.walk(LOG_DIR_ROOT):
        for file in files:
            if not file.endswith(".csv"): continue
            
            path = os.path.join(root, file)
            # print(f"Processing {file}...")
            
            try:
                with open(path, 'r') as f:
                    reader = csv.reader(f, delimiter=',')
                    for row in reader:
                        if len(row) < 4: continue
                        
                        can_id = row[1].strip()
                        data_str = row[3].strip()
                        data_bytes = data_str.split(' ')
                        
                        if len(data_bytes) < 2: continue
                        
                        try:
                            b0 = int(data_bytes[0], 16)
                            ft = (b0 & 0xF0) >> 4
                            
                            sid = 0
                            payload = []
                            
                            if ft == 0 and len(data_bytes) > 2:
                                sid = int(data_bytes[1], 16) # SF
                                payload = data_bytes[2:] # Data after SID
                            elif ft == 1 and len(data_bytes) > 3:
                                sid = int(data_bytes[2], 16) # FF
                                payload = data_bytes[3:] # Data after SID
                            
                            # 0x5A (KWP Ident Resp), 0x62 (UDS ReadDataByIdent Resp), 0x61 (KWP ReadLocal Resp)
                            if sid in [0x5A, 0x62, 0x61]:
                                # Attempt ASCII decode
                                ascii_cand = ""
                                valid_chars = 0
                                for b_str in payload:
                                    try:
                                        b = int(b_str, 16)
                                        if 32 <= b <= 126:
                                            ascii_cand += chr(b)
                                            valid_chars += 1
                                    except: pass
                                
                                # Filter for meaningful strings (at least 3 valid chars)
                                if valid_chars >= 3:
                                    key = f"ID:{can_id} SID:{sid:02X} ASCII:{ascii_cand}"
                                    if key not in unique_findings:
                                        unique_findings[key] = file
                                        print(f"[{file}] {key}")
                        except:
                            pass
            except:
                pass

scan_all_logs()
