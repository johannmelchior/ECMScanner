import zipfile, os
from collections import Counter

ptx = r'C:\Program Files (x86)\BRP\BUDS2\OTXData\DiagApi_25.13.0.ptx'

with zipfile.ZipFile(ptx, 'r') as z:
    names = z.namelist()
    print(f'Total de arquivos no .ptx: {len(names)}')

    exts = Counter(os.path.splitext(n)[1] for n in names)
    for ext, count in sorted(exts.items(), key=lambda x: -x[1]):
        label = ext if ext else '(sem extensao)'
        print(f'  {label}: {count} arquivos')
    print()

    otx_files = [n for n in names if n.endswith('.otx')]
    print(f'Arquivos .otx ({len(otx_files)}):')
    for n in sorted(otx_files)[:40]:
        info = z.getinfo(n)
        print(f'  {n}  ({info.file_size} bytes)')

    # Lê o Api.otx para entender estrutura
    print()
    print('=== Trecho de Api.otx ===')
    content = z.read('src/com/diagnostics/Api.otx').decode('utf-8', errors='replace')
    print(content[:2000])
