import ctypes
import struct

# Load DLL
dll_path = r"c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\original-software\BUDS2\lib\seed_key.dll"
try:
    dll = ctypes.CDLL(dll_path)
except OSError as e:
    print(f"Failed to load DLL: {e}")
    exit(1)

# Function prototype
# int sk_calculate_key(int level, char* seed, int seed_len, char* key, int key_max_len)
# Using generic pointers
calculate_key = dll[1] # Ordinal 1
calculate_key.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
calculate_key.restype = ctypes.c_int

# Known Seed and Partial Key from Log
# Log Timestamp: 16:08:29.524
# Seed from 7BB (ECU)
raw_seed_hex = "062EA28C48C270A636B0500046572630BBA0776C700B799C03E31D489AFAEAAD"
seed_bytes = bytes.fromhex(raw_seed_hex)

# Partial Key from 7B3 (BUDS)
# Starts with F3 E7 0E E7
target_key_start = bytes.fromhex("F3E70EE7")

print(f"Target Seed: {raw_seed_hex}")
print(f"Target Key Start: {target_key_start.hex()}")

def test_config(type_val):
    # Construct buffer
    # Header: [C1] [Type...]
    header = b'\xC1' + type_val
    input_data = header + seed_bytes
    
    # buffers
    seed_buf = ctypes.create_string_buffer(input_data, len(input_data))
    key_buf = ctypes.create_string_buffer(64) # Big enough
    
    # Level 1 (Security Access Level 1)
    # The first arg is 'level'. In logs: 02 27 01 -> Level 1.
    ret = calculate_key(1, seed_buf, len(input_data), key_buf, 64)
    
    if ret == 0:
        # Check generated key against target
        # Key buffer might contain garbage after null terminator? Or just raw bytes.
        # usually key is ~32 bytes.
        gen_key = key_buf.raw[:32]
        
        if gen_key.startswith(target_key_start):
            print(f"!!! MATCH FOUND !!! Type: {type_val.hex()}")
            print(f"Full Key: {gen_key.hex()}")
            return True
    return False

print("Starting Brute Force...")

# Strategy 1: Type is 1 byte (0-255)
print("Testing 1-byte Cluster Type...")
for i in range(256):
    if test_config(bytes([i])):
        exit(0)

# Strategy 2: Type is 2 bytes (0-65535) - Little Endian
print("Testing 2-byte Cluster Type (LE)...")
for i in range(256*256):
    type_bytes = struct.pack('<H', i)
    if test_config(type_bytes):
        exit(0)

print("Failed to find match.")
