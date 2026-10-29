import subprocess, os

sz = r'C:\Program Files (x86)\BRP\BUDS2\ODXDataBin\7za.exe'
fw = r'C:\Program Files (x86)\BRP\BUDS2\ODXDataBin\Firmware.7z'
out_dir = r'C:\Users\johan\Documents\projetoCAN\temp_7z\firmware'
os.makedirs(out_dir, exist_ok=True)

# Just list / test integrity (no extract)
result = subprocess.run([sz, 't', fw], capture_output=True, text=True, timeout=30)
print('TEST result:')
print(result.stdout[-500:])
print(result.stderr[:200])
print('Return code:', result.returncode)
print()

# Try extracting one file to test
result2 = subprocess.run(
    [sz, 'e', fw, '-o' + out_dir, '*.xml', '-y', '-aoa'],
    capture_output=True, text=True, timeout=30
)
print('EXTRACT result code:', result2.returncode)
print(result2.stdout[-300:])
files = os.listdir(out_dir)
print(f'Extracted {len(files)} files')
for f in files[:5]:
    fp = os.path.join(out_dir, f)
    print(f'  {f}  ({os.path.getsize(fp)} bytes)')
    with open(fp, 'r', encoding='utf-8', errors='replace') as fh:
        print(fh.read()[:400])
