import urllib.request
import zipfile
import os
import sys

# URL da versão "Embeddable" (Portátil) do Python 3.11 32-bit
PYTHON_32_URL = "https://www.python.org/ftp/python/3.11.7/python-3.11.7-embed-win32.zip"
DEST_DIR = "python32_env"
ZIP_NAME = "python32.zip"

def setup_python32():
    print(f"--- Configurando Ambiente Python 32-bit ---")
    
    if os.path.exists(os.path.join(DEST_DIR, "python.exe")):
        print("Python 32-bit já existe na pasta 'python32_env'.")
        return

    # 1. Baixar
    print(f"Baixando Python 32-bit de: {PYTHON_32_URL} ...")
    try:
        urllib.request.urlretrieve(PYTHON_32_URL, ZIP_NAME)
    except Exception as e:
        print(f"Erro no download: {e}")
        return

    # 2. Extrair
    print("Extraindo arquivos...")
    os.makedirs(DEST_DIR, exist_ok=True)
    with zipfile.ZipFile(ZIP_NAME, 'r') as z:
        z.extractall(DEST_DIR)

    # 3. Limpar
    if os.path.exists(ZIP_NAME):
        os.remove(ZIP_NAME)
        
    print(f"Sucesso! Python 32-bit pronto em: {os.path.abspath(DEST_DIR)}")
    print("Para usar, chame: python32_env/python.exe seu_script.py")

if __name__ == "__main__":
    setup_python32()
