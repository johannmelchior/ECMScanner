
import csv
import glob
import os

def parse_logs():
    log_files = glob.glob('logs/BRP-SEADOO-GTX-2022-300hp/*.csv')
    log_files.sort()
    
    diag_req_id = 0x7E0
    diag_res_id = 0x7E8
    
    print(f"Scanning {len(log_files)} files for Diagnostic Messages (IDs {hex(diag_req_id)}, {hex(diag_res_id)})...")

    for log_file in log_files:
        print(f"Checking {os.path.basename(log_file)}...")
        has_diag = False
        try:
            with open(log_file, 'r') as f:
                reader = csv.reader(f)
                header = next(reader) # Skip header
                
                for row in reader:
                    # Expected format: Timestamp, ID, DLC, Data
                    if len(row) < 4: continue
                    
                    try:
                        can_id = int(row[1], 16)
                    except ValueError:
                        continue
                        
                    if can_id in [diag_req_id, diag_res_id]:
                        data_str = row[3]
                        print(f"[{os.path.basename(log_file)}] Time: {row[0]}, ID: {hex(can_id)}, Data: {data_str}")
                        has_diag = True
        except Exception as e:
            print(f"Error reading {log_file}: {e}")

if __name__ == "__main__":
    parse_logs()
