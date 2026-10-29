"""Analyze EMFFromSecXMLDataSource and other key in2soft classes."""
import struct, os, sys

# reuse core functions from read_class without importing the module-level code
def read_utf8(data, pos):
    length = struct.unpack_from('>H', data, pos)[0]
    raw = data[pos+2:pos+2+length]
    try:    return raw.decode('utf-8'), pos + 2 + length
    except: return raw.decode('latin-1'), pos + 2 + length

def parse_constant_pool(data, pos, count):
    cp = [None]
    i = 1
    while i < count:
        tag = data[pos]; pos += 1
        if   tag ==  1: s, pos = read_utf8(data, pos); cp.append(('Utf8', s))
        elif tag ==  3: v=struct.unpack_from('>i',data,pos)[0]; pos+=4; cp.append(('Integer',v))
        elif tag ==  4: v=struct.unpack_from('>f',data,pos)[0]; pos+=4; cp.append(('Float',v))
        elif tag ==  5: v=struct.unpack_from('>q',data,pos)[0]; pos+=8; cp.append(('Long',v));   cp.append(None); i+=1
        elif tag ==  6: v=struct.unpack_from('>d',data,pos)[0]; pos+=8; cp.append(('Double',v)); cp.append(None); i+=1
        elif tag ==  7: idx=struct.unpack_from('>H',data,pos)[0]; pos+=2; cp.append(('Class',idx))
        elif tag ==  8: idx=struct.unpack_from('>H',data,pos)[0]; pos+=2; cp.append(('String',idx))
        elif tag in (9,10,11,12): a,b=struct.unpack_from('>HH',data,pos); pos+=4; cp.append((tag, a, b))
        elif tag == 15: pos+=3; cp.append(('MH',))
        elif tag == 16: pos+=2; cp.append(('MT',))
        elif tag == 18: pos+=4; cp.append(('ID',))
        else: raise ValueError(f'Unknown tag {tag}')
        i += 1
    return cp, pos

def analyze(path):
    with open(path, 'rb') as f:
        data = f.read()
    if struct.unpack_from('>I', data, 0)[0] != 0xCAFEBABE:
        print('Not a class file'); return

    cp_count = struct.unpack_from('>H', data, 8)[0]
    cp, pos = parse_constant_pool(data, 10, cp_count)

    access, this_idx, super_idx = struct.unpack_from('>HHH', data, pos); pos += 6
    class_name = cp[cp[this_idx][1]][1] if cp[this_idx] else '?'

    print(f'\n{"="*60}')
    print(f'Class: {class_name}')
    all_utf8 = [(i, cp[i][1]) for i in range(1, len(cp)) if cp[i] and cp[i][0] == 'Utf8']
    print('  All strings (first 80):')
    for i, s in all_utf8[:80]:
        print(f'    [{i:3d}] {s!r}')

    # Skip interfaces, fields
    icount = struct.unpack_from('>H', data, pos)[0]; pos += 2 + 2 * icount
    fcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    for _ in range(fcount):
        pos += 6
        ac = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for __ in range(ac):
            pos += 2; pos += 4 + struct.unpack_from('>I', data, pos)[0] + 4; pos -= 4  # fix: read correctly
    # Fix field skipping
    # Re-do properly
    return cp, class_name, data

targets = [
    r'temp_jar_extract\in2soft_model\com\in2soft\licensemanager\converter\EMFFromSecXMLDataSource.class',
    r'temp_jar_extract\in2soft_model\com\in2soft\licensemanager\v002\GrantedLicenses.class',
]

for t in targets:
    if os.path.exists(t):
        with open(t, 'rb') as f:
            data = f.read()
        cp_count = struct.unpack_from('>H', data, 8)[0]
        cp, pos = parse_constant_pool(data, 10, cp_count)
        all_utf8 = [(i, cp[i][1]) for i in range(1, len(cp)) if cp[i] and cp[i][0] == 'Utf8']
        pclass_idx = struct.unpack_from('>H', data, pos)[0]
        class_name = cp[cp[pclass_idx][1]][1] if cp[pclass_idx] else '?'
        print(f'\n{"="*60}')
        print(f'Class: {class_name}')
        print(f'  Strings:')
        for i, s in all_utf8:
            print(f'    [{i:3d}] {s!r}')
    else:
        print(f'NOT FOUND: {t}')
