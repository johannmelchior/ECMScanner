"""
Inspect the structure of the BUDS2 license .xml.bin file
"""
import base64, struct, glob, os

# Find the license file
paths = glob.glob(r'C:\Users\*\in2soft_license\1225765425\*.xml.bin')
if not paths:
    print('No license file found!')
    exit(1)

path = paths[0]
raw_b64 = open(path, 'rb').read()
raw = base64.b64decode(raw_b64)
print(f'File: {path}')
print(f'File size on disk: {len(raw_b64)} bytes  (Base64 text)')
print(f'Decoded size: {len(raw)} bytes')
print()

# Header analysis
print('=== First 64 bytes ===')
h = raw[:64]
for i in range(0, 64, 16):
    chunk = h[i:i+16]
    hex_part = chunk.hex()
    asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f'  {i:4d}: {hex_part}  |{asc_part}|')

print()
u32_be_0 = struct.unpack_from('>I', raw, 0)[0]
u32_be_4 = struct.unpack_from('>I', raw, 4)[0]
u32_le_0 = struct.unpack_from('<I', raw, 0)[0]
u32_le_4 = struct.unpack_from('<I', raw, 4)[0]
print(f'  BE uint32 at 0: {u32_be_0}')
print(f'  BE uint32 at 4: {u32_be_4}')
print(f'  LE uint32 at 0: {u32_le_0}')
print(f'  LE uint32 at 4: {u32_le_4}')

print()
print('=== Last 60 bytes ===')
tail = raw[-60:]
for i in range(0, len(tail), 16):
    chunk = tail[i:i+16]
    offset = len(raw) - 60 + i
    asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f'  {offset:5d}: {chunk.hex()}  |{asc_part}|')

print()
print('=== XML / string search ===')
for marker in [b'<?xml', b'<License', b'<license', b'BUDS', b'BRP', b'email', b'serial']:
    idx = raw.find(marker)
    print(f'  {marker}: found at {idx}' if idx >= 0 else f'  {marker}: NOT FOUND')

print()
print('=== PKCS1 padding markers (0x00 0x02) in any block ===')
block_size = 256
total_blocks = len(raw) // block_size
remainder = len(raw) % block_size
print(f'  Total 256-byte blocks: {total_blocks}  remainder: {remainder} bytes')
for i in range(min(total_blocks, 47)):
    block = raw[i*block_size:(i+1)*block_size]
    if block[0] == 0x00 and block[1] == 0x02:
        print(f'  Block {i:2d}: PKCS1v1.5 public-op marker (0x00 0x02 ...) ← encrypted by server public key')
    elif block[0] == 0x00 and block[1] == 0x01:
        print(f'  Block {i:2d}: PKCS1v1.5 signature marker (0x00 0x01 ...)')
    else:
        print(f'  Block {i:2d}: first 2 bytes = {block[0]:02x} {block[1]:02x}')

# Try to see if any block starts after a known header
print()
print('=== Try skipping possible headers ===')
for skip in [0, 4, 8, 12, 16, 32, 44]:
    remaining = raw[skip:]
    if len(remaining) % 256 == 0:
        print(f'  Skip {skip}: {len(remaining)} bytes = EXACTLY {len(remaining)//256} * 256 blocks!')
    else:
        blocks, rem = divmod(len(remaining), 256)
        print(f'  Skip {skip}: {len(remaining)} bytes = {blocks} blocks + {rem} bytes extra')
