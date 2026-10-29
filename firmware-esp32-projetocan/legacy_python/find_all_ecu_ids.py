import csv
import os

LOG_DIR = r"logs/BRP-SEADOO-GTX-2022-300hp"
LOG_FILES = [
    "can_log_20260123_160153.csv",
    "can_log_20260123_160726.csv",
    "inicializacao.csv"
]

def scan_for_ident(filename):
    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path):
         # Try root
         path = os.path.join("logs", filename)
         if not os.path.exists(path): return

    print(f"--- Scanning {filename} ---")
    
    seen_responses = set()

    with open(path, 'r') as f:
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            if len(row) < 4: continue
            
            can_id = row[1].strip()
            data_str = row[3].strip()
            data_bytes = data_str.split(' ')
            if not data_bytes: continue
            
            try:
                # Check for KWP Ident Response: 5A ...
                # or UDS Ident Response: 62 ...
                
                # We need to handle PCI byte(s)
                # SF: [Len] [SID] ...
                # FF: [1x] [Len] [SID] ...
                
                pci = int(data_bytes[0], 16)
                ft = (pci & 0xF0) >> 4
                
                sid = 0
                payload = []
                
                if ft == 0: # SF
                    if len(data_bytes) > 2:
                        sid = int(data_bytes[1], 16)
                        payload = data_bytes[1:]
                elif ft == 1: # FF
                    if len(data_bytes) > 3:
                        sid = int(data_bytes[2], 16)
                        payload = data_bytes[2:]

                # 0x5A = KWP ReadEcuIdent Positive Response
                # 0x62 = UDS ReadDataByIdent Positive Response
                if sid in [0x5A, 0x62]:
                    sig = f"ID: {can_id} | SID: {sid:02X} | Data: {' '.join(payload)}"
                    if sig not in seen_responses:
                        seen_responses.add(sig)
                        print(sig)
                        
                        # Try to decode ASCII
                        ascii_str = ""
                        for b_str in payload:
                            b = int(b_str, 16)
                            if 32 <= b <= 126:
                                ascii_str += chr(b)
                        print(f"   -> ASCII: {ascii_str}")

            except:
                pass

for f in LOG_FILES:
    scan_for_ident(f)
