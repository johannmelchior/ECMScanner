import os
import json
import re

# Paths
BASE_DIR = os.getcwd()
ODX_DIR = os.path.join(BASE_DIR, 'original-software', 'BUDS2', 'ODXDataBin')
OUTPUT_JSON = os.path.join(BASE_DIR, 'docs', 'brp_translations.json')
OUTPUT_HEADER = os.path.join(BASE_DIR, 'main', 'brp_translations.h')

FILES = {
    'en': os.path.join(ODX_DIR, 'ODX_en.properties'),
    'pt': os.path.join(ODX_DIR, 'ODX_pt.properties')
}

def parse_properties(filepath):
    """Parses a Java .properties file handling unicode escapes."""
    data = {}
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return data

    print(f"Parsing {os.path.basename(filepath)}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Decode Java unicode escapes (e.g., \u00e9 -> é)
                # Python's 'unicode_escape' codec isn't perfect for all java properties nuances but works for \uXXXX
                try:
                    # Need to be careful not to decode normal backslashes that aren't escapes
                    # But .properties usually escapes everything.
                    value = value.encode('utf-8').decode('unicode_escape')
                except Exception as e:
                    pass # Keep raw if fail
                
                data[key] = value
    return data

def main():
    dict_en = parse_properties(FILES['en'])
    dict_pt = parse_properties(FILES['pt'])
    
    # Merge keys (union of all keys)
    all_keys = set(dict_en.keys()) | set(dict_pt.keys())
    
    # Build merged structure
    merged = {}
    for k in sorted(all_keys):
        merged[k] = {
            'en': dict_en.get(k, ""),
            'pt': dict_pt.get(k, "")
        }
    
    print(f"Total entries: {len(merged)}")
    
    # 1. Export JSON
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON to {OUTPUT_JSON}")
    
    # 2. Export C Header (Simplified - Only Keys that look like valid C identifiers or close to it)
    # Since 12k entries is too big for a single header array usually, 
    # we will generate a file that defines a struct but maybe commented out or just a few examples.
    # Actually, let's put it all in Flash memory (const).
    
    with open(OUTPUT_HEADER, 'w', encoding='utf-8') as f:
        f.write("#pragma once\n\n")
        f.write("// Generated BRP Translations (EN/PT)\n")
        f.write("// Stored in Flash (RODATA) to save RAM\n\n")
        f.write("#include <stddef.h>\n\n")
        f.write("typedef struct {\n")
        f.write("    const char* key;\n")
        f.write("    const char* en;\n")
        f.write("    const char* pt;\n")
        f.write("} BrpTranslation;\n\n")
        
        f.write(f"static const BrpTranslation BRP_DICT[{len(merged)}] = {{\n")
        
        for k in sorted(all_keys):
            en_val = dict_en.get(k, "").replace('"', '\\"').replace('\n', ' ')
            pt_val = dict_pt.get(k, "").replace('"', '\\"').replace('\n', ' ')
            # Use raw strings
            f.write(f'    {{"{k}", "{en_val}", "{pt_val}"}},\n')
            
        f.write("};\n\n")
        f.write(f"const size_t BRP_DICT_SIZE = {len(merged)};\n")

    print(f"Saved Header to {OUTPUT_HEADER}")

if __name__ == "__main__":
    main()
