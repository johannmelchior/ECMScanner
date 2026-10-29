import struct, sys

def read_class(path):
    with open(path, 'rb') as f:
        return bytearray(f.read())

def read_cp(data, pos):
    count = struct.unpack_from('>H', data, pos)[0]
    pos += 2
    cp = [None]
    cp_tags = [0]
    i = 1
    while i < count:
        tag = data[pos]; pos += 1
        cp_tags.append(tag)
        if tag == 1:
            ln = struct.unpack_from('>H', data, pos)[0]; pos += 2
            cp.append(data[pos:pos+ln].decode('utf-8', errors='replace')); pos += ln
        elif tag in (7, 8, 16, 19, 20):
            cp.append(struct.unpack_from('>H', data, pos)[0]); pos += 2
        elif tag in (3, 4):
            cp.append(struct.unpack_from('>I', data, pos)[0]); pos += 4
        elif tag in (9, 10, 11, 12, 17, 18):
            a = struct.unpack_from('>HH', data, pos)
            cp.append((a[0], a[1])); pos += 4
        elif tag in (5, 6):
            cp.append(struct.unpack_from('>Q', data, pos)[0]); pos += 8
            cp.append(None); cp_tags.append(0); i += 1
        elif tag == 15:
            cp.append((data[pos], struct.unpack_from('>H', data, pos+1)[0])); pos += 3
        else:
            print(f'Unknown tag {tag}'); break
        i += 1
    return cp, cp_tags, pos

def resolve(cp, cp_tags, idx):
    if idx >= len(cp): return f'?{idx}'
    tag = cp_tags[idx]
    val = cp[idx]
    if tag == 1: return val
    if tag == 7: return resolve(cp, cp_tags, val)
    if tag == 8: return 'STR(' + resolve(cp, cp_tags, val) + ')'
    if tag == 12:
        return resolve(cp, cp_tags, val[0]) + ':' + resolve(cp, cp_tags, val[1])
    if tag in (9, 10, 11):
        return resolve(cp, cp_tags, val[0]) + '.' + resolve(cp, cp_tags, val[1])
    return str(val)

def disasm(data, cp, cp_tags, pos, code_len):
    code = data[pos:pos+code_len]
    i = 0
    while i < len(code):
        op = code[i]
        s = f'  {i:4d}: '
        if op == 0x00: s += 'nop'
        elif op == 0x01: s += 'aconst_null'
        elif op == 0x02: s += 'iconst_m1'
        elif op == 0x03: s += 'iconst_0'
        elif op == 0x04: s += 'iconst_1'
        elif op == 0x05: s += 'iconst_2'
        elif op == 0x06: s += 'iconst_3'
        elif op == 0x10: s += f'bipush {code[i+1]}'; i += 1
        elif op == 0x11: v = struct.unpack_from('>h', code, i+1)[0]; s += f'sipush {v}'; i += 2
        elif op == 0x12: s += f'ldc #{code[i+1]} = {resolve(cp,cp_tags,code[i+1])}'; i += 1
        elif op == 0x13: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'ldc_w #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0x15: s += f'iload {code[i+1]}'; i += 1
        elif op == 0x19: s += f'aload {code[i+1]}'; i += 1
        elif op in range(0x1a, 0x1e): s += f'iload_{op-0x1a}'
        elif op in range(0x2a, 0x2e): s += f'aload_{op-0x2a}'
        elif op == 0x32: s += 'aaload'
        elif op in range(0x3b, 0x3f): s += f'istore_{op-0x3b}'
        elif op in range(0x4b, 0x4f): s += f'astore_{op-0x4b}'
        elif op == 0x3a: s += f'astore {code[i+1]}'; i += 1
        elif op == 0x36: s += f'istore {code[i+1]}'; i += 1
        elif op == 0x57: s += 'pop'
        elif op == 0x59: s += 'dup'
        elif op == 0x87: s += 'i2d'
        elif op == 0x91: s += 'i2b'
        elif op == 0x99: off = struct.unpack_from('>h', code, i+1)[0]; s += f'ifeq {i+off}'; i += 2
        elif op == 0x9a: off = struct.unpack_from('>h', code, i+1)[0]; s += f'ifne {i+off}'; i += 2
        elif op == 0x9b: off = struct.unpack_from('>h', code, i+1)[0]; s += f'iflt {i+off}'; i += 2
        elif op == 0x9c: off = struct.unpack_from('>h', code, i+1)[0]; s += f'ifge {i+off}'; i += 2
        elif op == 0x9d: off = struct.unpack_from('>h', code, i+1)[0]; s += f'ifgt {i+off}'; i += 2
        elif op == 0x9e: off = struct.unpack_from('>h', code, i+1)[0]; s += f'ifle {i+off}'; i += 2
        elif op == 0x9f: off = struct.unpack_from('>h', code, i+1)[0]; s += f'if_icmpeq {i+off}'; i += 2
        elif op == 0xa0: off = struct.unpack_from('>h', code, i+1)[0]; s += f'if_icmpne {i+off}'; i += 2
        elif op == 0xa5: off = struct.unpack_from('>h', code, i+1)[0]; s += f'if_acmpeq {i+off}'; i += 2
        elif op == 0xa6: off = struct.unpack_from('>h', code, i+1)[0]; s += f'if_acmpne {i+off}'; i += 2
        elif op == 0xa7: off = struct.unpack_from('>h', code, i+1)[0]; s += f'goto {i+off}'; i += 2
        elif op == 0xac: s += 'ireturn'
        elif op == 0xad: s += 'lreturn'
        elif op == 0xb0: s += 'areturn'
        elif op == 0xb1: s += 'return'
        elif op == 0xb2: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'getstatic #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xb3: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'putstatic #{idx}'; i += 2
        elif op == 0xb4: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'getfield #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xb5: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'putfield #{idx}'; i += 2
        elif op == 0xb6: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'invokevirtual #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xb7: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'invokespecial #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xb8: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'invokestatic #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xb9: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'invokeinterface #{idx} = {resolve(cp,cp_tags,idx)}'; i += 4
        elif op == 0xbb: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'new #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xbd: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'anewarray #{idx}'; i += 2
        elif op == 0xbe: s += 'arraylength'
        elif op == 0xbf: s += 'athrow'
        elif op == 0xc0: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'checkcast #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xc1: idx = struct.unpack_from('>H', code, i+1)[0]; s += f'instanceof #{idx} = {resolve(cp,cp_tags,idx)}'; i += 2
        elif op == 0xc6: off = struct.unpack_from('>h', code, i+1)[0]; s += f'ifnull {i+off}'; i += 2
        elif op == 0xc7: off = struct.unpack_from('>h', code, i+1)[0]; s += f'ifnonnull {i+off}'; i += 2
        else: s += f'??? op=0x{op:02x}'
        print(s)
        i += 1

