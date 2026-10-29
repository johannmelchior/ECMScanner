import csv
import os

FILE_PATH = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\funcionamento completo.csv"

def parse_csv(filepath):
    data_map = {} # ID -> List of rows
    try:
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                if len(row) < 4: continue
                ts, hex_id_str, dlc, data_str = row
                try:
                    can_id = int(hex_id_str, 16)
                    data_bytes = [int(x, 16) for x in data_str.strip().split()]
                    if len(data_bytes) < 8:
                        data_bytes += [0] * (8 - len(data_bytes))
                    
                    if can_id not in data_map:
                        data_map[can_id] = []
                    data_map[can_id].append(data_bytes)
                except:
                    pass
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return {}
    return data_map

def analyze_110(rows):
    if not rows:
        print("\n=== ID 110: No Data ===")
        return

    print(f"\n=== ID 110 Analysis ({len(rows)} packets) ===")
    
    # 1. Check for constant bytes vs changing bytes
    byte_values = [set() for _ in range(8)]
    for data in rows:
        for i in range(8):
            byte_values[i].add(data[i])
            
    print("Byte Variability:")
    for i in range(8):
        vals = sorted(list(byte_values[i]))
        if len(vals) == 1:
            print(f"  Byte {i}: Constant {vals[0]} (0x{vals[0]:02X})")
        else:
            print(f"  Byte {i}: {len(vals)} unique values: {[f'0x{v:02X}' for v in vals[:10]]}...")

    # 2. Look for patterns in changing bytes
    # print samples of unique payloads
    unique_payloads = set()
    for data in rows:
        unique_payloads.add(tuple(data))
    
    print(f"\n  Unique 0x110 Payloads ({len(unique_payloads)} total):")
    for up in list(unique_payloads)[:20]:
        print(f"    {' '.join([f'{b:02X}' for b in up])}")

def analyze_103(rows):
    if not rows:
        print("\n=== ID 103: No Data ===")
        return

    print(f"\n=== ID 103 Analysis ({len(rows)} packets) ===")
    
    b6_vals = []
    b7_vals = []
    val16_vals = []
    
    for data in rows:
        b6 = data[6]
        b7 = data[7]
        val16 = (b6 << 8) | b7
        b6_vals.append(b6)
        b7_vals.append(b7)
        val16_vals.append(val16)
        
    print(f"  B6: Min={min(b6_vals)}, Max={max(b6_vals)}, Avg={sum(b6_vals)/len(b6_vals):.1f}")
    print(f"  B7: Min={min(b7_vals)}, Max={max(b7_vals)}, Avg={sum(b7_vals)/len(b7_vals):.1f}")
    print(f"  16-bit (B6<<8|B7): Min={min(val16_vals)}, Max={max(val16_vals)}")
    print(f"  First 10 16-bit values: {val16_vals[:10]}")

def analyze_102(rows):
    if not rows: return
    print(f"\n=== ID 102 Analysis ({len(rows)} packets) ===")
    rpms = []
    tpss = []
    temps = [] # B3
    maps = [] # B4
    b5s = []
    b6s = []
    
    for data in rows:
        val_rpm = ((data[0] << 8) | data[1]) / 4
        val_tps = (data[2] / 255.0) * 100
        val_temp = data[3]
        val_map = data[4]
        
        rpms.append(val_rpm)
        tpss.append(val_tps)
        temps.append(val_temp)
        maps.append(val_map)
        b5s.append(data[5])
        b6s.append(data[6])
        
    print(f"  RPM: Min={min(rpms):.0f}, Max={max(rpms):.0f}")
    print(f"  TPS: Min={min(tpss):.1f}%, Max={max(tpss):.1f}%")
    print(f"  B3 (Exhaust/Temp?): Min={min(temps)}, Max={max(temps)}, Avg={sum(temps)/len(temps):.1f}")
    print(f"  B4 (MAP/Temp?): Min={min(maps)}, Max={max(maps)}, Avg={sum(maps)/len(maps):.1f}")
    print(f"  B5: Range [{min(b5s)}-{max(b5s)}]")
    print(f"  B6: Range [{min(b6s)}-{max(b6s)}]")

def main():
    if not os.path.exists(FILE_PATH):
        print("File not found.")
        return
        
    data = parse_csv(FILE_PATH)
    
    analyze_102(data.get(0x102))
    analyze_103(data.get(0x103))
    analyze_110(data.get(0x110))
    
    # Quick check for IBR
    if 0x230 in data:
        print(f"\n=== ID 230 (IBR Trigger B5) ===")
        b5s = [d[5] for d in data[0x230]]
        print(f"  Min={min(b5s)}, Max={max(b5s)} (Raw)")

    if 0x204 in data:
        print(f"\n=== ID 204 (Gate B1/B0?) ===")
        b1s = [d[1] for d in data[0x204]]
        print(f"  B1: Min={min(b1s)}, Max={max(b1s)} (Raw)")

if __name__ == "__main__":
    main()
