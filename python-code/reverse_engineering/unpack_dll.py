import urllib.request
import zipfile
import os
import subprocess
import shutil
import re

# Configurações do UPX e Alvos
# URL oficial do release mais atual
UPX_URL = 'https://github.com/upx/upx/releases/download/v4.2.1/upx-4.2.1-win64.zip'
UPX_ZIP = 'upx.zip'
UPX_EXE = 'upx.exe'

# Caminho da DLL original criptografada/comprimida
TARGET_DLL = os.path.join('original-software', 'BUDS2', 'PDSEncryption.dll')
# Caminho onde salvaremos a DLL limpa
UNPACKED_DLL = os.path.join('original-software', 'BUDS2', 'PDSEncryption_unpacked.dll')

def download_and_extract_upx():
    """Baixa o UPX do GitHub e extrai apenas o executável."""
    if os.path.exists(UPX_EXE):
        print(f"[OK] UPX já encontrado: {UPX_EXE}")
        return True

    print(f"[INFO] Baixando UPX de: {UPX_URL} ...")
    try:
        urllib.request.urlretrieve(UPX_URL, UPX_ZIP)
        
        print("[INFO] Extraindo UPX...")
        with zipfile.ZipFile(UPX_ZIP, 'r') as z:
            # O executável fica dentro de uma subpasta no zip, vamos achá-lo
            for filename in z.namelist():
                if filename.lower().endswith('upx.exe'):
                    # Lê o conteúdo do arquivo dentro do zip
                    content = z.read(filename)
                    # Salva na raiz do nosso projeto
                    with open(UPX_EXE, 'wb') as f_out:
                        f_out.write(content)
                    print(f"[SUCESSO] UPX extraído para: {UPX_EXE}")
                    return True
    except Exception as e:
        print(f"[ERRO] Falha ao baixar/extrair UPX: {e}")
        return False
    finally:
        # Limpa o zip baixado
        if os.path.exists(UPX_ZIP):
            os.remove(UPX_ZIP)

def unpack_dll():
    """Roda o comando upx -d na DLL alvo."""
    if not os.path.exists(TARGET_DLL):
        print(f"[ERRO] Arquivo alvo não encontrado: {TARGET_DLL}")
        return False
    
    print(f"[INFO] Tentando descompactar {TARGET_DLL}...")
    
    # Monta o comando: upx.exe -d "arquivo_origem" -o "arquivo_destino" --force
    cmd = [
        os.path.abspath(UPX_EXE), 
        '-d', 
        os.path.abspath(TARGET_DLL), 
        '-o', 
        os.path.abspath(UNPACKED_DLL), 
        '--force'
    ]
    
    try:
        # Executa o processo
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Mostra a saída do UPX (útil para debug)
        print("--- Saída do UPX ---")
        print(result.stdout)
        if result.stderr:
            print("--- Erros do UPX ---")
            print(result.stderr)
            
        if result.returncode == 0:
            print(f"[SUCESSO] DLL descompactada criada em: {UNPACKED_DLL}")
            return True
        else:
            print("[FALHA] O UPX não conseguiu descompactar o arquivo.")
            print("Motivos possíveis: O arquivo não está compactado com UPX ou está corrompido/protegido.")
            return False

    except Exception as e:
        print(f"[ERRO] Exceção ao executar UPX: {e}")
        return False

def analyze_unpacked_dll():
    """Lê a DLL descompactada e procura por strings interessantes."""
    if not os.path.exists(UNPACKED_DLL):
        print("[ERRO] Nada para analisar.")
        return

    print("\n" + "="*50)
    print(" ANÁLISE DE STRINGS - DLL DESCOMPACTADA")
    print("="*50)

    try:
        with open(UNPACKED_DLL, 'rb') as f:
            content = f.read()

        # Expressão regular para encontrar strings ASCII legíveis (5 chars ou mais)
        # b'[ -~]{5,}' significa sequências de bytes entre espaço (32) e til (126)
        all_strings = re.findall(b'[ -~]{5,}', content)
        
        print(f"[INFO] Total de strings encontradas: {len(all_strings)}")
        
        # Filtrar apenas as interessantes
        keywords = [
            'Seed', 'Key', 'Secur', 'Access', 'Unlock', 'Algo', 'Crypt', 
            'BRP', 'Rotax', 'Privilege', 'Calculate', 'Generate', 'Auth'
        ]
        
        interesting_strings = []
        for s in all_strings:
            try:
                decoded = s.decode('utf-8', 'ignore')
                # Verifica se contém alguma das palavras-chave (case insensitive)
                if any(k.lower() in decoded.lower() for k in keywords):
                    interesting_strings.append(decoded)
            except:
                pass

        # Remove duplicatas e ordena
        unique_interesting = sorted(list(set(interesting_strings)))

        print(f"[INFO] Strings suspeitas encontradas: {len(unique_interesting)}")
        print("-" * 40)
        for s in unique_interesting:
            print(f" > {s}")
        print("-" * 40)

    except Exception as e:
        print(f"[ERRO] Falha na análise de strings: {e}")

if __name__ == "__main__":
    print("--- INICIANDO PROCESSO DE ENGENHARIA REVERSA (UPX) ---")
    if download_and_extract_upx():
        if unpack_dll():
            analyze_unpacked_dll()
    print("\nProcesso concluído.")
