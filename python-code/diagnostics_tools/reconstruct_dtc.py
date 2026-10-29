import csv

def parse_iso_tp(filepath, target_id=0x7BB):
    print(f"Parsing ISO-TP for ID {hex(target_id)} in {filepath}...")
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except: pass
        
        buffer = {} # ID -> { 'size': 0, 'data': [], 'next_sn': 0 }
        
        for row in reader:
            if len(row) < 4: continue
            try:
                can_id = int(row[1], 16)
                if can_id != target_id: continue
                
                data = [int(x, 16) for x in row[3].strip().split()]
                if not data: continue
                
                # PCI Byte
                pci = data[0]
                frame_type = (pci & 0xF0) >> 4
                
                if frame_type == 0: # Single Frame
                    length = pci & 0x0F
                    payload = data[1:1+length]
                    print(f"Single Frame: {payload}")
                    if len(payload) > 1 and payload[0] == 0x59:
                         print(f" -> UDS Response: {payload}")
                    elif len(payload) > 1 and payload[0] == 0x58:
                         print(f" -> KWP Response: {payload}")

                elif frame_type == 1: # First Frame
                    length = ((pci & 0x0F) << 8) | data[1]
                    payload = data[2:]
                    buffer[can_id] = {'size': length, 'data': payload, 'next_sn': 1}
                    print(f"Start Multi-Frame: Expecting {length} bytes. Got {len(payload)} so far.")

                elif frame_type == 2: # Consecutive Frame
                    sn = pci & 0x0F
                    if can_id in buffer:
                        expected_sn = buffer[can_id]['next_sn']
                        if sn != expected_sn:
                            print(f"[Warning] Sequence Jump! Expected {expected_sn}, got {sn}")
                        
                        payload = data[1:]
                        buffer[can_id]['data'].extend(payload)
                        buffer[can_id]['next_sn'] = (sn + 1) & 0x0F
                        
                        current_len = len(buffer[can_id]['data'])
                        print(f" -> Appended {len(payload)} bytes. Total: {current_len}/{buffer[can_id]['size']}")
                        
                        if current_len >= buffer[can_id]['size']:
                            full_data = buffer[can_id]['data'][:buffer[can_id]['size']]
                            print(f"Reassembly Complete: {['{:02X}'.format(x) for x in full_data]}")
                            if full_data[0] == 0x59:
                                print(" -> UDS ReadDTC Response!")
                                parse_dtc_uds(full_data)
                            del buffer[can_id]
            except Exception as e:
                # print(e)
                pass

def parse_dtc_uds(data):
    # Data[0] = 59
    # Data[1] = Subfunction
    # Data[2] = Availability Mask / Count
    # Then DTCs...
    print("Parsing DTCs...")
    idx = 2
    count = 0
    while idx < len(data) - 3:
        # DTC is usually 3 bytes + 1 status, or 3 bytes (if status included in wrapper)
        # BRP 2022 is likely 3 bytes DTC + 1 byte Status
        dtc_bytes = data[idx:idx+3]
        status = data[idx+3]
        dtc_hex = "".join([f"{b:02X}" for b in dtc_bytes])
        print(f"  DTC #{count+1}: {dtc_hex} Status: {status:02X}")
        idx += 4
        count += 1

if __name__ == "__main__":
    parse_iso_tp(r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp\can_log_20260123_152804.csv", 0x7BB)
    parse_iso_tp(r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp\can_log_20260123_153244.csv", 0x7BD)
