import csv
import os

LOG_DIR_ROOT = "logs"

# Strings related to the GPS module from the image
SEARCH_STRINGS = [
    "GPSCAN",
    "278003899",
    "1001131822",
    "899A21621168",
    "1001133301",
    "1001167206",
    "340F0000"
]

def analyze_gps_logs():
    print("--- Searching for GPS Module Info ---")
    
    findings = {}

    for root, dirs, files in os.walk(LOG_DIR_ROOT):
        for file in files:
            if not file.endswith(".csv"): continue
            
            path = os.path.join(root, file)
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                
                rows = list(reader)
                for i, row in enumerate(rows):
                    if len(row) < 4: continue
                    
                    try:
                        can_id = row[1].strip()
                        data_str = row[3].strip()
                        data_bytes = [int(b, 16) for b in data_str.split()]
                        
                        # Convert to ASCII to check for matches
                        ascii_str = ""
                        for b in data_bytes:
                            if 0x20 <= b <= 0x7E:
                                ascii_str += chr(b)
                                
                        # Check for matches
                        match = False
                        for s in SEARCH_STRINGS:
                            if s in ascii_str: # Simple check, might be split across frames
                                match = True
                                break
                                
                        # Also check if we can construct a longer string from ISO-TP Consecutive Frames
                        # This is a bit complex for a simple script, but let's check basic ASCII chunks
                        
                        # Let's check for hex signature of 278003899 -> 32 37 38 30 30 33 38 39 39
                        # This typically appears in a 0x62 (UDS) or 0x5A (KWP) response
                        
                        if match or any(s in ascii_str for s in ["GPS", "899A", "27800", "10011"]):
                             print(f"[{file}] Line {i} ID:{can_id} Data:{data_str} ASCII:{ascii_str}")
                             # Print context (request)
                             if i > 0:
                                 prev = rows[i-1]
                                 print(f"   -> Request? ID:{prev[1]} Data:{prev[3]}")

                    except Exception as e:
                        pass

if __name__ == "__main__":
    analyze_gps_logs()
