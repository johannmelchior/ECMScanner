import ctypes
import os
import struct

DLL_PATH = os.path.join(os.getcwd(), 'original-software', 'BUDS2', 'PDSEncryption_unpacked.dll')

def test_dll_functions():
    if not os.path.exists(DLL_PATH):
        print("DLL nao encontrada.")
        return

    print(f"Carregando DLL: {DLL_PATH}")
    try:
        pds_lib = ctypes.CDLL(DLL_PATH)
    except:
        try:
            pds_lib = ctypes.WinDLL(DLL_PATH)
        except Exception as e:
            print(f"Erro load: {e}")
            return

    # Seed encontrada nos Logs (Exchange 1)
    # Seed: 46 6E
    # Key Esperada: 3B 32
    print(f"Target: Seed 46 6E -> Key 3B 32")

    # --- TENTATIVA DE ARROMBAR O deskey ---
    # O erro "access violation reading 0x7" com arg2=0 sugere que arg2 é um ponteiro.
    # Vamos criar buffers grandes para garantir.
    key_buf = ctypes.create_string_buffer(8)     # Chave de 8 bytes (padrão DES)
    schedule_buf = ctypes.create_string_buffer(256) # Buffer grande para "schedule" ou contexto
    
    # Vamos tentar uma chave "chute" (pode ser qualquer coisa para teste)
    # Mas se a chave real for hardcoded, talvez não precisemos chamar deskey.
    # Vamos testar se deskey PRELCISA ser chamada para o des funcionar.
    
    # Setar assinatura
    pds_lib.deskey.argtypes = [ctypes.c_char_p, ctypes.c_char_p] # Dois ponteiros!
    pds_lib.deskey.restype = None

    print("\n--- TESTE DESKEY (Com Buffers) ---")
    try:
        # Tenta chamar passando dois buffers
        pds_lib.deskey(key_buf, schedule_buf)
        print(">>> SUCESSO! deskey rodou sem crash com (buffer, buffer).")
        print("Isso confirma que 'deskey' gera um KeySchedule no segundo argumento.")
    except Exception as e:
        print(f"Crash no deskey: {e}")

    # --- TESTE DAS COMBINACOES DE SEED ---
    # Primeiro tentamos com 2 argumentos (se usar Global)
    pds_lib.des.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    pds_lib.des.restype = None

    seed_variations = []
    
    # 1. Padding com Zeros a direita: 46 6E 00 00 ...
    b = bytearray(8); b[0]=0x46; b[1]=0x6E
    seed_variations.append(("Right Pad", b))
    
    # 2. Padding com Zeros a esquerda: ... 00 00 46 6E
    b = bytearray(8); b[6]=0x46; b[7]=0x6E
    seed_variations.append(("Left Pad", b))

    # 3. Little Endian Right: 6E 46 00 00 ...
    b = bytearray(8); b[0]=0x6E; b[1]=0x46
    seed_variations.append(("LE Right", b))

    # 4. Little Endian Left: ... 00 00 6E 46
    b = bytearray(8); b[6]=0x6E; b[7]=0x46
    seed_variations.append(("LE Left", b))
    
    # 5. Repeticao: 46 6E 46 6E ...
    b = bytearray(8); 
    for i in range(0,8,2): b[i]=0x46; b[i+1]=0x6E
    seed_variations.append(("Repeat", b))

    print("\n--- TESTE DE CRIPTOGRAFIA (SEED -> KEY) ---")
    out_buf = ctypes.create_string_buffer(8)
    
    for name, seed in seed_variations:
        inp = ctypes.create_string_buffer(bytes(seed))
        ctypes.memset(out_buf, 0, 8)
        
        try:
            # Tenta com 2 argumentos
            pds_lib.des(inp, out_buf)
            res = out_buf.raw.hex()
            found = "3b32" in res or "323b" in res
            print(f"[{name:10}] (2args) In: {inp.raw.hex()} -> Out: {res}{' <<< FOUND!' if found else ''}")
            
        except Exception as e:
            # Se crashar, tenta com 3 argumentos (passando o schedule)
            # Reconfigura assinatura dinamicamente
            try:
                pds_lib.des.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
                if name == "Right Pad": print("...Tentando com 3 argumentos (input, output, schedule)...")
                pds_lib.des(inp, out_buf, schedule_buf)
                res = out_buf.raw.hex()
                found = "3b32" in res or "323b" in res
                print(f"[{name:10}] (3args) In: {inp.raw.hex()} -> Out: {res}{' <<< FOUND!' if found else ''}")
                
                # Reseta argtypes para o próximo loop tentar 2 de novo (ou mantem 3 se funcionar)
                # Na verdade, se funcionar com 3, deveriamos manter.
                
            except Exception as e2:
                print(f"[{name:10}] Crash: {e2}")

if __name__ == '__main__':
    test_dll_functions()
