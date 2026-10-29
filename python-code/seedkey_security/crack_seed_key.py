
def solve():
    # Pair 1 (from 155256.csv)
    # Seed: 04 67 01 46 6E -> 0x466E (18030)
    # Key: 04 27 02 3B 32 -> 0x3B32 (15154)
    s1 = 0x466E
    k1 = 0x3B32

    # Pair 2 (from 155628.csv)
    # Seed: 04 67 01 BD 9E -> 0xBD9E (48542)
    # Key: 04 27 02 06 39 -> 0x0639 (1593)
    s2 = 0xBD9E
    k2 = 0x0639

    print(f"S1: {s1:04X} ({s1}) -> K1: {k1:04X} ({k1})")
    print(f"S2: {s2:04X} ({s2}) -> K2: {k2:04X} ({k2})")

    # Method 1: Linear relation (Key = Seed * Multiplier + Increment)
    print("\n--- Testing Linear Relation (Key = Seed * M + A) (Mod 16-bit) ---")
    for m in range(65536):
        # Check if this slope works for the delta
        # (s1 * m + a) - (s2 * m + a) = k1 - k2
        # m * (s1 - s2) = k1 - k2 (mod 65536)
        
        diff_s = (s1 - s2) & 0xFFFF
        diff_k = (k1 - k2) & 0xFFFF
        
        if (m * diff_s) & 0xFFFF == diff_k:
            # Found a potential M, calculate A
            # k1 = s1 * m + a => a = k1 - s1 * m
            a = (k1 - (s1 * m)) & 0xFFFF
            
            # Verify with S2
            calc_k2 = (s2 * m + a) & 0xFFFF
            if calc_k2 == k2:
                print(f"MATCH FOUND! Key = (Seed * {m} + {a}) & 0xFFFF")
                print(f"Multiplier: 0x{m:04X}, Increment: 0x{a:04X}")

    # Method 2: XOR then Add (Key = (Seed ^ XOR) + ADD)
    print("\n--- Testing XOR then ADD ---")
    for x in range(65536):
        a1 = (k1 - (s1 ^ x)) & 0xFFFF
        a2 = (k2 - (s2 ^ x)) & 0xFFFF
        if a1 == a2:
             print(f"MATCH FOUND! Key = ((Seed ^ 0x{x:04X}) + 0x{a1:04X}) & 0xFFFF")

    # Method 3: Add then XOR (Key = (Seed + ADD) ^ XOR)
    print("\n--- Testing ADD then XOR ---")
    for a in range(65536):
        x1 = k1 ^ ((s1 + a) & 0xFFFF)
        x2 = k2 ^ ((s2 + a) & 0xFFFF)
        if x1 == x2:
            print(f"MATCH FOUND! Key = ((Seed + 0x{a:04X}) ^ 0x{x1:04X})")

    # Method 4: Bitwise rotations?
    # Not easily brute forced without a custom implementation, but standard algos usually fit above.

if __name__ == "__main__":
    solve()
