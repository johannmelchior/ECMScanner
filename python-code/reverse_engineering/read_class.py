"""
read_class.py — Lê string constants e bytecode de arquivos .class Java
para encontrar métodos de validação de licença a serem patcheados.
"""
import struct
import sys
import os

def read_utf8(data, pos):
    length = struct.unpack_from('>H', data, pos)[0]
    s = data[pos+2:pos+2+length]
    try:
        return s.decode('utf-8'), pos + 2 + length
    except:
        return s.decode('latin-1'), pos + 2 + length

def parse_constant_pool(data, pos, count):
    cp = [None]  # index 0 unused
    i = 1
    while i < count:
        tag = data[pos]; pos += 1
        if tag == 1:   # Utf8
            s, pos = read_utf8(data, pos)
            cp.append(('Utf8', s))
        elif tag == 3:  # Integer
            v = struct.unpack_from('>i', data, pos)[0]; pos += 4
            cp.append(('Integer', v))
        elif tag == 4:  # Float
            v = struct.unpack_from('>f', data, pos)[0]; pos += 4
            cp.append(('Float', v))
        elif tag == 5:  # Long
            v = struct.unpack_from('>q', data, pos)[0]; pos += 8
            cp.append(('Long', v)); cp.append(None); i += 1
        elif tag == 6:  # Double
            v = struct.unpack_from('>d', data, pos)[0]; pos += 8
            cp.append(('Double', v)); cp.append(None); i += 1
        elif tag == 7:  # Class
            idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
            cp.append(('Class', idx))
        elif tag == 8:  # String
            idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
            cp.append(('String', idx))
        elif tag == 9:  # Fieldref
            a, b = struct.unpack_from('>HH', data, pos); pos += 4
            cp.append(('Fieldref', a, b))
        elif tag == 10:  # Methodref
            a, b = struct.unpack_from('>HH', data, pos); pos += 4
            cp.append(('Methodref', a, b))
        elif tag == 11:  # InterfaceMethodref
            a, b = struct.unpack_from('>HH', data, pos); pos += 4
            cp.append(('IfaceMethodref', a, b))
        elif tag == 12:  # NameAndType
            a, b = struct.unpack_from('>HH', data, pos); pos += 4
            cp.append(('NameAndType', a, b))
        elif tag == 15:  # MethodHandle
            pos += 3; cp.append(('MethodHandle',))
        elif tag == 16:  # MethodType
            pos += 2; cp.append(('MethodType',))
        elif tag == 18:  # InvokeDynamic
            pos += 4; cp.append(('InvokeDynamic',))
        else:
            print(f'  Unknown tag {tag} at pos {pos-1}')
            cp.append(('Unknown',))
        i += 1
    return cp, pos

def analyze_class(path):
    with open(path, 'rb') as f:
        data = f.read()
    
    magic = struct.unpack_from('>I', data, 0)[0]
    if magic != 0xCAFEBABE:
        print(f'  Not a class file: {path}')
        return
    
    minor, major = struct.unpack_from('>HH', data, 4)
    cp_count = struct.unpack_from('>H', data, 8)[0]
    
    cp, pos = parse_constant_pool(data, 10, cp_count)
    
    # access flags, this class, super class
    access, this_idx, super_idx = struct.unpack_from('>HHH', data, pos)
    pos += 6
    
    class_name = ''
    if cp[this_idx][0] == 'Class':
        name_idx = cp[this_idx][1]
        class_name = cp[name_idx][1]
    
    print(f'\n{"="*60}')
    print(f'Class: {class_name}  (Java {major-44})')
    
    # Print string constants
    strings = [(i, cp[i][1]) for i in range(1, len(cp)) if cp[i] and cp[i][0] == 'Utf8']
    interesting = [(i, s) for i, s in strings if any(kw in s.lower() for kw in
        ['valid', 'licens', 'invalid', 'expir', 'error', 'ok', 'deny', 'grant', 'hardware', 'decrypt', 'verify', 'check'])]
    if interesting:
        print(f'  Interesting strings:')
        for i, s in interesting[:30]:
            print(f'    [{i:3d}] {s!r}')
    
    # Interfaces count
    icount = struct.unpack_from('>H', data, pos)[0]; pos += 2 + 2 * icount
    
    # Fields
    fcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    for _ in range(fcount):
        pos += 6  # access, name_idx, desc_idx
        attr_count = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for __ in range(attr_count):
            name_idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
            attr_len = struct.unpack_from('>I', data, pos)[0]; pos += 4 + attr_len
    
    # Methods
    mcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    print(f'  Methods ({mcount}):')
    for m in range(mcount):
        mflags, mname_idx, mdesc_idx = struct.unpack_from('>HHH', data, pos); pos += 6
        mname = cp[mname_idx][1] if mname_idx < len(cp) and cp[mname_idx] else ''
        mdesc = cp[mdesc_idx][1] if mdesc_idx < len(cp) and cp[mdesc_idx] else ''
        
        method_bytecode = None
        method_code_pos = None
        method_code_len = None
        
        attr_count = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for a in range(attr_count):
            aname_idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
            alen = struct.unpack_from('>I', data, pos)[0]; pos += 4
            aname = cp[aname_idx][1] if aname_idx < len(cp) and cp[aname_idx] else ''
            if aname == 'Code':
                # max_stack(2) + max_locals(2) + code_len(4) + code
                code_len = struct.unpack_from('>I', data, pos + 4)[0]
                code_start = pos + 8
                method_bytecode = data[code_start:code_start + code_len]
                method_code_pos = code_start  # absolute position in file
                method_code_len = code_len
                pos += alen
            else:
                pos += alen
        
        flags_str = ''
        if mflags & 0x0001: flags_str += 'public '
        if mflags & 0x0002: flags_str += 'private '
        if mflags & 0x0008: flags_str += 'static '
        
        print(f'    {flags_str}{mname}{mdesc}')
        if method_bytecode and method_code_pos:
            # Show first few opcodes
            opcodes = method_bytecode[:20].hex()
            print(f'      code_pos={method_code_pos:#010x}  len={method_code_len}  bytes: {opcodes}')
            
            # Check if it returns boolean/enum
            if 'Z)' in mdesc or 'Validity' in mdesc or 'boolean' in mdesc.lower():
                print(f'      *** INTERESTING RETURN TYPE ***')
    
    return cp, class_name


base = r'C:\Users\johan\Documents\projetoCAN\temp_jar_extract\kpit_license'
targets = [
    'com/kpit/license/licenseservice/LocalLicenseServiceImpl.class',
    'com/kpit/license/LicenseManagerImpl.class',
    'com/kpit/license/Validity.class',
    'com/kpit/license/decryption/DecryptionServiceImpl.class',
    'com/kpit/license/utils/LicenseHandler.class',
    'com/kpit/license/verification/SystemVerificationService.class',
]

for t in targets:
    path = os.path.join(base, t)
    if os.path.exists(path):
        analyze_class(path)
    else:
        print(f'\nNOT FOUND: {t}')
