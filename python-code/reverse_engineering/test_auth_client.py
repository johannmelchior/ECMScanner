import socket
import struct
import random
import string

# Configurações do Alvo (Pode ser localhost ou o IP real se remover do hosts)
TARGET_HOST = 'brptuning.com' 
TARGET_PORT = 9005

def write_dotnet_string(sock, text):
    """
    Simula o BinaryWriter.Write(String) do .NET.
    Escreve o tamanho da string codificado em 7-bit integer, seguido pelos bytes UTF-8.
    """
    encoded = text.encode('utf-8')
    length = len(encoded)
    
    # Lógica do 7-bit encoded int para o tamanho
    while length >= 0x80:
        sock.send(bytes([(length | 0x80) & 0xFF]))
        length >>= 7
    sock.send(bytes([length]))
    
    # Envia o conteúdo
    sock.send(encoded)

def generate_fake_hash():
    """Gera um Hash simulado parecido com o gerado pelo Hardware ID (BIOS+CPU+Baseboard)"""
    # Formato observado geralmente é uma "tripa" de seriais concatenados
    # Exemplo fictício: "BFEBFBFF000406F1SerialNumber12345Hostname"
    chars = string.ascii_uppercase + string.digits
    fake_serial = ''.join(random.choice(chars) for _ in range(20))
    hostname = "DESKTOP-" + ''.join(random.choice(chars) for _ in range(7))
    return f"{fake_serial}{hostname}"

def test_authentication(email="teste@email.com", serial="100123456"):
    print(f"\n[---] Iniciando teste de autenticação para: {email} (Serial: {serial}) [---]")
    print(f"[*] Conectando em {TARGET_HOST}:{TARGET_PORT}...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0) # Timeout de 5s
    
    try:
        sock.connect((TARGET_HOST, TARGET_PORT))
        print("[+] Conectado!")
        
        # 1. Enviar Handshake
        handshake_str = "BUDS2 License Client for DIUS platform"
        print(f"[>] Enviando Handshake: '{handshake_str}'")
        write_dotnet_string(sock, handshake_str)
        
        # 2. Receber Confirmação de Versão
        ver_byte = sock.recv(1)
        if not ver_byte:
            print("[-] Conexão fechada pelo servidor antes da resposta de versão.")
            return

        if ver_byte == b'\x00':
            print("[<] Resposta de Versão: OK (0x00)")
        else:
            print(f"[-] Resposta de Versão INESPERADA: {ver_byte.hex()} (Esperado 0x00)")
            # Nota: O cliente oficial fecha se não for 0, mas vamos continuar para ver o que acontece
        
        # 3. Montar e Enviar Dados do Cliente
        # Formato: Hash, Serial, Email, Nome, Sobrenome, Empresa, Telefone, Idioma
        fake_hash = generate_fake_hash()
        user_data = f"{fake_hash},{serial},{email},Tester,Silva,HackLab,5511999999999,pt"
        
        print(f"[>] Enviando Dados do Cliente: '{user_data}'")
        write_dotnet_string(sock, user_data)
        
        # 4. Receber Status da Licença
        status_byte = sock.recv(1)
        if not status_byte:
            print("[-] Sem resposta de status.")
            return
            
        print(f"[<] Byte de Status Recebido: {status_byte.hex()}")
        
        if status_byte == b'\x00':
            print("[+] SUCESSO! O servidor aceitou e vai enviar a licença.")
            
            # 5. Ler Tamanho da Licença (Int32 Little Endian)
            len_data = sock.recv(4)
            if len(len_data) < 4:
                print("[-] Erro ao ler tamanho da licença.")
                return
                
            license_size = struct.unpack('<I', len_data)[0]
            print(f"[<] Tamanho da Licença: {license_size} bytes")
            
            # 6. Ler Conteúdo
            content = b""
            while len(content) < license_size:
                chunk = sock.recv(license_size - len(content))
                if not chunk: break
                content += chunk
                
            print("\n[+] --- CONTEÚDO DA LICENÇA RECEBIDA ---")
            try:
                print(content.decode(errors='ignore'))
            except:
                print(content.hex())
            print("[+] ------------------------------------\n")
            
        elif status_byte == b'\x82': # 130 decimal
            print("[-] ERRO: Licença não encontrada (Código 130/0x82).")
            print("    Isso significa que o servidor rejeitou o Email ou o Serial.")
        else:
            print(f"[-] Código de Status Desconhecido: {status_byte[0]}")
            
    except ConnectionRefusedError:
        print("[-] Falha na conexão: Servidor recusou ou não está rodando.")
    except socket.timeout:
        print("[-] Timeout: O servidor parou de responder.")
    except Exception as e:
        print(f"[-] Exceção: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    # Teste 1: Tenta com o nosso serial de bypass
    test_authentication(email="bypass@teste.com", serial="100123456")
    
    # Teste 2: Tenta com um serial qualquer para ver se o servidor rejeita (se fosse o real)
    # test_authentication(email="falha@teste.com", serial="UNKNOWN123")
