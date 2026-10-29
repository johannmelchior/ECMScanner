import csv
import statistics

LOG_FILE = r"logs/BRP-SEADOO-RXT-X-AS-2011-260hp/funcionamento completo.csv"

def analyze_rxt_voltage():
    print(f"Analyzing {LOG_FILE}...")
    
    rpm_data = [] # (time, rpm)
    candidates = {} # Key: (ID, Byte), Value: list of (time, val)

    with open(LOG_FILE, 'r') as f:
        reader = csv.reader(f)
        start_time = None
        
        for row in reader:
            if len(row) < 4: continue
            try:
                # Time format might be HH:MM:SS.ffffff or just seconds
                # Let's try to parse or just use row index if needed.
                # The previous logs had "15:33:09.340478"
                t_str = row[0].strip()
                
                # Simple seconds converter
                parts = t_str.split(':')
                if len(parts) == 3:
                    h, m, s = parts
                    curr_time = float(h)*3600 + float(m)*60 + float(s)
                else:
                    curr_time = 0 # Fallback
                
                if start_time is None: start_time = curr_time
                rel_time = curr_time - start_time
                
                can_id = int(row[1].strip(), 16)
                data = [int(x, 16) for x in row[3].strip().split()]
                
                # Check RPM on ID 0x102 (Bytes 0,1)
                if can_id == 0x102 and len(data) >= 2:
                    raw_rpm = (data[0] << 8) | data[1]
                    rpm = raw_rpm / 4 # Standard factor
                    rpm_data.append((rel_time, rpm))
                
                # Collect candidates for voltage
                # We look for 1 byte or 2 byte values that look like voltage
                # 1 Byte: Val/10 (~12-14V -> 120-145), Val/5 (~60-72)
                # 2 Byte: Val/100 (~1200-1450), Val/1000 (~12000-14500)
                
                # Store potential candidates
                # To save memory, only process specific IDs or just aggregate stats?
                # Using a moving average might be better but let's just collect all for now for generic IDs.
                # Optimization: Only check IDs that appear frequent enough.
                
                if can_id in [0x342, 0x400, 0x202, 0x110, 0x106, 0x122, 0x232, 0x7E8]:
                     for i in range(len(data)):
                        # Byte catch
                        val = data[i]
                        candidates.setdefault((can_id, i, 1), []).append((rel_time, val))
                        
                     for i in range(len(data)-1):
                        # Word catch
                        val = (data[i] << 8) | data[i+1]
                        candidates.setdefault((can_id, i, 2), []).append((rel_time, val))

            except: pass

    # Find Engine OFF time
    # Look for RPM dropping from > 2000 to 0
    cutoff_time = 0
    last_rpm_high = 0
    
    for t, rpm in rpm_data:
        if rpm > 1000:
            last_rpm_high = t
        if rpm < 100 and last_rpm_high > 0 and (t - last_rpm_high) > 1:
            cutoff_time = t
            break
            
    if cutoff_time == 0:
        cutoff_time = rpm_data[-1][0] if rpm_data else 0
        print(f"Comparison split at end (No drop found?): {cutoff_time:.1f}s")
    else:
        print(f"Engine Cutoff detected at: {cutoff_time:.1f}s")

    # Compare Before vs After
    print(f"\nComparing Average Values (Before {cutoff_time:.1f}s vs After)")
    print(f"{'ID':<6} {'Off':<4} {'Sz':<3} {'Running (Avg)':<15} {'Stopped (Avg)':<15} {'Diff':<10} {'Scale Candidate'}")
    
    for key, values in candidates.items():
        can_id, offset, size = key
        
        # More lenient timing
        vals_run = [v for t, v in values if 10 < t < cutoff_time - 1] 
        vals_stop = [v for t, v in values if t > cutoff_time]
        
        if not vals_run or not vals_stop: continue
        
        avg_run = statistics.mean(vals_run)
        avg_stop = statistics.mean(vals_stop)
        
        diff = avg_run - avg_stop
        
        if diff < 0.5: continue # Must be a drop
        
        # Check specific logical scales
        # /10
        if 100 <= avg_run <= 160:
             print(f"{can_id:03X}    {offset}    {size}    {avg_run:.1f} ({avg_run/10:.2f}V)    {avg_stop:.1f} ({avg_stop/10:.2f}V)    {diff:.1f}       (Scale /10)")
        # /5
        elif 50 <= avg_run <= 80:
             print(f"{can_id:03X}    {offset}    {size}    {avg_run:.1f} ({avg_run/5:.2f}V)     {avg_stop:.1f} ({avg_stop/5:.2f}V)     {diff:.1f}       (Scale /5)")
        # /1000
        elif 10000 <= avg_run <= 16000:
             print(f"{can_id:03X}    {offset}    {size}    {avg_run:.0f} ({avg_run/1000:.2f}V)  {avg_stop:.0f} ({avg_stop/1000:.2f}V)  {diff:.0f}       (Scale /1000)")
        else:
             # Just print raw if it looks promising (large drop)
             if diff > (avg_run * 0.05): # >5% drop
                print(f"{can_id:03X}    {offset}    {size}    {avg_run:.1f} (Raw)          {avg_stop:.1f} (Raw)          {diff:.1f}       (Unknown)")


if __name__ == "__main__":
    analyze_rxt_voltage()
