import csv
import os

LOG_DIR = r"logs/BRP-SEADOO-GTX-2022-300hp"
FILENAME = "can_log_20260123_160153.csv"
TARGET_ID = "7BA"

def reconstruct_iso_tp(log_file):
    path = os.path.join(LOG_DIR, log_file)
    if not os.path.exists(path): return

    print(f"--- Reconstructing ISO-TP for {TARGET_ID} in {log_file} ---")
    
    current_msg = {} # {id: {size, data, timestamp}}
    
    with open(path, 'r') as f:
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            if len(row) < 4: continue
            can_id = row[1].strip()
            if can_id != TARGET_ID: continue
            
            data_str = row[3].strip()
            data_bytes_hex = data_str.split(' ')
            if not data_bytes_hex: continue
            
            try:
                data_bytes = [int(b, 16) for b in data_bytes_hex]
                pci = data_bytes[0]
                frame_type = (pci & 0xF0) >> 4
                
                # Single Frame
                if frame_type == 0:
                    length = pci & 0x0F
                    payload = data_bytes[1:1+length]
                    print_payload(payload, "SF")
                    
                # First Frame
                elif frame_type == 1:
                    length = ((pci & 0x0F) << 8) + data_bytes[1]
                    payload = data_bytes[2:]
                    current_msg = {'total_len': length, 'data': payload}
                
                # Consecutive Frame
                elif frame_type == 2:
                    if current_msg:
                        payload = data_bytes[1:]
                        current_msg['data'].extend(payload)
                        if len(current_msg['data']) >= current_msg['total_len']:
                            final_data = current_msg['data'][:current_msg['total_len']]
                            print_payload(final_data, "MF")
                            current_msg = {} # Reset
            except:
                pass

def print_payload(data, ftype):
    # Decode ASCII if possible
    ascii_str = ""
    try:
        chars = [chr(b) for b in data if 31 < b < 127]
        if len(chars) > 3:
            ascii_str = "".join(chars)
    except: pass
    
    hex_str = " ".join([f"{b:02X}" for b in data])
    
    # Check for Service IDs
    sid = data[0] if len(data) > 0 else 0
    sid_name = ""
    if sid == 0x5A: sid_name = "ReadEcuIdent_Resp"
    if sid == 0x62: sid_name = "ReadDataByIdent_Resp"
    if sid == 0x61: sid_name = "ReadDataByLocal_Resp"
    
    if ascii_str:
        print(f"[{ftype}] {hex_str} | ASCII: {ascii_str} | {sid_name}")
    else:
        print(f"[{ftype}] {hex_str} | {sid_name}")

reconstruct_iso_tp(FILENAME)
