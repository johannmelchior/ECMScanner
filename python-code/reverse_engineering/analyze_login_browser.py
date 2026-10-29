"""Find methods in diagfw application login classes."""
import zipfile, struct

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
        else: raise ValueError(f'Unknown tag {tag} at pos {pos-1}')
        i+=1
    return cp, pos

def find_methods(data, class_file=''):
    cp_count = struct.unpack_from('>H', data, 8)[0]
    cp, pos = parse_cp(data, 10, cp_count)
    pclass_idx = struct.unpack_from('>H', data, pos)[0]
    class_name = cp[cp[pclass_idx][1]][1] if cp[pclass_idx] else '?'
    pos += 6
    icount = struct.unpack_from('>H', data, pos)[0]; pos += 2 + 2 * icount
    fcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    for _ in range(fcount):
        pos += 6
        ac = struct.unpack_from('>H', data, pos)[0]; pos += 2
        for __ in range(ac):
            pos += 2
            al = struct.unpack_from('>I', data, pos)[0]; pos += 4 + al

    # also collect all string constants for context
    all_strings = [(i, cp[i][1]) for i in range(1, len(cp)) if cp[i] and cp[i][0] == 'Utf8']

    print(f'\n{"="*60}')
    print(f'Class: {class_name}  [{class_file}]')
    interesting = [(i,s) for i,s in all_strings if any(k in s.lower() for k in
        ['licens','login','valid','auth','dialog','error','message','install','grant','state','token'])]
    print('  Key strings:')
    for i, s in interesting[:20]:
        print(f'    [{i:3d}] {s!r}')

    mcount = struct.unpack_from('>H', data, pos)[0]; pos += 2
    print(f'  Methods ({mcount}):')
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
                print(f'    {mname}{mdesc}')
                print(f'      code@0x{code_start:08x} len={code_len} first={data[code_start:code_start+12].hex()}')
            pos += alen

jar = r'C:\Program Files (x86)\BRP\BUDS2\plugins\com.kpit.diagfw.application_1.7.121.jar'
targets = [
    'com/kpit/diagfw/application/login/oauth/LoginBrowser.class',
    'com/kpit/diagfw/application/handler/LicenseHandler.class',
]
with zipfile.ZipFile(jar) as z:
    for t in targets:
        try:
            find_methods(z.read(t), t)
        except Exception as e:
            print(f'\nERROR {t}: {e}')
