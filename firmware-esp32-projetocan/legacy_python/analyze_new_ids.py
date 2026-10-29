
import csv

log_file = r"logs/seadoo 2009 is 2.csv"
target_time_str = "13:30:46.225431"
target_command = "04 31 01 02 03" # The coil command

ids_before = set()
ids_after = set()
new_ids_times = {}
command_found = False

def time_to_seconds(t_str):
    # Format HH:MM:SS.micros
    h, m, s = t_str.split(':')
    return float(h) * 3600 + float(m) * 60 + float(s)

target_seconds = time_to_seconds(target_time_str)

with open(log_file, 'r') as f:
    reader = csv.reader(f)
    for row in reader:
        if len(row) < 3: continue
        
        ts_str = row[0]
        can_id = row[1]
        data = row[3] if len(row) > 3 else ""

        try:
            current_seconds = time_to_seconds(ts_str)
        except ValueError:
            continue


        if current_seconds < target_seconds:
            ids_before.add(can_id)
        else:
            ids_after.add(can_id)
            if can_id not in ids_before and can_id not in new_ids_times:
                new_ids_times[can_id] = ts_str

new_ids = ids_after - ids_before

print(f"IDs seen ONLY after {target_time_str}:")
for nid in new_ids:
    print(f"- {nid} first seen at {new_ids_times[nid]}")

if not new_ids:
    print("No new IDs found appearing only after the command.")
