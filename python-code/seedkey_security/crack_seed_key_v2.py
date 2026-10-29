
def ror(val, r_bits, max_bits=16):
    return ((val & ((1 << max_bits) - 1)) >> r_bits % max_bits) | \
           (val << (max_bits - (r_bits % max_bits)) & ((1 << max_bits) - 1))

def rol(val, r_bits, max_bits=16):
    return (val << r_bits % max_bits) & ((1 << max_bits) - 1) | \
           ((val & ((1 << max_bits) - 1)) >> (max_bits - (r_bits % max_bits)))

def solve():
    # Pair 1
    s1 = 0x466E
    k1 = 0x3B32
    # Pair 2
    s2 = 0xBD9E
    k2 = 0x0639

    print("Checking standard shifts/rotations + XOR/Linear...")

    for shift in range(16):
        # Apply shift
        s1_rol = rol(s1, shift)
        s2_rol = rol(s2, shift)
        
        s1_ror = ror(s1, shift)
        s2_ror = ror(s2, shift)

        # Check ROL + XOR
        xor_val1 = s1_rol ^ k1
        xor_val2 = s2_rol ^ k2
        if xor_val1 == xor_val2:
            print(f"FOUND! Key = ROL(Seed, {shift}) ^ 0x{xor_val1:04X}")

        # Check ROR + XOR
        xor_val1_r = s1_ror ^ k1
        xor_val2_r = s2_ror ^ k2
        if xor_val1_r == xor_val2_r:
            print(f"FOUND! Key = ROR(Seed, {shift}) ^ 0x{xor_val1_r:04X}")

        # Check ROL + Add
        add_val1 = (k1 - s1_rol) & 0xFFFF
        add_val2 = (k2 - s2_rol) & 0xFFFF
        if add_val1 == add_val2:
             print(f"FOUND! Key = (ROL(Seed, {shift}) + 0x{add_val1:04X}) & 0xFFFF")
        
        # Check ROR + Add
        add_val1_r = (k1 - s1_ror) & 0xFFFF
        add_val2_r = (k2 - s2_ror) & 0xFFFF
        if add_val1_r == add_val2_r:
             print(f"FOUND! Key = (ROR(Seed, {shift}) + 0x{add_val1_r:04X}) & 0xFFFF")

    print("Checking Byte Swaps...")
    def swap_bytes(n):
        return ((n & 0xFF) << 8) | ((n >> 8) & 0xFF)

    s1_swap = swap_bytes(s1)
    s2_swap = swap_bytes(s2)

    # Check Swap + XOR
    if (s1_swap ^ k1) == (s2_swap ^ k2):
        print(f"FOUND! Key = Swap(Seed) ^ 0x{(s1_swap ^ k1):04X}")

    print("Checking specific BRP Multiplier...")
    # Some BRP use Seed * 7 + 3 or similar.
    # We already checked linear in v1, but maybe with shifts?
    
    # Try complex masks
    # Key = (Seed & Mask1) + Constant
    
    # Try XOR then Multiply?
    # K = (S ^ X) * M
    
    # Try Multiply then XOR?
    # K = (S * M) ^ X
    # (k1 ^ x) / s1 = M
    # Hard to solve.

if __name__ == "__main__":
    solve()
