import subprocess
import os
import sys
import itertools
import string
import time

# Configurações
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SEVEN_ZIP_EXE = os.path.join(PROJECT_ROOT, "original-software", "BUDS2", "ODXDataBin", "7za.exe")
TARGET_FILE = os.path.join(PROJECT_ROOT, "original-software", "BUDS2", "ODXDataBin", "ParamAndCalib.7z")

# Lista de palavras base para gerar permutações e combinações "inteligentes"
SMART_WORDS = [
    "BRP", "brp", "BUDS", "buds", "BUDS2", "buds2", 
    "kpit", "KPIT", "2024", "2025", "2023", "1234",
    "Param", "Calib", "ParamAndCalib", "ODX", "odx",
    "rotax", "ROTAX", "can-am", "seadoo", "skidoo",
    "admin", "password", "service", "diag", "fw"
]

def try_password(password):
    """Tenta extrair (teste) o arquivo usando a senha fornecida."""
    # O comando 't' testa a integridade, o -p fornece a senha
    # -y assume yes para tudo
    cmd = [SEVEN_ZIP_EXE, "t", f"-p{password}", "-y", TARGET_FILE]
    
    # Rodamos o processo escondendo a saída para não sujar o terminal, 
    # exceto se encontrarmos a senha ou erro crítico
    try:
        # startupinfo esconde a janela do prompt no Windows
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(
            cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        )
        
        # Se o código de retorno for 0, sucesso na descompactação (senha correta)
        if result.returncode == 0:
            return True
    except Exception as e:
        print(f"Erro ao executar 7za: {e}")
    
    return False

def smart_dictionary_attack():
    print("--- Iniciando Ataque Baseado em Dicionário Inteligente ---")
    
    # 1. Tentar palavras soltas
    for word in SMART_WORDS:
        yield word
    
    # 2. Combinações de 2 palavras (ex: brp2024, budsrotax)
    for w1, w2 in itertools.permutations(SMART_WORDS, 2):
        yield f"{w1}{w2}"
        yield f"{w1}_{w2}"
        yield f"{w1}-{w2}"
        yield f"{w1}@{w2}"

def brute_force_attack(max_length=4):
    print(f"--- Iniciando Ataque de Força Bruta (até {max_length} caracteres) ---")
    chars = string.ascii_lowercase + string.digits # a-z0-9
    
    for length in range(1, max_length + 1):
        print(f"> Testando senhas com {length} caracteres...")
        for attempt in itertools.product(chars, repeat=length):
            yield "".join(attempt)

def main():
    if not os.path.exists(SEVEN_ZIP_EXE):
        print(f"ERRO: Não encontrei o 7za.exe em: {SEVEN_ZIP_EXE}")
        return

    if not os.path.exists(TARGET_FILE):
        print(f"ERRO: Não encontrei o arquivo alvo em: {TARGET_FILE}")
        return

    print("="*60)
    print(" FERRAMENTA DE QUEBRA DE SENHA (BRUTE FORCE) - 7ZIP")
    print(f" Alvo: {os.path.basename(TARGET_FILE)}")
    print("="*60)
    
    start_time = time.time()
    attempts = 0
    
    # Escolha o gerador de senhas aqui.
    # Ex: smart_dictionary_attack() ou brute_force_attack(3)
    
    # Vamos começar com o dicionário inteligente
    password_generator = smart_dictionary_attack()
    
    # Se quiser ativar força bruta pura (MUITO LENTO), descomente abaixo:
    # password_generator = brute_force_attack(max_length=5) 

    found = False
    for pwd in password_generator:
        attempts += 1
        if attempts % 100 == 0:
            elapsed = time.time() - start_time
            print(f"Tentativa #{attempts}: '{pwd}' ({attempts/elapsed:.1f} senhas/seg)")
        
        if try_password(pwd):
            end_time = time.time()
            print("\n" + "!"*60)
            print(f"SUCESSO! A SENHA FOI ENCONTRADA: {pwd}")
            print(f"Tempo total: {end_time - start_time:.2f} segundos")
            print("!"*60)
            
            # Salvar em arquivo
            with open("SENHA_DESCOBERTA.txt", "w") as f:
                f.write(pwd)
            
            found = True
            break
            
    if not found:
        print("\n" + "-"*60)
        print("Falha: A senha não foi encontrada na lista de tentativas.")
        print(f"Total testado: {attempts} senhas.")
        print("-"*60)

if __name__ == "__main__":
    main()
