files = [
    r'\\JOHANN\Documents\projetoCAN\yamaha vx 110 inicializacao painel ecm.txt',
    r'\\JOHANN\Documents\projetoCAN\yamaha vx 110 motor parado.txt',
]
for f in files:
    fname = f.split('\\')[-1]
    print('=== ' + fname + ' ===')
    header = {}
    n = 0
    with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
        for ln in fh:
            s = ln.strip()
            if s.startswith('#'):
                body = s[1:]
                if '=' in body:
                    k,v = body.split('=',1)
                    header[k.strip().upper()] = v.strip()
            elif s:
                n += 1
    clock_raw = header.get('CLOCK','2.0 S')
    clock_s = float(clock_raw.split()[0])
    fs = n / clock_s
    dt = clock_s * 1e6 / n
    print('  N=%d  CLOCK=%s  Fs=%.0fHz  dt=%.3fus' % (n, clock_raw, fs, dt))
    print('  Header:', header)
    print()
