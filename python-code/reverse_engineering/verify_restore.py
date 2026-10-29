import zipfile, struct, hashlib, os

plugins = r'C:\Program Files (x86)\BRP\BUDS2\plugins'
jars = [
    ('com.kpit.diagfw.application_1.7.121.jar', 'com/kpit/diagfw/application/login/oauth/LoginBrowser.class'),
    ('com.kpit.diagfw.application.oauth.brp_1.0.4.jar', 'com/kpit/diagfw/application/login/oauth/OAuthLoginModule.class'),
    ('com.kpit.diagfw.diagnosticapi_1.0.94.jar', 'com/kpit/diagfw/diagnosticapi/otx/DiagnosticApiOtx.class'),
]
for jar, cls in jars:
    cls_name = cls.split("/")[-1]
    for suffix, label in [('', 'current'), ('.original_backup', 'backup')]:
        path = os.path.join(plugins, jar + suffix)
        with zipfile.ZipFile(path) as z:
            data = z.read(cls)
        v = struct.unpack_from('>H', data, 6)[0]
        md5 = hashlib.md5(data).hexdigest()
        print(f'{jar} [{label}] {cls_name}: v{v}, md5={md5}')
    with open(os.path.join(plugins, jar), 'rb') as f:
        cur = hashlib.md5(f.read()).hexdigest()
    with open(os.path.join(plugins, jar+'.original_backup'), 'rb') as f:
        bak = hashlib.md5(f.read()).hexdigest()
    match = 'MATCH' if cur == bak else 'DIFFER'
    print(f'  JAR MD5 {match}: cur={cur[:12]} bak={bak[:12]}')
    print()
