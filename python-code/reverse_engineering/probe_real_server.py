import socket
import struct
import random
import string

# IP REAL de brptuning.com
TARGET_HOST = '194.135.20.80' 
# Portas para verificar (9005 é a original, mas seu scan mostrou 9001 e 5555 abertas)
TARGET_PORTS = [9005, 9001]

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

def probe_port(port):
    print(f"\n[---] Sondando Porta {port} em {TARGET_HOST} [---]")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    
    try:
        print(f"[*] Conectando...")
        sock.connect((TARGET_HOST, port))
        print(f"[+] Conexão TCP estabelecida na porta {port}!")
        
        # 1. Tentar enviar Handshake
        handshake_str = "BUDS2 License Client for DIUS platform"
        print(f"[>] Enviando Handshake BUDS2...")
        if not write_dotnet_string(sock, handshake_str):
            print("[-] Falha ao enviar dados.")
            return

        # 2. Receber Resposta (Esperamos o byte de versão)
        print("[*] Aguardando resposta...")
        try:
            ver_byte = sock.recv(1)
        except socket.timeout:
            print("[-] Timeout aguardando resposta (O serviço pode não ser o de licenças).")
            return
            
        if not ver_byte:
            print("[-] Servidor fechou a conexão após o handshake.")
            return

        print(f"[<] Resposta recebida: {ver_byte.hex()}")
        
        if ver_byte == b'\x00':
            print("!!! ENCONTRADO !!! O serviço nesta porta respondeu como o servidor de licenças!")
        else:
            print(f"[-] A resposta {ver_byte.hex()} não é a esperada (0x00). Provavelmente outro serviço.")
            return

        # 3. Enviar Dados Reais
        fake_email = "johannmelchior@gmail.com"
        fake_serial = "100123456" 
        fake_hash = generate_fake_hash()
        
        # Format: Hash, Serial, Email, Name, Surname, Company, Phone, Lang
        user_data = f"{fake_hash},{fake_serial},{fake_email},Johann,Melchior,Tester,5511999999999,en"
        
        print(f"[>] Enviando dados REAIS ({fake_email}): {user_data}")
        write_dotnet_string(sock, user_data)
        
        # 4. Receber Status
        print("[*] Aguardando status da licença...")
        status_byte = sock.recv(1)
        
        if not status_byte:
            print("[-] Sem resposta de status.")
            return
            
        print(f"[<] Status recebido: {status_byte.hex()} (Decimal: {status_byte[0]})")
        
        if status_byte == b'\x00':
            print("    -> SUCESSO! A licença foi encontrada (Incrivelmente).")
            
            # 5. BAIXAR A LICENÇA
            print("[*] Lendo tamanho da licença...")
            len_bytes = sock.recv(4)
            license_len = struct.unpack('<I', len_bytes)[0]
            print(f"[<] Tamanho do arquivo: {license_len} bytes")
            
            print(f"[*] Baixando conteúdo...")
            content = b""
            while len(content) < license_len:
                chunk = sock.recv(license_len - len(content))
                if not chunk: break
                content += chunk
            
            # 6. SALVAR ARQUIVO
            import os
            # Caminho padrão onde o BUDS2 procura
            save_dir = os.path.join(os.environ['USERPROFILE'], 'in2soft_license', '1225765425')
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
                
            filename = f"license_{fake_email}.xml.bin"
            save_path = os.path.join(save_dir, filename)
            
            with open(save_path, 'wb') as f:
                f.write(content)
                
            print(f"\n[+] LICENÇA SALVA EM: {save_path}")
            print(f"[+] Agora você pode rodar o BUDS2 original!")
            
            # Mostra preview
            try:
                print(f"[Preview] Primeiros 100 chars:\n{content[:100].decode(errors='ignore')}")
            except: pass
            
        elif status_byte == b'\x82': # 130
            print("    -> REJEITADO (Código 130). O email ou serial não têm licença válida.")
        else:
            print(f"    -> Código desconhecido: {status_byte.hex()}")


    except ConnectionRefusedError:
        print(f"[-] Porta {port} fechada (recusou conexão).")
    except socket.timeout:
        print(f"[-] Timeout conectando na porta {port}.")
    except Exception as e:
        print(f"[-] Erro: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    for port in TARGET_PORTS:
        probe_port(port)

