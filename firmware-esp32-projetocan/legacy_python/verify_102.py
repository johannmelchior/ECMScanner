import csv
import os

LOG_FILES = [
    r"logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_153244.csv",
    r"logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_160153.csv"
]

def analyze_102():
    for path in LOG_FILES:
        if not os.path.exists(path): continue
        print(f"\n--- Analyzing ID 102 in {path} ---")
        
        values_b4 = [] # Index 3
        values_b5 = [] # Index 4
        uds_intake = []
        uds_engine = []

        with open(path, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 4: continue
                can_id_str = row[1].strip().upper()
                
                # Check 102
                if can_id_str == "102":
                    data_hex = row[3].strip().split()
                    if len(data_hex) >= 8:
                        v4 = int(data_hex[3], 16)
                        v5 = int(data_hex[4], 16)
                        values_b4.append(v4)
                        values_b5.append(v5)

                # Check UDS
                if can_id_str == "7E8":
                    d = [int(x, 16) for x in row[3].split()]
                    if len(d) > 3 and d[1] == 0x62:
                        did = (d[2] << 8) | d[3]
                        if did == 0x2107: # Intake
                             val = d[4] # Byte 0 of payload
                             uds_intake.append(val/2.0)
                        if did == 0x2104: # Engine
                             # 2104 payload B0 1D ...
                             # Assuming byte 1 is the temp
                             if len(d) > 5:
                                uds_engine.append(d[5])

        if values_b4:
            avg4 = sum(values_b4)/len(values_b4)
            avg5 = sum(values_b5)/len(values_b5)
            print(f"ID 102 Byte 4 (Engine?) Avg: {avg4:.1f} (Hex {int(avg4):02X}) -> /3 = {avg4/3:.2f}")
            print(f"ID 102 Byte 5 (Intake?) Avg: {avg5:.1f} (Hex {int(avg5):02X}) -> /3 = {avg5/3:.2f}")
            
        if uds_engine:
            avg_eng = sum(uds_engine)/len(uds_engine)
            print(f"UDS Engine (2104) Avg: {avg_eng:.2f}")
        if uds_intake:
            avg_int = sum(uds_intake)/len(uds_intake)
            print(f"UDS Intake (2107) Avg: {avg_int:.2f}")

if __name__ == "__main__":
    analyze_102()
