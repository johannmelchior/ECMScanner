import csv
import glob
import os

def analyze_uds(filepath):
    print(f"Analyzing {filepath}...")
    msgs = []
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except:
            return

        for row in reader:
             if len(row) < 4: continue
             try:
                can_id_str = row[1]
                can_id = int(can_id_str, 16)
                data_hex = row[3].replace(' ', '')
                data_bytes = bytes.fromhex(data_hex)
                msgs.append({'time': row[0], 'id': can_id, 'data': data_bytes, 'id_str': can_id_str})
             except:
                pass

    # Generic ISO-TP Reassembly
    # We maintain a buffer per ID
    buffers = {} # {id: {'buf': bytearray, 'len': int, 'time': str}}

    for i, msg in enumerate(msgs):
        can_id = msg['id']
        data = msg['data']
        if not data: continue
        
        pci = data[0]
        pci_type = pci >> 4
        
        # Requests (Service IDs detection in SF or FF)
        service_id = None
        payload = None
        
        # Single Frame
        if pci_type == 0:
            datalen = pci & 0x0F
            if datalen == 0 and len(data)>1: datalen = data[1] # CAN FD not likely here
            if datalen > 0 and (1+datalen) <= len(data):
                payload = data[1:1+datalen]
                service_id = payload[0]
                
        # First Frame
        elif pci_type == 1:
            datalen = ((pci & 0x0F) << 8) + data[1]
            if can_id not in buffers:
                 buffers[can_id] = {}
            buffers[can_id] = {'buf': bytearray(data[2:]), 'len': datalen, 'time': msg['time']}
            
            # Note: We can only check service_id after full reassembly for multi-frame
                
        # Consecutive Frame
        elif pci_type == 2:
            if can_id in buffers:
                buffers[can_id]['buf'].extend(data[1:])
                if len(buffers[can_id]['buf']) >= buffers[can_id]['len']:
                    payload = buffers[can_id]['buf'][:buffers[can_id]['len']]
                    service_id = payload[0]
                    # Print Reassembled
                    del buffers[can_id]
        
        # Flow Control (3) - ignore
        
        if payload:
            is_request = False
            # Common Request SIDs
            if service_id in [0x10, 0x11, 0x14, 0x18, 0x19, 0x22, 0x27, 0x2E, 0x31, 0x3E, 0x84, 0x85]:
                is_request = True
                
            # Common Response SIDs (Request + 0x40) or 0x7F
            is_response = False
            if service_id == 0x7F:
                is_response = True
            elif service_id > 0x40:
                # Check if it corresponds to a known service
                req_sid = service_id - 0x40
                if req_sid in [0x10, 0x11, 0x14, 0x18, 0x19, 0x22, 0x27, 0x2E, 0x31, 0x3E, 0x84, 0x85]:
                    is_response = True
            
            # Filter specifically for DTC related
            # 18 (KWP Read DTC), 19 (UDS Read DTC), 84 (Proprietary)
            # Responses: 58, 59, C4
            
            if service_id in [0x18, 0x19, 0x58, 0x59, 0x84, 0xC4] or (service_id == 0x7F and  len(payload)>1 and payload[1] in [0x18, 0x19, 0x84]):
                
                direction = "unknown"
                if service_id in [0x18, 0x19, 0x84]: direction = "REQ"
                if service_id in [0x58, 0x59, 0xC4, 0x7F]: direction = "RES"
                
                print(f"{msg['time']} ID:{msg['id_str']} {direction} SID:{hex(service_id)} Data:{payload.hex(' ')}")
                
                if service_id == 0xC4:
                    parse_brp_faults(payload)
                elif service_id == 0x59:
                     parse_uds_faults(payload)

def parse_brp_faults(payload):
    # C4 CD ... assumption
    if len(payload) > 4:
        count = payload[4]
        print(f"    [BRP] Count: {count}")
        idx = 5
        for i in range(count):
             if idx+2 < len(payload):
                 code = payload[idx:idx+2]
                 st = payload[idx+2]
                 print(f"    Fault: {decode_dtc(code)} Status: {hex(st)}")
                 idx += 3
        
        # Check for ASCII remainder?
        if idx < len(payload):
            remainder = payload[idx:]
            try:
                # Try to filter only printable ASCII
                ascii_str = ""
                for b in remainder:
                    if 0x20 <= b <= 0x7E:
                        ascii_str += chr(b)
                print(f"    Possible ASCII: {ascii_str}")
            except:
                pass


def parse_uds_faults(payload):
    print(f"    [UDS] Payload: {payload.hex(' ')}")

def decode_dtc(b):
    if len(b) < 2: return "??"
    b1 = b[0]
    b2 = b[1]
    
    type_bits = (b1 & 0xC0) >> 6
    chars = "PCBU"
    char = chars[type_bits]
    code_val = ((b1 & 0x3F) << 8) | b2
    return f"{char}{code_val:04X}"


if __name__ == "__main__":
    analyze_uds("logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_155628.csv")
