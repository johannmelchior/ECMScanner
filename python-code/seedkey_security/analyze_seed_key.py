import ctypes
import os
import sys
import struct

# Load the DLL
dll_path = os.path.abspath(r"original-software/BUDS2/lib/seed_key.dll")
# Ensure dependencies are found
os.environ['PATH'] = os.path.dirname(dll_path) + ';' + os.environ['PATH']

try:
    lib = ctypes.CDLL(dll_path)
except OSError as e:
    print(f"Failed to load DLL: {e}")
    sys.exit(1)

# Signature matches what we found:
# int sk_calculate_key(int level, void* seed, int size, char* key_out, int max_key_len, int* actual_key_len)
sk_calculate_key = lib[1] # Ordinal 1
sk_calculate_key.argtypes = [
    ctypes.c_int,          # level
    ctypes.c_void_p,       # seed buffer
    ctypes.c_int,          # seed buffer size
    ctypes.c_char_p,       # key buffer
    ctypes.c_int,          # max key len
    ctypes.POINTER(ctypes.c_int) # actual key len pointer
]
sk_calculate_key.restype = ctypes.c_int

# Valid inputs found so far
VERSION_BYTE = 193 # 0xC1

print(f"Valid Version Found: {VERSION_BYTE}")
print("To find the Key, we need the correct 'Cluster Type'.")
print("We have determined the input buffer structure uses a Header.")
print("Byte 0: Version (193)")
print("Byte 1+: Cluster Type (Value Unknown)")

# Example usage structure
key_buf = ctypes.create_string_buffer(256)
actual_len = ctypes.c_int(0)
seed_buf = ctypes.create_string_buffer(32)

seed_buf[0] = VERSION_BYTE
# seed_buf[1] = ??? (Cluster Type)

print("\nCalling DLL with Version 193...")
# This will likely print "ERROR: Unknown cluster type"
ret = sk_calculate_key(1, seed_buf, 32, key_buf, 256, ctypes.byref(actual_len))
print(f"Return Code: {ret}")
