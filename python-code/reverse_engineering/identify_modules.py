import csv
import os

# Strings to find (from images)
TARGETS = {
    b"YDV02866": "VIN",
    b"278004394": "IBR_Part",
    b"278003434": "Cluster_Part",
    b"0420464492": "ECM_Part",
    b"278003899": "GPS_Part",
    b"464492": "ECM_Short",
    b"004394": "IBR_Short"
}

def identify_modules(folder_path):
    print(f"Scanning {folder_path} for Module Identification...")
    
    for filename in os.listdir(folder_path):
        if not filename.endswith(".csv"): continue
        filepath = os.path.join(folder_path, filename)
        
        # Simple ISO-TP Reassembly (Single + Multi Frame)
        buffer = {} # ID -> {data:[], size:0}
        
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            try: next(reader)
            except: pass
            
            for row in reader:
                if len(row) < 4: continue
                try:
                    can_id_hex = row[1]
                    can_id = int(can_id_hex, 16)
                    data = [int(x, 16) for x in row[3].strip().split()]
                    if not data: continue
                    
                    payload = []
                    
                    # ISO-TP Logic
                    pci = data[0]
                    ft = (pci & 0xF0) >> 4
                    
                    if ft == 0: # Single Frame
                        length = pci & 0x0F
                        payload = data[1:1+length]
                        check_payload(payload, can_id, filename)
                        
                    elif ft == 1: # First Frame
                        length = ((pci & 0x0F) << 8) | data[1]
                        buffer[can_id] = {'size': length, 'data': data[2:]}
                        
                    elif ft == 2: # Consecutive
                        if can_id in buffer:
                            buffer[can_id]['data'].extend(data[1:])
                            if len(buffer[can_id]['data']) >= buffer[can_id]['size']:
                                # Complete
                                full_data = buffer[can_id]['data'][:buffer[can_id]['size']]
                                check_payload(full_data, can_id, filename)
                                del buffer[can_id]
                                
                    elif ft == 3: # Flow Control
                        pass
                        
                except:
                    pass

def check_payload(data, can_id, filename):
    try:
        data_bytes = bytes(data)
        for target_bytes, label in TARGETS.items():
            if target_bytes in data_bytes:
                print(f"[MATCH] Found {label} ({target_bytes.decode()}) in {filename}")
                print(f"        Sender ID: {hex(can_id)}")
                # print(f"        Full Payload: {data_bytes}")
                print("-" * 30)
    except:
        pass

if __name__ == "__main__":
    identify_modules(r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp")
