import re
from collections import Counter, defaultdict
from statistics import mean

PATH = 'yam.txt'
BAUD = 15625
HARD_SPLIT_MS = 2.5

with open(PATH, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.read().splitlines()

headers = {}
samples = []
for ln in lines:
    s = ln.strip()
    if not s:
        continue
    if s.startswith('#'):
        m = re.match(r'^#\s*([A-Za-z0-9_]+)\s*[:=]?\s*(.*)$', s)
        if m:
            headers[m.group(1).upper()] = m.group(2).strip()
        continue
    nums = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', s)
    if nums:
        samples.append(float(nums[-1]))

N = len(samples)
if N == 0:
    raise SystemExit('No numeric samples found in yam.txt')

def to_num(x):
    if x is None:
        return None
    m = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', x)
    return float(m.group(0)) if m else None

clock_raw = headers.get('CLOCK')
size_raw = headers.get('SIZE')
clock_val = to_num(clock_raw)
size_val = int(to_num(size_raw)) if to_num(size_raw) is not None else None

bit_time = 1.0 / BAUD

# derive dt from #CLOCK/#SIZE with heuristics
dt_candidates = []
if clock_val is not None:
    dt_candidates += [
        ('1/CLOCK (CLOCK as Hz)', 1.0/clock_val if clock_val != 0 else None),
        ('CLOCK seconds/sample', clock_val),
        ('CLOCK ns/sample', clock_val * 1e-9),
        ('CLOCK us/sample', clock_val * 1e-6),
        ('CLOCK total seconds / N', clock_val / N),
    ]

dt_candidates = [(name, dt) for name, dt in dt_candidates if dt and dt > 0]

chosen = None
best_score = None
for name, dt in dt_candidates:
    spb = bit_time / dt
    if spb <= 0:
        continue
    # prefer plausible UART sampling density and common ranges
    if 2 <= spb <= 5000:
        score = abs(spb - 16)
    else:
        score = 1e9 + abs(spb - 16)
    if best_score is None or score < best_score:
        best_score = score
        chosen = (name, dt, spb)

if chosen is None:
    raise SystemExit('Could not derive sample period from #CLOCK/#SIZE')

source_name, dt_s, spb = chosen

vmin, vmax = min(samples), max(samples)
thr = (vmin + vmax) / 2.0
bits = [1 if v > thr else 0 for v in samples]

def decode_with_phase(bits, dt, baud, phase):
    spb = (1.0 / baud) / dt
    i = 1
    decoded = []
    attempts = 0
    valid = 0
    n = len(bits)
    min_needed = int((10.5 + phase) * spb) + 2
    while i < n - min_needed:
        if bits[i-1] == 1 and bits[i] == 0:
            attempts += 1
            sidx = int(round(i + phase * spb))
            if sidx >= n or bits[sidx] != 0:
                i += 1
                continue
            bval = 0
            ok = True
            for b in range(8):
                idx = int(round(i + (1 + phase + b) * spb))
                if idx >= n:
                    ok = False
                    break
                if bits[idx]:
                    bval |= (1 << b)
            stop_idx = int(round(i + (9 + phase) * spb))
            if ok and stop_idx < n and bits[stop_idx] == 1:
                valid += 1
                decoded.append((i * dt, bval))
                i += max(1, int(spb * 9.5))
                continue
        i += 1
    ratio = (valid / attempts) if attempts else 0.0
    return decoded, attempts, valid, ratio, spb

phases = [x/100 for x in range(20, 81)]
phase_results = []
for p in phases:
    dec, att, val, ratio, s = decode_with_phase(bits, dt_s, BAUD, p)
    phase_results.append((p, ratio, val, att, len(dec)))

best_phase = max(phase_results, key=lambda x: (x[1], x[2], x[4], -abs(x[0]-0.5)))
best_p = best_phase[0]
decoded, attempts, valid, ratio, spb = decode_with_phase(bits, dt_s, BAUD, best_p)

stream = [b for _, b in decoded]

frames = []
if decoded:
    cur = [decoded[0]]
    for j in range(1, len(decoded)):
        gap_ms = (decoded[j][0] - decoded[j-1][0]) * 1000.0
        if gap_ms > HARD_SPLIT_MS:
            frames.append(cur)
            cur = []
        cur.append(decoded[j])
    if cur:
        frames.append(cur)

print('=== INPUT / HEADER PARSE ===')
print(f'File: {PATH}')
print(f'Total lines: {len(lines)}')
print(f'Parsed samples: {N}')
print(f'#CLOCK raw: {clock_raw}')
print(f'#SIZE raw: {size_raw}')
print(f'Derived sample period: {dt_s:.12g} s ({dt_s*1e6:.6f} us) via {source_name}')
print(f'Samples per bit @ {BAUD}: {spb:.6f}')
if size_val is not None:
    print(f'#SIZE numeric: {size_val} (delta vs parsed: {N - size_val})')
print(f'Waveform min/max/threshold: {vmin:.6g} / {vmax:.6g} / {thr:.6g}')

print('\n=== PHASE OPTIMIZATION (0.20..0.80 bit) ===')
print('phase  valid_stop_ratio  valid  attempts  decoded')
for p, rr, vv, aa, dd in phase_results:
    if p in [0.2,0.3,0.4,0.5,0.6,0.7,0.8] or p == best_p:
        mark = ' <BEST>' if p == best_p else ''
        print(f'{p:0.2f}   {rr:0.6f}         {vv:6d}  {aa:8d}  {dd:7d}{mark}')
print(f'Chosen phase: {best_p:.2f} bit (ratio={ratio:.6f}, valid={valid}, attempts={attempts}, decoded={len(decoded)})')

print('\n=== BYTE STREAM ===')
print(f'Decoded bytes: {len(decoded)}')
if decoded:
    print(f'First byte timestamp: {decoded[0][0]*1000:.3f} ms')
    print(f'Last  byte timestamp: {decoded[-1][0]*1000:.3f} ms')

print('\n=== FRAME SPLIT BY GAP > 2.5 ms ===')
print(f'Frames detected: {len(frames)}')
flen_hist = Counter(len(f) for f in frames)
print('Frame length histogram (len:count):')
for k in sorted(flen_hist):
    print(f'  {k}: {flen_hist[k]}')

print('\n=== TOP REPEATED EXACT FRAMES (length 1..8, top 15 each) ===')
for L in range(1, 9):
    ctr = Counter(tuple(b for _, b in f) for f in frames if len(f) == L)
    print(f'-- length {L}: unique={len(ctr)} total={sum(ctr.values())}')
    for t, c in ctr.most_common(15):
        hx = ' '.join(f'{x:02X}' for x in t)
        print(f'  {c:5d}  {hx}')

print('\n=== TOP N-GRAMS IN CONTINUOUS BYTE STREAM (n=2..6, top 20 each) ===')
for n in range(2, 7):
    ctr = Counter(tuple(stream[i:i+n]) for i in range(0, max(0, len(stream)-n+1)))
    print(f'-- n={n}: unique={len(ctr)} total={sum(ctr.values())}')
    for t, c in ctr.most_common(20):
        hx = ' '.join(f'{x:02X}' for x in t)
        print(f'  {c:5d}  {hx}')

print('\n=== POTENTIAL POLL/RESPONSE MOTIFS ===')
print('Rule: 1-byte frame followed by 4..7-byte frame, gap 3..12 ms')
motif = Counter()
for i in range(len(frames)-1):
    f1, f2 = frames[i], frames[i+1]
    if len(f1) == 1 and 4 <= len(f2) <= 7:
        gap_ms = (f2[0][0] - f1[-1][0]) * 1000.0
        if 3.0 <= gap_ms <= 12.0:
            k = ((tuple(b for _, b in f1)), (tuple(b for _, b in f2)))
            motif[k] += 1
print(f'Unique motif pairs: {len(motif)}')
for (a, b), c in motif.most_common():
    ha = ' '.join(f'{x:02X}' for x in a)
    hb = ' '.join(f'{x:02X}' for x in b)
    print(f'  {c:5d}  [{ha}] -> [{hb}]')


def per_position_report(target_len):
    arr = [tuple(b for _, b in f) for f in frames if len(f) == target_len]
    print(f'\n=== {target_len}-BYTE FRAME POSITION STATS ===')
    print(f'Frames of length {target_len}: {len(arr)}')
    if not arr:
        return
    for pos in range(target_len):
        vals = [x[pos] for x in arr]
        ctr = Counter(vals)
        print(f'pos {pos}: min={min(vals)} max={max(vals)} mean={mean(vals):.3f}')
        top = ctr.most_common(10)
        s = ', '.join(f'{v:02X}:{c}' for v, c in top)
        print(f'  top10: {s}')

per_position_report(5)
per_position_report(6)

arr6 = [tuple(b for _, b in f) for f in frames if len(f) == 6]
if arr6:
    ok6 = sum(1 for x in arr6 if x[5] == (sum(x[0:5]) & 0xFF))
    print('\n=== 6-BYTE CHECKSUM TEST ===')
    print('Rule: byte5 == (byte0+byte1+byte2+byte3+byte4) & 0xFF')
    print(f'Pass: {ok6}/{len(arr6)} ({(100.0*ok6/len(arr6)):.2f}%)')

arr5 = [tuple(b for _, b in f) for f in frames if len(f) == 5]
if arr5:
    ok5 = sum(1 for x in arr5 if x[4] == (sum(x[0:4]) & 0xFF))
    print('\n=== 5-BYTE CHECKSUM TEST ===')
    print('Rule: byte4 == (byte0+byte1+byte2+byte3) & 0xFF')
    print(f'Pass: {ok5}/{len(arr5)} ({(100.0*ok5/len(arr5)):.2f}%)')

print('\n=== FIRST 80 DECODED FRAMES (timestamp + gap) ===')
prev_end_ms = None
for idx, f in enumerate(frames[:80], start=1):
    start_ms = f[0][0] * 1000.0
    end_ms = f[-1][0] * 1000.0
    gap = None if prev_end_ms is None else (start_ms - prev_end_ms)
    hx = ' '.join(f'{b:02X}' for _, b in f)
    gtxt = 'N/A' if gap is None else f'{gap:.3f} ms'
    print(f'{idx:02d}  t={start_ms:.3f} ms  gap={gtxt:>9}  len={len(f):2d}  {hx}')
    prev_end_ms = end_ms
