import struct, os, zipfile

def get_strings_from_class_file(data):
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
    return cp

# Look at appfw ApplicationWorkbenchAdvisor for security login building
plugins = r'C:\Program Files (x86)\BRP\BUDS2\plugins'
jar = os.path.join(plugins, 'com.kpit.appfw_1.0.5.201809031018.jar')

with zipfile.ZipFile(jar) as z:
    for cls in z.namelist():
        if cls.endswith('.class'):
            data = z.read(cls)
            cp = get_strings_from_class_file(data)
            # Look for security/login related strings
            interesting = [s for s in cp if s and ('security' in s.lower() or 'jaas' in s.lower() or 
                          'loginmodule' in s.lower() or 'ExtensionLogin' in s or
                          'getSubject' in s or 'appConfigEntry' in s.lower() or
                          'AppConfigurationEntry' in s)]
            if interesting:
                print(f'=== {cls} ===')
                for s in interesting:
                    print(f'  {repr(s)}')
                print()

# Also check com.kpit.appfw.security or similar
for jar_name in os.listdir(plugins):
    if jar_name.endswith('.jar') and 'appfw' in jar_name.lower():
        jar_path = os.path.join(plugins, jar_name)
        try:
            with zipfile.ZipFile(jar_path) as z:
                for cls in z.namelist():
                    if cls.endswith('.class'):
                        data = z.read(cls)
                        cp = get_strings_from_class_file(data)
                        if any('AppConfigurationEntry' in s for s in cp if s):
                            print(f'FOUND AppConfigurationEntry in: {jar_name} :: {cls}')
        except: pass
