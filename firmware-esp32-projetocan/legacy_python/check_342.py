import csv
import collections
import time

LOG_FILE = r"logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_153244.csv"

def check_periodicity():
    timestamps = []
    values_b4 = []
    
    with open(LOG_FILE, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4: continue
            can_id = row[1].strip()
            
            if can_id == "400":
                try:
                    ts_str = row[0] 
                    data = [int(x, 16) for x in row[3].split()]
                    if len(data) > 7:
                        values_b4.append(data[7])
                except: pass

    if not values_b4:
        print("ID 400 not found")
        return

    print(f"ID 400 Count: {len(values_b4)}")
    c = collections.Counter(values_b4)
    for v, count in c.most_common():
        print(f"  {v:02X} ({v}) = {v/10.0}V? | Count: {count}")

check_periodicity()
