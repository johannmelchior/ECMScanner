import subprocess, os
from collections import Counter

sz = r'C:\Program Files (x86)\BRP\BUDS2\ODXDataBin\7za.exe'

# Check Firmware.7z
fw = r'C:\Program Files (x86)\BRP\BUDS2\ODXDataBin\Firmware.7z'
result = subprocess.run([sz, 'l', fw], capture_output=True, text=True)

lines = result.stdout.split('\n')
exts = Counter()
names = []
for line in lines:
    parts = line.strip().split()
    if len(parts) >= 5 and '-' in parts[0] and ':' in parts[1]:
        name = parts[-1]
        ext = os.path.splitext(name)[1]
        exts[ext] += 1
        names.append(name)

print(f'Firmware.7z - Total arquivos: {len(names)}')
for ext, count in sorted(exts.items(), key=lambda x: -x[1])[:15]:
    label = ext if ext else '(sem ext)'
    print(f'  {label}: {count}')
print()
print('Primeiros 30 arquivos:')
for n in names[:30]:
    print(f'  {n}')

# Check BRPBin header
print()
print('=== BRPBin_25.7.0.i2s header ===')
with open(r'C:\Program Files (x86)\BRP\BUDS2\ODXDataBin\BRPBin_25.7.0.i2s', 'rb') as f:
    header = f.read(64)
print('Hex:', header.hex())
print('ASCII:', ''.join(chr(b) if 32 <= b < 127 else '.' for b in header))
