"""
revert_patch.py — Reverte o bypass de licença BUDS2 restaurando os JARs originais.
Execute como Administrador.
"""
import os, shutil

BUDS2_PLUGINS = r'C:\Program Files (x86)\BRP\BUDS2\plugins'

JARS = [
    'com.kpit.license_2.0.5.201710302306.jar',
    'com.kpit.license.auth_2.0.5.201710302306.jar',
]

for jar in JARS:
    src = os.path.join(BUDS2_PLUGINS, jar)
    bak = src + '.original_backup'
    if os.path.isfile(bak):
        shutil.copy2(bak, src)
        print(f'[✓] Restaurado: {jar}')
    else:
        print(f'[!] Backup não encontrado: {bak}')
