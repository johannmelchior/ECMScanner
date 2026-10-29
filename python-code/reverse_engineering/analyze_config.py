import struct, os

def get_strings_from_class(fpath):
    with open(fpath, 'rb') as f:
        data = f.read()
    cp_count = struct.unpack_from('>H', data, 8)[0]
    cp = []; pos = 10; i = 1
    while i < cp_count:
        tag = data[pos]; pos += 1
        if tag == 1:
            l = struct.unpack_from('>H', data, pos)[0]
            s = data[pos+2:pos+2+l].decode('utf-8','replace')
            cp.append(s)
            pos += 2+l
        elif tag in (5,6): pos+=8; cp.append(''); cp.append(''); i+=1
        elif tag in (3,4,9,10,11,12,18): pos+=4; cp.append('')
        elif tag in (7,8,16): pos+=2; cp.append('')
        elif tag==15: pos+=3; cp.append('')
        else: cp.append('')
        i+=1
    return [s for s in cp if s and len(s)>3]

secdir = r'C:\Users\johan\Documents\projetoCAN\temp_jar_extract\equinox_sec'

for cls in ['ConfigurationFederator', 'ConfigurationFactory']:
    fpath = os.path.join(secdir, 'org', 'eclipse', 'equinox', 'internal', 'security', 'auth', cls+'.class')
    if os.path.isfile(fpath):
        print(f'=== {cls} ===')
        for s in get_strings_from_class(fpath):
            if 'login' in s.lower() or 'jaas' in s.lower() or 'module' in s.lower() or 'config' in s.lower() or 'extension' in s.lower():
                print(' ', repr(s))
        print()
