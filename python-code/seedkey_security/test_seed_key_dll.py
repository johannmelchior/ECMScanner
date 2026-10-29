import ctypes
import os
import sys

# Using the copied file in BUDS2 root
DLL_PATH = os.path.join(os.getcwd(), 'original-software', 'BUDS2', 'seed_key.dll')

def test_it():
    if not os.path.exists(DLL_PATH):
        print(f"DLL not found at: {DLL_PATH}")
        return

    print(f"Attempting to load: {DLL_PATH}")
    
    # Try loading with LoadLibrary to check error
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    hMod = kernel32.LoadLibraryW(DLL_PATH)
    if not hMod:
        err = ctypes.get_last_error()
        print(f"LoadLibraryW failed with error code: {err}")
        # Error 126 = Module not found (dependencies?)
        # Error 193 = Bad exe format (32/64 mismatch)
        return

    print(f"LoadLibraryW success. Handle: {hMod}")
    
    # Now use CDLL wrapping that handle (optional, or just load again)
    try:
        sk = ctypes.CDLL(DLL_PATH)
    except Exception as e:
        print(f"CDLL path failed: {e}")
        return

    print("Definitions loaded.")
    
    # Valid Signature Found! 
    # (level, seed_ptr, seed_len, key_ptr, max_len, actual_len_ptr)
    
    sk.sk_calculate_key.argtypes = [
        ctypes.c_int,               # LEVEL
        ctypes.c_char_p,            # SEED PTR
        ctypes.c_int,               # SEED LEN
        ctypes.c_char_p,            # KEY PTR
        ctypes.c_int,               # MAX LEN
        ctypes.POINTER(ctypes.c_int) # ACTUAL LEN PTR
    ]
    
    # Try multiple combinations
    print("\nStarting Brute Force on Parameters...")
    
    key_buffer = ctypes.create_string_buffer(64)
    actual_len = ctypes.c_int(0)
    
    # Seeds to try
    # 46 6E
    seeds = [
        (b'\x46\x6E', 2),
        (b'\x46\x6E\x00\x00', 4),
        (b'\x00\x00\x46\x6E', 4)
    ]
    
    found = False
    
    for lvl in range(20): # Try levels 0-19
        for s_bytes, s_len in seeds:
            ctypes.memset(key_buffer, 0, 64)
            actual_len.value = 0
            
            # Print less to avoid noise, only on success or error change
            try:
                # Capture stdout? Hard in dll.
                res = sk.sk_calculate_key(lvl, s_bytes, s_len, key_buffer, 64, ctypes.byref(actual_len))
                
                if res == 0: # Success usually 0? Or 1?
                     print(f"[!] SUCCESS? Lvl={lvl} SeedLen={s_len} Bytes={s_bytes.hex()}")
                     print(f"    Key: {key_buffer.raw[:actual_len.value].hex()}")
                     if b'\x3B\x32' in key_buffer.raw[:actual_len.value]:
                         print("    MATCHED TARGET KEY 3B32!")
                         found = True
                         break
                elif key_buffer.raw[0] != 0: # Check if key buffer touched
                     pass # Maybe error with partial key
                     
            except Exception as e:
                print(f"Crash at Lvl={lvl}: {e}")
        if found: break
        
    print("Test finished.")

if __name__ == "__main__":
    test_it()