def analyze_class(path, target_methods=None):
    data = read_class(path)
    pos = 8
    cp, cp_tags, pos = read_cp(data, pos)
    pos += 6
    icount = struct.unpack_from('>H', data, pos)[0]; pos += 2 + icount * 2
    fcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    for _ in range(fcount):
        pos += 6
        ac = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for _ in range(ac):
            pos += 2; al = struct.unpack_from('>I', data, pos)[0]; pos += 4 + al
    mcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    for _ in range(mcount):
        aflags = struct.unpack_from('>H', data, pos)[0]; pos += 2
        name_idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
        desc_idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
        name = resolve(cp, cp_tags, name_idx)
        desc = resolve(cp, cp_tags, desc_idx)
        ac = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for _ in range(ac):
            attr_name_idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
            al = struct.unpack_from('>I', data, pos)[0]; pos += 4
            attr_name = resolve(cp, cp_tags, attr_name_idx)
            if attr_name == 'Code':
                max_s, max_l = struct.unpack_from('>HH', data, pos)
                code_len = struct.unpack_from('>I', data, pos+4)[0]
                if target_methods is None or name in target_methods:
                    print(f'\n=== {name}{desc}  code_len={code_len} max_stack={max_s} max_locals={max_l} ===')
                    disasm(data, cp, cp_tags, pos+8, code_len)
            pos += al
    return cp, cp_tags

if __name__ == '__main__':
    base = r'C:\Users\johan\Documents\projetoCAN\temp_jar_extract'

    # Dump entire constant pool of PreferencesManager
    path = base + r'\diagfw\com\kpit\diagfw\application\preferences\PreferencesManager.class'
    data = read_class(path)
    pos = 8
    cp, cp_tags, pos = read_cp(data, pos)
    
    print('=== PreferencesManager Constant Pool ===')
    for i in range(1, len(cp)):
        tag = cp_tags[i]
        tag_names = {1:'Utf8', 3:'Int', 4:'Float', 5:'Long', 6:'Double',
                     7:'Class', 8:'String', 9:'Fieldref', 10:'Methodref',
                     11:'InterfaceMethodref', 12:'NameAndType', 15:'MethodHandle',
                     16:'MethodType', 17:'Dynamic', 18:'InvokeDynamic',
                     19:'Module', 20:'Package'}
        tn = tag_names.get(tag, f'?{tag}')
        val = cp[i]
        if tag == 8:  # String constant - these can be used with ldc
            s = resolve(cp, cp_tags, val)
            print(f'  #{i:3d} [{tn:20s}] → {s}  *** LDC-USABLE ***')
        elif tag == 1:  # Utf8
            print(f'  #{i:3d} [{tn:20s}] = {repr(val)}')
        elif tag == 7:  # Class
            print(f'  #{i:3d} [{tn:20s}] → {resolve(cp, cp_tags, i)}')
        elif tag in (9,10,11):
            print(f'  #{i:3d} [{tn:20s}] → {resolve(cp, cp_tags, i)}')
        elif tag == 12:
            print(f'  #{i:3d} [{tn:20s}] → {resolve(cp, cp_tags, val[0])}:{resolve(cp, cp_tags, val[1])}')
        elif val is not None:
            print(f'  #{i:3d} [{tn:20s}] = {val}')
    
    # Also show what CP entries are used in getStoreQualifier
    print('\n=== getStoreQualifier CP refs: #58, #63, #67 ===')
    for i in [58, 63, 67]:
        if i < len(cp):
            print(f'  #{i}: tag={cp_tags[i]}, val={cp[i]}, resolved={resolve(cp, cp_tags, i)}')
