"""Find bytecode positions of methods in BUDS2 auth JAR classes."""
import struct, zipfile

def read_utf8(data, pos):
    l = struct.unpack_from('>H', data, pos)[0]
    raw = data[pos+2:pos+2+l]
    try:    return raw.decode('utf-8'), pos+2+l
    except: return raw.decode('latin-1'), pos+2+l

def parse_cp(data, pos, count):
    cp = [None]; i = 1
    while i < count:
        tag = data[pos]; pos += 1
        if   tag== 1: s,pos=read_utf8(data,pos); cp.append(('Utf8',s))
        elif tag in (3,4): pos+=4; cp.append((tag,))
        elif tag in (5,6): pos+=8; cp.append((tag,)); cp.append(None); i+=1
        elif tag in (7,8): idx=struct.unpack_from('>H',data,pos)[0]; pos+=2; cp.append((tag,idx))
        elif tag in (9,10,11,12): a,b=struct.unpack_from('>HH',data,pos); pos+=4; cp.append((tag,a,b))
        elif tag==15: pos+=3; cp.append((15,))
        elif tag==16: pos+=2; cp.append((16,))
        elif tag==18: pos+=4; cp.append((18,))
        else: raise ValueError(f'Unknown tag {tag}')
        i+=1
    return cp, pos

def find_methods(data, show_all=False):
    cp_count = struct.unpack_from('>H', data, 8)[0]
    cp, pos = parse_cp(data, 10, cp_count)

    pclass_idx = struct.unpack_from('>H', data, pos)[0]
    class_name = cp[cp[pclass_idx][1]][1] if cp[pclass_idx] else '?'
    pos += 6  # access, this, super

    icount = struct.unpack_from('>H', data, pos)[0]; pos += 2 + 2 * icount

    fcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    for _ in range(fcount):
        pos += 6
        ac = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for __ in range(ac):
            pos += 2
            al = struct.unpack_from('>I', data, pos)[0]; pos += 4 + al

    print(f'\nClass: {class_name}')
    mcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    for _ in range(mcount):
        mflags, mname_idx, mdesc_idx = struct.unpack_from('>HHH', data, pos); pos += 6
        mname = cp[mname_idx][1] if cp[mname_idx] else ''
        mdesc = cp[mdesc_idx][1] if cp[mdesc_idx] else ''

        ac = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for __ in range(ac):
            aname_idx = struct.unpack_from('>H', data, pos)[0]; pos += 2
            alen = struct.unpack_from('>I', data, pos)[0]; pos += 4
            aname = cp[aname_idx][1] if cp[aname_idx] else ''
            if aname == 'Code':
                code_len = struct.unpack_from('>I', data, pos+4)[0]
                code_start = pos + 8
                code_bytes = data[code_start:code_start+min(12, code_len)]
                if show_all or mname in ('login','commit','abort','initialize','isLoginPossible','attemptLogin','autoLogin'):
                    print(f'  {mname}{mdesc}')
                    print(f'    code_pos=0x{code_start:08x}  len={code_len}  bytes: {code_bytes.hex()}')
            pos += alen

jar = r'C:\Program Files (x86)\BRP\BUDS2\plugins\com.kpit.license.auth_2.0.5.201710302306.jar'
with zipfile.ZipFile(jar) as z:
    for cls in ['com/kpit/license/auth/LicenseLoginModule.class',
                'com/kpit/license/auth/LicenseAutoLoginModule.class']:
        try:
            find_methods(z.read(cls), show_all=True)
        except Exception as e:
            print(f'ERROR: {cls}: {e}')
