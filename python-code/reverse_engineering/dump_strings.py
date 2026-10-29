import sys
import re

def strings(filename, min=4):
    with open(filename, errors="ignore") as f:  # Python 3: errors="ignore"
        # However, simpler to read binary
        pass
    
    with open(filename, "rb") as f:
        data = f.read()
        # Regex for ASCII strings
        result = re.findall(b"[A-Za-z0-9_ \-\.]{4,}", data)
        for r in result:
            try:
                print(r.decode("ascii"))
            except:
                pass

if __name__ == "__main__":
    strings(sys.argv[1])
