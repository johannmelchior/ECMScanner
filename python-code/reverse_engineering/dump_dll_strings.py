import re

DLL_PATH = r'c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\original-software\BUDS2\seed_key.dll'

with open(DLL_PATH, 'rb') as f:
    data = f.read()

strings = re.findall(b'[ -~]{5,}', data)
print(f"Strings found: {len(strings)}")

for s in strings:
    print(s.decode('utf-8', 'ignore'))
