import serial
import time
import threading
import queue

# --- Configuration ---
SERIAL_PORT = "COM3"  # CHANGE THIS to your ESP32's port
BAUD_RATE = 115200

# Scanner Configuration
START_ID = 0x7E0
REPLY_ID = 0x7E8
WAIT_TIMEOUT = 0.2  # Seconds to wait for a response

# ID Ranges to Scan (BRP Proprietary often uses F0xx or 02xx or 03xx)
ROUTINE_RANGES = [
    range(0x0200, 0x02FF), # Common Standard Range
    range(0xE000, 0xE0FF), # Proprietary
    range(0xF000, 0xF1FF), # Proprietary
]

running = True
resp_queue = queue.Queue()

def listener(ser):
    """Listens for RX packets from ESP32."""
    global running
    buffer = ""
    while running:
        try:
            if ser.in_waiting:
                chunk = ser.read(ser.in_waiting).decode(errors='ignore')
                buffer += chunk
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line.startswith("RX:"):
                        # Format: RX:ID,DLC,Data...
                        parts = line.split(',')
                        if len(parts) >= 3:
                            try:
                                can_id = int(parts[0].split(':')[1], 16)
                                data_bytes = [int(x, 16) for x in parts[2:]]
                                if can_id == REPLY_ID:
                                    resp_queue.put(data_bytes)
                            except: pass
        except Exception as e:
            print(f"Listener Error: {e}")
            break
        time.sleep(0.001)

def send_packet(ser, can_id, data):
    """Sends TX command to ESP32."""
    # Data is list of ints
    data_str = ",".join([f"{b:02X}" for b in data])
    # Pad to 8 bytes if needed (UDS is often 8)
    while len(data.split(',')) if isinstance(data, str) else len(data) < 8:
        # Actually logic above is wrong for list
        pass
    
    # Re-do list padding
    dlc = 8
    padded_data = list(data)
    while len(padded_data) < 8:
        padded_data.append(0)
            
    data_str = ",".join([f"{b:02X}" for b in padded_data])
    cmd = f"TX:{can_id:X},{dlc},{data_str}\n"
    ser.write(cmd.encode())

def scan_routine_control(ser):
    print(f"\n[!] Starting Routine Control (0x31) Scan on {hex(START_ID)}...")
    
    # 1. Enter Extended Session (0x10 0x03)
    print("[-] Requesting Extended Diagnostic Session...")
    send_packet(ser, START_ID, [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
    time.sleep(0.5)
    # Clear queue
    while not resp_queue.empty(): resp_queue.get()

    # 2. Scan
    found_routines = []
    
    for r_range in ROUTINE_RANGES:
        for rid in r_range:
            if not running: break
            
            rid_high = (rid >> 8) & 0xFF
            rid_low = rid & 0xFF
            
            # Service 31 (RoutineControl), 01 (Start), RID_H, RID_L
            # Note: Some actuators require params. We try valid 'Start' with no params first.
            payload = [0x04, 0x31, 0x01, rid_high, rid_low, 0x00, 0x00, 0x00]
            
            send_packet(ser, START_ID, payload)
            
            try:
                # Wait for response
                resp = resp_queue.get(timeout=WAIT_TIMEOUT)
                
                # Check Positive Response (0x71) or specific Negative Responses
                # Positive: 71 01 RID_H RID_L ...
                # Negative: 7F 31 RC ...
                
                if resp[1] == 0x71:
                    print(f"[+] POSITIVE RESPONSE for RID {hex(rid)}! (Actuator/Routine Valid)")
                    found_routines.append(rid)
                elif resp[1] == 0x7F and resp[2] == 0x31:
                    nrc = resp[3]
                    # Filter out "Service Not Supported" (0x11) or "Request Out of Range" (0x31) typical
                    # Interesting NRCs: 
                    # 0x22 (Conditions Not Correct - e.g. Engine must be off) -> FOUND!
                    # 0x24 (Sequence Error)
                    # 0x33 (Security Access Denied) -> FOUND! (Needs unlock)
                    
                    if nrc == 0x33:
                        print(f"[*] RID {hex(rid)} exists but requires Security Access (NRC 0x33)")
                        found_routines.append(rid)
                    elif nrc == 0x22:
                       print(f"[*] RID {hex(rid)} exists but conditions not met (NRC 0x22)")
                       found_routines.append(rid)
                    elif nrc != 0x31 and nrc != 0x11:
                       # 0x31 = RequestOutOfRange (ID doesn't exist)
                       # 0x11 = ServiceNotSupported
                       print(f"[?] RID {hex(rid)} gave unusual NRC: {hex(nrc)}")
                       
            except queue.Empty:
                pass
            
            if rid % 20 == 0:
                print(f"    Scanning {hex(rid)}...", end='\r')

    print("\n[=] Scan Complete.")
    print("Potential Actuator IDs found:", [hex(x) for x in found_routines])

if __name__ == "__main__":
    try:
        print(f"Opening {SERIAL_PORT}...")
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        time.sleep(2) # Wait for ESP32 reset
        
        t = threading.Thread(target=listener, args=(ser,))
        t.start()
        
        # Keep Alive Thread (Tester Present)
        def keep_alive():
            while running:
                # 0x3E Tester Present
                send_packet(ser, START_ID, [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                time.sleep(2.0)
        
        ka = threading.Thread(target=keep_alive)
        ka.start()
        
        scan_routine_control(ser)
        
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        running = False
        if 'ser' in locals() and ser.is_open: ser.close()
