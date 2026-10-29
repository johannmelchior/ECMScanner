import socket
import struct
import random
import string
import os
import time

# IP REAL de brptuning.com
TARGET_HOST = '194.135.20.80' 
# Portas para verificar
TARGET_PORTS = [9005, 9001, 5555]

# Lista de seriais de interface para testar
INTERFACE_SERIALS = [
    "100123456",
    "100123457",
    "100123458", 
    "100123459",
]

# Lista de emails para testar em cada serial
TARGET_EMAILS = [
    "johannmelchior@gmail.com",
    "test@test.com",
    "admin@admin.com",
    "service@brp.com",
    "brp@brp.com"
]

def write_dotnet_string(sock, text):
    try:
        encoded = text.encode('utf-8')
        length = len(encoded)
        while length >= 0x80:
            sock.send(bytes([(length | 0x80) & 0xFF]))
            length >>= 7
        sock.send(bytes([length]))
        sock.send(encoded)
        return True
    except:
        return False

def generate_fake_hash():
    chars = string.ascii_uppercase + string.digits
    fake_serial = ''.join(random.choice(chars) for _ in range(20))
    hostname = "DESKTOP-" + ''.join(random.choice(chars) for _ in range(7))
    return f"{fake_serial}{hostname}"

def perform_handshake(sock):
    """Realiza o handshake inicial e retorna True se o servidor responder corretamente."""
    try:
        handshake_str = "BUDS2 License Client for DIUS platform"
        if not write_dotnet_string(sock, handshake_str):
            return False

        # Receber Resposta (Esperamos o byte de versão)
        ver_byte = sock.recv(1)
        if not ver_byte:
            return False
            
        if ver_byte == b'\x00':
            return True
        return False
    except:
        return False

def check_license(port, serial, email):
    print(f"\n[---] Verificando Serial {serial} na porta {port} [---]")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0) # Timeout um pouco maior
    
    try:
        sock.connect((TARGET_HOST, port))
        
        # 1. Handshake
        if not perform_handshake(sock):
            print("[-] Falha no Handshake.")
            return

        # 2. Enviar Dados Reais
        fake_hash = generate_fake_hash()
        
        # Format: Hash, Serial, Email, Name, Surname, Company, Phone, Lang
        user_data = f"{fake_hash},{serial},{email},Johann,Melchior,Tester,5511999999999,en"
        
        write_dotnet_string(sock, user_data)
        
        # 3. Receber Status
        status_byte = sock.recv(1)
        
        if not status_byte:
            print("[-] Sem resposta de status.")
            return
            
        if status_byte == b'\x00':
            print(f"!!! SUCESSO !!! Licença encontrada para serial {serial}")
            
            # 4. BAIXAR A LICENÇA
            len_bytes = sock.recv(4)
            license_len = struct.unpack('<I', len_bytes)[0]
            print(f"[<] Tamanho do arquivo: {license_len} bytes")
            
            content = b""
            while len(content) < license_len:
                chunk = sock.recv(license_len - len(content))
                if not chunk: break
                content += chunk
            
            # 5. SALVAR ARQUIVO
            # Caminho padrão onde o BUDS2 procura
            # Usando uma pasta diferente para cada serial para organizar
            save_dir = os.path.join(os.environ['USERPROFILE'], 'in2soft_license', serial)
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
                
            filename = f"license_{email}.xml.bin"
            save_path = os.path.join(save_dir, filename)
            
            with open(save_path, 'wb') as f:
                f.write(content)
                
            print(f"[+] LICENÇA SALVA EM: {save_path}")
            
        elif status_byte == b'\x82': # 130
            print(f"[-] REJEITADO (Código 130). Serial {serial} sem licença.")
        else:
            print(f"[-] Código desconhecido: {status_byte.hex()}")

    except ConnectionRefusedError:
        print(f"[-] Porta {port} fechada.")
    except socket.timeout:
        print(f"[-] Timeout.")
    except Exception as e:
        print(f"[-] Erro: {e}")
    finally:
        sock.close()

def scan_for_server():
    """Encontra qual porta é a do servidor de licenças."""
    print("Mapeando servidor...")
    for port in TARGET_PORTS:
        print(f"Testando porta {port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((TARGET_HOST, port))
            if perform_handshake(sock):
                print(f"[+] Servidor encontrado na porta {port}!")
                sock.close()
                return port
            sock.close()
        except:
            pass
    return None

if __name__ == "__main__":
    valid_port = scan_for_server()
    
    if valid_port:
        print(f"\nIniciando varredura de combinações na porta {valid_port}...")
        
        for serial in INTERFACE_SERIALS:
            print(f"\n>>> Testando Serial: {serial} <<<")
            for email in TARGET_EMAILS:
                print(f"    [Testando Email: {email}]")
                check_license(valid_port, serial, email)
                # Pequena pausa para evitar bloqueio
                time.sleep(0.5)
            
            # Pausa maior entre seriais
            time.sleep(2.0)
    else:
        print("[-] Não foi possível encontrar o servidor de licenças em nenhuma porta.")
