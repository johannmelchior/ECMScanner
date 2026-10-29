import csv
import os

LOG_DIR = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\logs\BRP-SEADOO-RXT-X-AS-2011-260hp"
FILE_RUN = os.path.join(LOG_DIR, "funcionamento completo.csv")

def parse_csv(filepath):
    """ Returns dict: {id: {byte_idx: [values...], 'words': {idx: [vals...]}}} """
    data_map = {}
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        
        for row in reader:
            if not row or len(row) < 4: continue
            
            try:
                can_id = int(row[1], 16)
                data_str = row[3].strip()
                bytes_list = [int(b, 16) for b in data_str.split()]
                
                if can_id not in data_map:
                    data_map[can_id] = {}
                
                for i, val in enumerate(bytes_list):
                    if i not in data_map[can_id]:
                        data_map[can_id][i] = []
                    data_map[can_id][i].append(val)
                
                # Also store 16-bit words (Little Endian)
                if 'words' not in data_map[can_id]:
                    data_map[can_id]['words'] = {}
                
                for i in range(len(bytes_list)-1):
                    val16 = bytes_list[i] + (bytes_list[i+1] << 8) # LE
                    if i not in data_map[can_id]['words']:
                        data_map[can_id]['words'][i] = []
                    data_map[can_id]['words'][i].append(val16)

            except:
                continue
                
    return data_map

def analyze_candidates():
    print("Loading Run File...")
    run_data = parse_csv(FILE_RUN)
    
    candidates = []
    
    # Analyze Bytes & Words
    print(f"Analyzing {len(run_data)} IDs...")
    for can_id, content in run_data.items():
        # Bytes
        for b_idx in range(8):
            if b_idx not in content: continue
            values = content[b_idx]
            if len(values) < 50: continue
            
            start_val = values[0]; end_val = values[-1]
            min_val = min(values); max_val = max(values)
            delta = end_val - start_val
            unique_vals = set(values)
            
            if (max_val - min_val) > 10 and len(unique_vals) >= 5:
                  # Check trend
                  sample_rate = max(1, len(values) // 200)
                  sampled_vals = values[::sample_rate]
                  pos_steps = sum(1 for k in range(1, len(sampled_vals)) if sampled_vals[k] > sampled_vals[k-1])
                  total_steps = sum(1 for k in range(1, len(sampled_vals)) if sampled_vals[k] != sampled_vals[k-1])
                  ratio = pos_steps / total_steps if total_steps > 0 else 0
                  
                  if ratio > 0.6: # Strongly simple rising
                       candidates.append({"type": "Byte", "id": hex(can_id), "idx": b_idx, "start": start_val, "end": end_val, "delta": delta, "uniq": len(unique_vals), "min": min_val, "max": max_val})

        # Words (16-bit LE)
        if 'words' in content:
            for w_idx, values in content['words'].items():
                if len(values) < 50: continue
                
                start_val = values[0]; end_val = values[-1]
                min_val = min(values); max_val = max(values)
                delta = end_val - start_val
                unique_vals = set(values)
                
                # Range check > 50 (more resolution)
                if (max_val - min_val) > 50 and len(unique_vals) >= 10:
                      sample_rate = max(1, len(values) // 200)
                      sampled_vals = values[::sample_rate]
                      pos_steps = sum(1 for k in range(1, len(sampled_vals)) if sampled_vals[k] > sampled_vals[k-1])
                      total_steps = sum(1 for k in range(1, len(sampled_vals)) if sampled_vals[k] != sampled_vals[k-1])
                      ratio = pos_steps / total_steps if total_steps > 0 else 0
                      
                      if ratio > 0.7: # Very clean rise
                           candidates.append({"type": "Word", "id": hex(can_id), "idx": w_idx, "start": start_val, "end": end_val, "delta": delta, "uniq": len(unique_vals), "min": min_val, "max": max_val})

    # Sort
    candidates.sort(key=lambda x: x['delta'], reverse=True)
    
    print("\n--- CANDIDATES (Bytes & Words) ---")
    print(f"{'Type':<5} | {'ID':<8} | {'Idx':<3} | {'Start':<6} | {'End':<6} | {'Min':<6} | {'Max':<6} | {'Delta':<6} | {'Uniq'}")
    print("-" * 80)
    for c in candidates:
         print(f"{c['type']:<5} | {c['id']:<8} | {c['idx']:<3} | {c['start']:<6} | {c['end']:<6} | {c['min']:<6} | {c['max']:<6} | {c['delta']:<6} | {c['uniq']}")

if __name__ == "__main__":
    analyze_candidates()
