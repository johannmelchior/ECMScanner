import csv
import os
import binascii

LOG_DIR = r"logs/BRP-SEADOO-GTX-2022-300hp"
# logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_160153.csv seems to be initialization
LOG_FILES = [
    "can_log_20260123_160153.csv",
    "inicializacao.csv" 
]
TARGET_ID = "7BA" # IBR Response

def decode_ascii(hex_bytes):
    try:
        chars = [chr(int(b, 16)) for b in hex_bytes if int(b, 16) > 31 and int(b, 16) < 127]
        if len(chars) > 3:
            return "".join(chars)
    except:
        pass
    return ""

def scan_file(filename):
    path = os.path.join(LOG_DIR, filename)
    # Fallback to root logs if not in subdir
    if not os.path.exists(path):
        path = os.path.join("logs", filename)
        
    print(f"--- Scanning {filename} ---")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    unique_resps = set()
    
    with open(path, 'r') as f:
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            if len(row) < 4: continue
            
            can_id = row[1].strip()
            if can_id != TARGET_ID: continue
            
            data_str = row[3].strip()
            data_bytes = data_str.split(' ')
            if not data_bytes: continue
            
            # Reconstruct Multi-frame ISO-TP if possible, but for now just dump lines
            # to see if we spot the numbers
            
            # Simple signature
            sig = " ".join(data_bytes)
            if sig not in unique_resps:
                unique_resps.add(sig)
                ascii_dec = decode_ascii(data_bytes)
                if ascii_dec:
                    print(f"[{can_id}] {sig}  -> ASCII: {ascii_dec}")
                else:
                    print(f"[{can_id}] {sig}")

scan_file("can_log_20260123_160153.csv")
