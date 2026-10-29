import csv
import os

LOG_DIR = r"logs/BRP-SEADOO-GTX-2022-300hp"
LOG_FILES = [
    "can_log_20260123_160153.csv",
    "can_log_20260123_160726.csv"
]
TARGET_IDS = ["7E0", "7B2", "7B3"]

def scan_file(filename):
    path = os.path.join(LOG_DIR, filename)
    print(f"--- Scanning {filename} ---")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    unique_cmds = set()

    with open(path, 'r') as f:
        reader = csv.reader(f, delimiter=',') # Assuming comma restricted
        # Skip header if exists (check first char of first line usually, but lets try robust)
        try:
             # Basic sniff? No just iterate
             pass
        except:
             pass
        
        for row in reader:
            if len(row) < 3: continue
            # Format usually: Timestamp, ID, DL, Data...
            # Or ID, Data...
            # Let's handle generic columns. 
            # Trying to find ID column.
            
            can_id_hex = ""
            data_bytes = []
            
            # Simple heuristic: Identify ID column by length/content
            # Our usual format is Timestamp;ID;DLC;D0;D1... or Timestamp,ID,DLC...
            # The prompt says delimiter is usually ; or ,
            
            # Let's reconstruct the line to be safe or parse carefully
            # If row[1] looks like "0x7E0" or "7E0"
            
            line_str = ",".join(row)
            if ";" in line_str:
                 row = line_str.split(";")
            
            # Try to locate ID
            try:
                # Common format: timestamp, id, dlc, d0...
                # row[1] might be ID
                potential_id = row[1].strip().replace("0x", "").upper()
                if potential_id in TARGET_IDS:
                    can_id_hex = potential_id
                    # Data starts at row[3] usually
                    data_part = row[3:]
                    # Filter empty or non-hex
                    data_bytes = [b.strip() for b in data_part if len(b.strip()) == 2]
                else:
                    # Maybe row[0] is ID?
                    potential_id = row[0].strip().replace("0x", "").upper()
                    if potential_id in TARGET_IDS:
                        can_id_hex = potential_id
                        data_bytes = [b.strip() for b in row[2:] if len(b.strip()) == 2]
            except:
                continue

            if can_id_hex and data_bytes:
                # Check for UDS Service 2F or 31
                # ISO-TP handling:
                # Single Frame: Byte 0 high nibble = 0. Service ID is Byte 1.
                # First Frame: Byte 0 high nibble = 1. Service ID is Byte 2.
                
                # Check First Byte (PCI)
                try:
                    pci = int(data_bytes[0], 16)
                    frame_type = (pci & 0xF0) >> 4
                    length = (pci & 0x0F)
                    
                    service_id = 0
                    payload_str = ""
                    
                    if frame_type == 0: # Single Frame
                        if len(data_bytes) > 1:
                            service_id = int(data_bytes[1], 16)
                            payload_str = " ".join(data_bytes[1:1+length])
                    elif frame_type == 1: # First Frame
                         if len(data_bytes) > 2:
                             service_id = int(data_bytes[2], 16)
                             payload_str = " ".join(data_bytes[2:]) + " (Multi-frame start)"
                    
                    if service_id in [0x2F, 0x31]:
                        cmd_sig = f"ID: {can_id_hex} | CMD: {payload_str}"
                        if cmd_sig not in unique_cmds:
                            unique_cmds.add(cmd_sig)
                            print(cmd_sig)
                except:
                    pass

scan_file("can_log_20260123_160153.csv")
scan_file("can_log_20260123_160726.csv")
