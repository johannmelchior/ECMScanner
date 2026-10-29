import csv
import os

def analyze_uds(file_path):
    print(f"Analyzing {file_path}...")
    relevant_ids = {'7E0', '7E8', '7B3', '7BB'}
    output_path = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\extracted_uds.csv"
    
    with open(file_path, 'r') as f, open(output_path, 'w') as out:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4: continue
            
            timestamp = row[0]
            can_id = row[1]
            dlc = row[2]
            data_str = row[3]
            
            if can_id in relevant_ids:
                out.write(f"{timestamp},{can_id},{dlc},{data_str}\n")
    print(f"Done. Wrote to {output_path}")

if __name__ == "__main__":
    analyze_uds(r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-GTX-2022-300hp\can_log_20260123_160726.csv")
