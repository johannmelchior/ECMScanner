
import csv
import glob
import os

def process_log(filepath):
    print(f"Processing {filepath}")
    
    # Store ISO-TP fragments
    # Key: ID, Value: { 'expected_seq': x, 'data': bytearray }
    # Simplified: We just look for standard 7E0/7E8 pair logic
    
    # This is a specialized parser for the trace we saw
    # We look for 7E8 messages
    
    msgs = []
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
             if len(row) < 4: continue
             try:
                can_id = int(row[1], 16)
                data_hex = row[3].replace(' ', '')
                data_bytes = bytes.fromhex(data_hex)
                msgs.append({'time': row[0], 'id': can_id, 'data': data_bytes})
             except:
                pass

    print(f"Loaded {len(msgs)} frames.")
    
    # Reassemble ISO-TP for 7E8 (Response)
    # We look for flow starting with 10 (First Frame)
    
    buffer = bytearray()
    expected_len = 0
    in_frame = False
    
    # We will search specifically around the 18 00 00 00 request
    # Request 04 18 00 00 00 found at ID 7E0
    
    for i, msg in enumerate(msgs):
        if msg['id'] == 0x7E0:
            if msg['data'][0] == 0x04 and msg['data'][1] == 0x18:
                print(f"Ref: Request Found at {msg['time']}: {msg['data'].hex(' ')}")
        
        if msg['id'] == 0x7E8:
            pci = msg['data'][0]
            pci_type = pci >> 4
            
            if pci_type == 0: # SF
                sid = msg['data'][1]
                if sid == 0x58 or sid == 0x59:
                    print(f"Single Frame Response at {msg['time']}: {msg['data'].hex(' ')}")
            
            elif pci_type == 1: # FF
                dl = ((pci & 0x0F) << 8) + msg['data'][1]
                buffer = bytearray(msg['data'][2:])
                expected_len = dl
                in_frame = True
                print(f"Start MultiFrame {dl} bytes at {msg['time']}")
                
            elif pci_type == 2: # CF
                if in_frame:
                    buffer.extend(msg['data'][1:])
                    if len(buffer) >= expected_len:
                        # Frame Complete
                        full_payload = buffer[:expected_len]
                        sid = full_payload[0]
                        print(f"MultiFrame Complete at {msg['time']}: {full_payload.hex(' ')}")
                        
                        if sid == 0x58 or sid == 0x59:
                            analyze_dtc_payload(full_payload)
                        
                        in_frame = False
                        buffer = bytearray()

def analyze_dtc_payload(data):
    sid = data[0]
    print(f"Analyzing Response SID {hex(sid)}")
    if sid == 0x58:
        # KWP: 58 <count> <DTC1_H> <DTC1_L> <Status> ...
        num_dtcs = data[1]
        print(f"Num Faults: {num_dtcs}")
        # BRP faults are often 2 bytes P-Code + 1 byte status? Or 3 bytes DTC?
        # Usually KWP is 2 byte DTC + 1 byte status
        
        offset = 2
        for k in range(num_dtcs):
            if offset + 2 >= len(data): break
            dtc_high = data[offset]
            dtc_low = data[offset+1]
            status = data[offset+2]
            
            code = (dtc_high << 8) | dtc_low
            print(f"  Fault {k+1}: P{code:04X} Status: {hex(status)}")
            offset += 3

if __name__ == "__main__":
    process_log("logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_155628.csv")
    process_log("logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_160153.csv")
