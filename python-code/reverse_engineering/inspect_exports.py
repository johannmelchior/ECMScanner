import pefile
import os

DLL_PATH = 'original-software/BUDS2/PDSEncryption_unpacked.dll'

def list_exports():
    if not os.path.exists(DLL_PATH):
        print(f"Arquivo não encontrado: {DLL_PATH}")
        return

    print(f"Analisando exportações de: {DLL_PATH}")
    try:
        pe = pefile.PE(DLL_PATH)
        
        if not hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
            print("A DLL não possui tabela de exportação (Export Directory).")
            return

        print("\n--- Funções Exportadas ---")
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            ordinal = exp.ordinal
            name = exp.name.decode('utf-8') if exp.name else f"Ordinal_{ordinal}"
            address = hex(pe.OPTIONAL_HEADER.ImageBase + exp.address)
            print(f"[{ordinal}] {name} @ {address}")
            
    except Exception as e:
        print(f"Erro ao analisar PE: {e}")

if __name__ == '__main__':
    list_exports()
