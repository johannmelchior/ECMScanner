
import os

# Path to ODX.properties
odx_path = r"original-software/BUDS2/ODXDataBin/ODX.properties"

# Keywords to search for (case insensitive)
keywords = [
    "IBR", "Gate", "VTS", "Trim", "Suspension", "IS", "Cluster", 
    "RPM", "Speed", "Throttle", "TPS", "Brake", "Steering", 
    "Key", "Seed", "Security", "DTC", "Fault", "Service", "Reset", 
    "Actuator", "Sensor", "Pump", "Fan"
]

def search_buds_terms():
    if not os.path.exists(odx_path):
        print(f"File not found: {odx_path}")
        return

    print(f"Scanning {odx_path} for keywords: {', '.join(keywords)}...\n")
    
    found_count = 0
    results = {k: [] for k in keywords}

    try:
        with open(odx_path, 'r', encoding='latin-1') as f: # Properties files are often latin-1 or utf-8
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                
                if "=" in line:
                    key, value = line.split("=", 1)
                    value_lower = value.lower()
                    
                    for kw in keywords:
                        if kw.lower() in value_lower:
                            results[kw].append(f"{key} = {value}")
                            found_count += 1
                            
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Print Summary results
    print("-" * 60)
    for kw in keywords:
        matches = results[kw]
        if matches:
            print(f"--- MATCHES FOR '{kw.upper()}' ({len(matches)}) ---")
            # Limit to top 10 to avoid flooding, unless user asks for more
            for m in matches[:10]:
                print(m)
            if len(matches) > 10:
                print(f"... and {len(matches) - 10} more.")
            print("")
            
    print("-" * 60)
    print(f"Total matches found: {found_count}")

    # Optional: Save full results to a file
    with open("buds_terms_analysis.txt", "w", encoding="utf-8") as out:
        for kw in keywords:
             matches = results[kw]
             if matches:
                 out.write(f"\n--- {kw.upper()} ---\n")
                 for m in matches:
                     out.write(m + "\n")
    print("Full results saved to 'buds_terms_analysis.txt'")

if __name__ == "__main__":
    search_buds_terms()
