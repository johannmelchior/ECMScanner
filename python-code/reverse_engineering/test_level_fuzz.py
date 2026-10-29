import ctypes
import os
import sys

# Load the DLL
dll_path = os.path.abspath(r"original-software/BUDS2/lib/seed_key.dll")
os.environ['PATH'] = os.path.dirname(dll_path) + ';' + os.environ['PATH']

try:
    lib = ctypes.CDLL(dll_path)
except OSError as e:
    print(f"Failed to load DLL: {e}")
    sys.exit(1)

# Signature
sk_calculate_key = lib[1]
sk_calculate_key.argtypes = [
    ctypes.c_int,          # level/cluster_id?
    ctypes.c_void_p,       # seed buffer
    ctypes.c_int,          # seed buffer size
    ctypes.c_char_p,       # key buffer
    ctypes.c_int,          # max key len
    ctypes.POINTER(ctypes.c_int) # actual key len pointer
]
sk_calculate_key.restype = ctypes.c_int

# Buffers
key_buf = ctypes.create_string_buffer(256)
actual_len = ctypes.c_int(0)
seed_buf = ctypes.create_string_buffer(32)
seed_buf[0] = 193 # Fix version

print("Fuzzing Arg 1 (Level/Cluster?)...")
for lvl in range(20):
    print(f"[TEST] Arg1={lvl}", flush=True)
    try:
        sk_calculate_key(lvl, seed_buf, 32, key_buf, 256, ctypes.byref(actual_len))
    except:
        pass

print("\nFuzzing Arg 3 (Size)...")
for s in range(35):
    print(f"[TEST] Arg3={s}", flush=True)
    try:
        sk_calculate_key(1, seed_buf, s, key_buf, 256, ctypes.byref(actual_len))
    except:
        pass
