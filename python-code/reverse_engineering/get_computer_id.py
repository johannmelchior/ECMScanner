import subprocess
import socket
import os

def get_wmi_property(class_name, property_name):
    try:
        # Usando PowerShell pois wmic pode estar ausente
        ps_cmd = f"Get-CimInstance {class_name} | Select-Object -ExpandProperty {property_name}"
        cmd = f"powershell -NoProfile -Command \"{ps_cmd}\""
        
        # Cria o processo evitando janelas pop-up
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.check_output(cmd, startupinfo=si).decode().strip()
        else:
            result = subprocess.check_output(cmd, shell=True).decode().strip()
            
        return result
    except Exception as e:
        print(f"Erro lendo {class_name}.{property_name}: {e}")
        return ""

def get_computer_hash():
    print("Gerando Computer ID (Hash) baseado no hardware local...")
    
    # 1. BIOS Serial
    # Class: Win32_BIOS
    bios_serial = get_wmi_property("Win32_BIOS", "SerialNumber")
    print(f"  [+] BIOS Serial: {bios_serial}")
    
    # 2. CPU ID
    # Class: Win32_Processor
    cpu_id = get_wmi_property("Win32_Processor", "ProcessorId")
    print(f"  [+] CPU ID:      {cpu_id}")
    
    # 3. Hostname
    hostname = socket.gethostname()
    print(f"  [+] Hostname:    {hostname}")
    
    # 4. BaseBoard Serial
    # Class: Win32_BaseBoard
    baseboard_serial = get_wmi_property("Win32_BaseBoard", "SerialNumber")
    print(f"  [+] MB Serial:   {baseboard_serial}")
    
    # Concatenação conforme engenharia reversa do BUDS2 Registrator
    # text += BIOS_SN
    # text += CPU_ID
    # text += Hostname
    # text += BaseBoard_SN
    
    computer_id = bios_serial + cpu_id + hostname + baseboard_serial
    
    print(f"\n>>> COMPUTER ID GERADO: {computer_id}\n")
    return computer_id

if __name__ == "__main__":
    get_computer_hash()
