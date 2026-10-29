import sys
import re
import os

def strings(filename, min_len=4):
    with open(filename, "rb") as f:
        data = f.read()
        # Look for ASCII strings (encoded)
        pattern = b"[\x20-\x7E]{" + str(min_len).encode() + b",}"
        # Look for Unicode (UTF-16LE) strings often found in .NET
        pattern_uni = b"(?:[\x20-\x7E]\x00){" + str(min_len).encode() + b",}"
        
        ascii_strings = [x.decode('ascii') for x in re.findall(pattern, data)]
        uni_strings = [x.decode('utf-16le') for x in re.findall(pattern_uni, data)]
        
        return ascii_strings + uni_strings

def analyze(filepath):
    print(f"Analyzing {filepath}...")
    try:
        s = strings(filepath)
        
        keywords = ["http:", "https:", "www.", ".com", ".net", ".org", "ftp:"]
        
        print("--- Potential URLs / Network Calls ---")
        found = False
        for x in s:
            for k in keywords:
                if k in x.lower():
                    print(f"  {x}")
                    found = True
                    break
        if not found:
            print("No URLs found.")
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    base_path = r"C:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\original-software\BUDS2"
    files = [
        "BUDS2 License Registrator.exe"
    ]
    
    for f in files:
        full_path = os.path.join(base_path, f)
        if os.path.exists(full_path):
            analyze(full_path)
            print("\n" + "="*40 + "\n")
        else:
            print(f"File not found: {full_path}")
