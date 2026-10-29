import csv
import os

LOG_DIR = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-RXT-X-AS-2011-260hp"

def get_means(filepath):
    """ Returns dict: {id: {byte_idx: mean_val}} """
    sums = {}
    counts = {}
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if not row or len(row) < 4: continue
            try:
                can_id = int(row[1], 16)
                data_str = row[3].strip()
                bytes_list = [int(b, 16) for b in data_str.split()]
                
                if can_id not in sums:
                    sums[can_id] = {}
                    counts[can_id] = 0
                
                counts[can_id] += 1
                for i, val in enumerate(bytes_list):
                    if i not in sums[can_id]: sums[can_id][i] = 0
                    sums[can_id][i] += val
            except: pass
            
    means = {}
    for cid, s_map in sums.items():
        count = counts[cid]
        means[cid] = {i: s_map[i]/count for i in s_map}
    return means

def compare():
    print("Processing INIT...")
    means_init = get_means(os.path.join(LOG_DIR, "inicializacao.csv"))
    
    print("Processing RUN...")
    means_run = get_means(os.path.join(LOG_DIR, "funcionamento completo.csv"))
    
    print("\n--- SIGNIFICANT INCREASES (Mean RUN - Mean INIT > 20) ---")
    print(f"{'ID':<8} | {'Byte':<4} | {'Mean Init':<10} | {'Mean Run':<10} | {'Diff':<10}")
    print("-" * 60)
    
    for cid, map_run in means_run.items():
        if cid in means_init:
            map_init = means_init[cid]
            for i, m_run in map_run.items():
                if i in map_init:
                    m_init = map_init[i]
                    diff = m_run - m_init
                    # User said "Linear Increase" -> RUN should be higher than INIT
                    if diff > 10:
                        print(f"{hex(cid):<8} | {i:<4} | {m_init:<10.2f} | {m_run:<10.2f} | {diff:<10.2f}")

if __name__ == "__main__":
    compare()
