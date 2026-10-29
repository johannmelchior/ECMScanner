import ctypes
import os
import sys
import hashlib
import re

DLL_PATH = os.path.join(os.getcwd(), 'original-software', 'BUDS2', 'PDSEncryption_unpacked.dll')
CLASS_PATH = os.path.join(os.getcwd(), 'original-software', 'BUDS2', 'ODXDataBin', 'temp_diag', 'DiagnosticApiOtx.class')

def crack_it():
    if not os.path.exists(DLL_PATH):
        print("DLL nao encontrada.")
        return
    
    try:
        pds = ctypes.CDLL(DLL_PATH)
    except:
        pds = ctypes.WinDLL(DLL_PATH)

    pds.deskey.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    pds.des.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

    # SEED: 46 6E
    # KEY: 3B 32
    
    # Seeds variants
    seeds = [
        ctypes.create_string_buffer(b'\x46\x6E\x00\x00\x00\x00\x00\x00'),
        ctypes.create_string_buffer(b'\x00\x00\x00\x00\x00\x00\x46\x6E'),
        ctypes.create_string_buffer(b'\x46\x6E\x46\x6E\x46\x6E\x46\x6E'),
        ctypes.create_string_buffer(b'\x46\x6E\xFF\xFF\xFF\xFF\xFF\xFF'),
        ctypes.create_string_buffer(b'\x6E\x46\x00\x00\x00\x00\x00\x00'), # ENDIAN SWAP SEED
        ctypes.create_string_buffer(b'\x00\x00\x00\x00\x00\x00\x6E\x46'), # ENDIAN SWAP RIGHT
    ]

    sched_buf = ctypes.create_string_buffer(256)
    out_buf = ctypes.create_string_buffer(8)
    
    with open(CLASS_PATH, 'rb') as f:
        data = f.read()

    candidates = []
    
    # 1. Start/End
    candidates.append(data[:8])
    candidates.append(data[-8:])
    
    # 2. Hashes
    md5 = hashlib.md5(data).digest()
    candidates.append(md5[:8])
    candidates.append(md5[8:16])
    
    sha1 = hashlib.sha1(data).digest()
    candidates.append(sha1[:8])
    candidates.append(sha1[8:16])
    candidates.append(sha1[10:18])

    # 3. Hex Strings in File (16 chars = 8 bytes)
    hex_pattern = re.compile(b'[0-9A-Fa-f]{16}')
    hex_matches = hex_pattern.findall(data)
    print(f"Found {len(hex_matches)} hex strings.")
    for h in hex_matches:
        try:
            candidates.append(bytes.fromhex(h.decode('ascii')))
        except: pass

    # 4. Strings "masterKey" locality?
    # Not exact bytes.

    print(f"Testing {len(candidates)} Smart Candidates...")
    
    for idx, key in enumerate(candidates):
        if len(key) != 8: continue
        
        k_buf = ctypes.create_string_buffer(key)
        try:
            pds.deskey(k_buf, sched_buf)
        except: continue
        
        for s_idx, in_buf in enumerate(seeds):
            ctypes.memset(out_buf, 0, 8)
            pds.des(in_buf, out_buf)
            res = out_buf.raw.hex()
            
            if "3b32" in res or "323b" in res:
                 print(f"\n[!!!] KEY ENCONTRADA (Smart): {key.hex()}")
                 print(f"Seed Idx: {s_idx}")
                 print(f"Result: {res}")
                 return
                 
    print("Candidates failed. Scanning ALL Hex Sequences (Byte-aligned window)...")
    # Sliding window logic for Raw Bytes again? I already did that.
    # What if the bytes are NOT ASCII Hex, but just Raw Bytes? 
    # I scanned that in v2.
    
    print("Failed.")

if __name__ == "__main__":
    crack_it()
