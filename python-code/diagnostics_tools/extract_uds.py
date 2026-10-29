import csv
import sys

def analyze_uds(file_path):
    print(f"Analyzing {file_path}...")
    relevant_ids = {'7E0', '7E8', '7B3', '7BB'}
    
    with open(file_path, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4: continue
            
            timestamp = row[0]
            can_id = row[1]
            dlc = row[2]
            data_str = row[3]
            
            if can_id in relevant_ids:
                print(f"{timestamp},{can_id},{dlc},{data_str}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_uds(sys.argv[1])
    else:
        analyze_uds("logs/BRP-SEADOO-GTX-2022-300hp/can_log_20260123_160726.csv")
