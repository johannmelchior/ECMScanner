import pefile
import os

DLL_PATH = r'c:\Users\johan\OneDrive\Documentos\projetoCAN\firmware-esp32-projetocan\original-software\BUDS2\lib\seed_key.dll'

if not os.path.exists(DLL_PATH):
    print(f"File not found: {DLL_PATH}")
    exit()

try:
    pe = pefile.PE(DLL_PATH)
    print(f"Architecture: {'64-bit' if pe.FILE_HEADER.Machine == 0x8664 else '32-bit'}")
    print(f"Time Date Stamp: {pe.FILE_HEADER.TimeDateStamp}")
    
    if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
        print("\nExports:")
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            print(f"  {exp.name.decode('utf-8', 'ignore')} (Ord: {exp.ordinal})")
    else:
        print("\nNo exports found.")

    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        print("\nImports:")
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            print(f"  {entry.dll.decode('utf-8', 'ignore')}")
            for imp in entry.imports:
                if imp.name:
                    print(f"    {imp.name.decode('utf-8', 'ignore')}")


except Exception as e:
    print(f"Error analyzing PE: {e}")
