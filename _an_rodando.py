import math
from collections import Counter, defaultdict
from statistics import mean

import sys
path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\johan\Documents\projetoCAN\yamaha rodando.txt"
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

header = {}
data = []
for ln in lines:
    s = ln.strip()
    if not s:
        continue
    if s.startswith('#'):
        body = s[1:]
        if '=' in body:
            k,v = body.split('=',1)
            header[k.strip().upper()] = v.strip()
        continue
    try:
        data.append(float(s))
    except:
        pass

N = len(data)
clock_raw = header.get('CLOCK','20.0 S')
clock_s = float(clock_raw.split()[0])
dt_us = (clock_s * 1_000_000.0) / N
vmin, vmax = min(data), max(data)
th = (vmin + vmax) / 2.0

bits = [1 if x > th else 0 for x in data]

cross = []
for i in range(N-1):
    if bits[i] != bits[i+1]:
        cross.append(i)

print('PARSE')
print('N',N,'CLOCK',clock_raw,'dt_us',dt_us,'vmin',vmin,'vmax',vmax,'th',th)
print('crossings',len(cross))
print('first20_cross_idx',cross[:20])
if len(cross) > 1:
    ints = [ (cross[i+1]-cross[i]) * dt_us for i in range(min(20,len(cross)-1))]
    print('first20_cross_intervals_us',[round(x,2) for x in ints])

def decode_for(baud, phase, polarity):
    # polarity 0: idle-high start 1->0 ; polarity 1: inverted idle-low start 0->1
    b = bits
    if polarity == 1:
        b = [1-x for x in bits]
    spb = (1_000_000.0 / baud) / dt_us
    attempts = 0
    valid = 0
    out = []
    i = 0
    minlen = int(spb * 11) + 2
    while i < len(b)-minlen:
        if b[i] == 1 and b[i+1] == 0:
            attempts += 1
            ok = True
            val = 0
            for bit in range(8):
                idx = int(i + (phase + 1 + bit) * spb)
                if idx >= len(b):
                    ok = False
                    break
                if b[idx]:
                    val |= (1 << bit)
            stop_idx = int(i + (phase + 9) * spb)
            if ok and stop_idx < len(b) and b[stop_idx] == 1:
                valid += 1
                t_us = i * dt_us
                out.append((t_us, val))
                i = int(i + spb * 10)
                continue
        i += 1
    ratio = (valid / attempts) if attempts else 0.0
    return {'baud':baud,'phase':phase,'pol':polarity,'attempts':attempts,'valid':valid,'ratio':ratio,'decoded':len(out),'out':out}

cfgs=[]
for baud in [16040, 16064, 16368, 15625, 15873, 10400, 9600]:
    p=0.15
    while p <= 0.850001:
        cfgs.append(decode_for(baud,p,0))
        cfgs.append(decode_for(baud,p,1))
        p += 0.02

cfgs_sorted = sorted(cfgs, key=lambda c:(c['ratio'], c['decoded']), reverse=True)
print('\nTOP15')
for c in cfgs_sorted[:15]:
    pol = 'idle-high' if c['pol']==0 else 'idle-low(inv)'
    print(c['baud'], round(c['phase'],2), pol, 'attempts',c['attempts'],'valid',c['valid'],'ratio',round(c['ratio'],6),'decoded',c['decoded'])

best = cfgs_sorted[0]
stream = best['out']
print('\nBEST',best['baud'],round(best['phase'],2),('idle-high' if best['pol']==0 else 'idle-low(inv)'),'decoded',len(stream))
if stream:
    print('span_ms',round(stream[0][0]/1000,3),'->',round(stream[-1][0]/1000,3))

# frame split
frames=[]
cur=[]
last=None
gap_thr_us=2500.0
for t,bv in stream:
    if last is not None and (t-last) > gap_thr_us:
        if cur:
            frames.append(cur)
        cur=[]
    cur.append((t,bv))
    last=t
if cur:
    frames.append(cur)

hist = Counter(len(fr) for fr in frames)
print('\nFRAME_HIST', dict(sorted(hist.items())))

# top exact frames length 1..8
bylen = defaultdict(Counter)
for fr in frames:
    L=len(fr)
    if 1 <= L <= 8:
        seq = tuple(x[1] for x in fr)
        bylen[L][seq]+=1

for L in range(1,9):
    print(f'\nTOP_EXACT_LEN_{L}')
    for seq,cnt in bylen[L].most_common(10):
        print(cnt, ' '.join(f'{x:02X}' for x in seq))

# ngrams n2..6 continuous
bytes_only=[b for _,b in stream]
for n in range(2,7):
    c=Counter()
    for i in range(0, max(0,len(bytes_only)-n+1)):
        c[tuple(bytes_only[i:i+n])] += 1
    print(f'\nTOP_NGRAM_{n}')
    for seq,cnt in c.most_common(20):
        print(cnt, ' '.join(f'{x:02X}' for x in seq))

# motifs 1-byte -> 4..7-byte within 3..12ms
mot=Counter()
for i in range(len(frames)-1):
    a=frames[i]
    b=frames[i+1]
    if len(a)==1 and 4 <= len(b) <= 7:
        gap_ms = (b[0][0] - a[-1][0]) / 1000.0
        if 3.0 <= gap_ms <= 12.0:
            mot[(tuple(x[1] for x in a), tuple(x[1] for x in b))]+=1
print('\nMOTIFS')
for (a,b),cnt in mot.most_common(20):
    print(cnt, '|', ' '.join(f'{x:02X}' for x in a), '->', ' '.join(f'{x:02X}' for x in b))

# checksums
f5=[tuple(x[1] for x in fr) for fr in frames if len(fr)==5]
f6=[tuple(x[1] for x in fr) for fr in frames if len(fr)==6]
pass5=sum(1 for s in f5 if ((sum(s[:4]) & 0xFF) == s[4]))
pass6=sum(1 for s in f6 if ((sum(s[:5]) & 0xFF) == s[5]))
print('\nCHECKSUM')
print('5byte',pass5,'/',len(f5), 'ratio', round((pass5/len(f5)) if f5 else 0,6))
print('6byte',pass6,'/',len(f6), 'ratio', round((pass6/len(f6)) if f6 else 0,6))

# first 120 frames
print('\nFIRST120')
for idx,fr in enumerate(frames[:120], start=1):
    t0=fr[0][0]/1000.0
    gap=0.0
    if idx>1:
        prev=frames[idx-2]
        gap=(fr[0][0]-prev[-1][0])/1000.0
    print(f"[{idx:03d}] t={t0:.3f}ms gap={gap:.3f}ms len={len(fr)} :: " + ' '.join(f'{x[1]:02X}' for x in fr))
