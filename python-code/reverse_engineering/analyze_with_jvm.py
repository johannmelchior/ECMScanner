"""
analyze_with_jvm.py — Decripta a licença do BUDS2 usando a JVM real via jpype.

Chama diretamente as classes Java internas do BUDS2:
  - com.kpit.license.hardwareid.HardwareIdTool     → calcula hardware ID
  - com.kpit.license.decryption.DecryptionServiceImpl → derivação da chave
  - com.in2soft.licensemanager.converter.EMFFromSecXMLDataSource → decriptação

Para executar:
  python analyze_with_jvm.py

Alternativa com JVM específico:
  JAVA_HOME="C:/Program Files (x86)/BRP/BUDS2/jre" python analyze_with_jvm.py
"""

import os
import sys
import base64
import struct
import socket

# ── Configuração ──────────────────────────────────────────────────────────────

JRE_PATH = r"C:\Program Files (x86)\BRP\BUDS2\jre"
PLUGIN_DIR = r"C:\Program Files (x86)\BRP\BUDS2\plugins"

LICENSE_PATH = os.path.join(
    os.path.expanduser('~'), 'in2soft_license', '1225765425',
    'license_johannmelchior@gmail.com.xml.bin'
)

# JARs necessários para o classpath
REQUIRED_JARS = [
    "com.kpit.license_2.0.5.201710302306.jar",
    "com.in2soft.licensemanager.model_1.0.4.201710302304.jar",
    "com.kpit.license.auth_2.0.5.201710302306.jar",
    "com.in2soft.licensemanager.model.edit_1.0.4.201710302304.jar",
    "com.jacob_1.18.0.jar",  # Para WMI calls (pode não existir)
]

# Chave pública do servidor (do plugin.xml)
SERVER_PUBLIC_KEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAg73Ub97mESbgVZkharBX12oeg1/"
    "HRTWsn1RA1e/J0fIW7PNclPv/mPi87UJYjrJBzsJpqUZFWHb4gOPXxgRbtp11G3seYu320"
    "oWs68o2BkuEk/gAvEDk8rtzppBgnAbtDlxdX5/OrDq6cRBNTbLSEqIueprZzJ0P2EHsYSz"
    "5qKwxAkk9XmF69KV6GZdBSu+jSdrjji0mQfz4LtiwCRVJGcG7YhZmj7o2I7TSmJxSmTF74"
    "XZ2xZAn0pmQfnxyFN0bu6KI43HxOOZaP7E6Z45Msod/EYU5k8ENSRW21K04USXL8g48bEB"
    "YIjgwGMOUsyFt8fzN06tgssKP/2lYUjJamQIDAQAB"
)


def java_string_hashcode(s: str) -> int:
    """Replica Java String.hashCode()."""
    h = 0
    for c in s:
        h = (31 * h + ord(c)) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def get_wmi_value(wmi_class: str, prop: str) -> str:
    import subprocess
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        cmd = f'Get-CimInstance {wmi_class} | Select-Object -ExpandProperty {prop}'
        out = subprocess.check_output(
            ['powershell', '-NoProfile', '-Command', cmd],
            startupinfo=si, stderr=subprocess.DEVNULL
        )
        return out.decode('utf-8', errors='replace').strip()
    except Exception:
        return ""


def compute_hardware_id() -> int:
    bios  = get_wmi_value("Win32_BIOS",      "SerialNumber")
    cpu   = get_wmi_value("Win32_Processor", "ProcessorId")
    mb    = get_wmi_value("Win32_BaseBoard",  "SerialNumber")
    host  = socket.gethostname()
    combined = bios + cpu + mb + host
    hw_int = java_string_hashcode(combined)
    print(f"  Hardware ID: {hw_int} (seed: '{hw_int}')")
    return hw_int


def run_with_jpype():
    """Usa jpype para chamar a JVM do BUDS2 e executar a decriptação real."""
    import jpype
    import jpype.imports

    # Montar classpath
    jars = []
    for jar_name in REQUIRED_JARS:
        jar_path = os.path.join(PLUGIN_DIR, jar_name)
        if os.path.isfile(jar_path):
            jars.append(jar_path)
        else:
            print(f"  [!] JAR não encontrado (ignorado): {jar_name}")

    if not jars:
        print("[-] Nenhum JAR encontrado!")
        return False

    jvm_path = os.path.join(JRE_PATH, "bin", "server", "jvm.dll")
    if not os.path.isfile(jvm_path):
        jvm_path = os.path.join(JRE_PATH, "bin", "client", "jvm.dll")
    if not os.path.isfile(jvm_path):
        jvm_path = jpype.getDefaultJVMPath()

    print(f"\n[*] Iniciando JVM: {jvm_path}")
    print(f"[*] Classpath: {len(jars)} JARs")

    classpath = os.pathsep.join(jars)
    jpype.startJVM(jvm_path, f"-Djava.class.path={classpath}", convertStrings=True)

    try:
        # Importar classes Java
        from jpype import JClass, JArray, JByte

        # 1. Computar hardware ID usando Java diretamente
        print("\n[*] Testando SHA1PRNG com hardware ID Python...")
        hw_int = compute_hardware_id()

        # 2. Usar Java SecureRandom diretamente via jpype
        SecureRandom = JClass("java.security.SecureRandom")
        KeyPairGenerator = JClass("java.security.KeyPairGenerator")
        String = JClass("java.lang.String")

        seed_str  = str(hw_int)
        seed_bytes = list(seed_str.encode('ascii'))

        random = SecureRandom.getInstance("SHA1PRNG")
        random.setSeed(bytes(seed_bytes))

        keyGen = KeyPairGenerator.getInstance("RSA")
        keyGen.initialize(2048, random)
        keyPair = keyGen.generateKeyPair()

        pubKey_hw = keyPair.getPublic()
        privKey_hw = keyPair.getPrivate()

        pub_encoded = bytes(pubKey_hw.getEncoded())
        print(f"[+] Par RSA gerado! Chave pública HW (primeiros 20 bytes): {pub_encoded[:20].hex()}")

        # 3. Carregar e decriptar o arquivo de licença
        print(f"\n[*] Decriptando licença: {LICENSE_PATH}")

        FileHelper = None
        EMFSource = None
        try:
            EMFSource = JClass("com.in2soft.licensemanager.converter.EMFFromSecXMLDataSource")
        except Exception as e:
            print(f"[!] EMFFromSecXMLDataSource não carregado: {e}")

        # Ler arquivo de licença
        with open(LICENSE_PATH, 'r') as f:
            license_str = f.read().strip()
        print(f"[+] Licença lida: {len(license_str)} chars")

        if EMFSource:
            # Carregar chave pública do servidor
            Base64Class = JClass("org.eclipse.osgi.internal.signedcontent.Base64")
            KeyFactory = JClass("java.security.KeyFactory")
            X509EncodedKeySpec = JClass("java.security.spec.X509EncodedKeySpec")

            import base64 as py_base64
            server_pub_der = list(py_base64.b64decode(SERVER_PUBLIC_KEY_B64))
            server_pub_spec = X509EncodedKeySpec(bytes(server_pub_der))
            kf = KeyFactory.getInstance("RSA")
            serverPubKey = kf.generatePublic(server_pub_spec)

            # Criar instância do EMFFromSecXMLDataSource
            # Constructor: (String licenseXML, boolean encrypted, boolean signed, boolean base64encoded)
            source = EMFSource(license_str, True, True, True)
            source.setPublicKey(serverPubKey)
            source.setPrivateKey(privKey_hw)

            print("[*] Executando getGrantedLicensesConverted()...")
            try:
                granted = source.getGrantedLicensesConverted()
                if granted is not None:
                    print(f"\n[✓✓✓] SUCCESSO! Licença decriptada!")
                    print(f"      Tipo: {type(granted)}")
                    print(f"      String: {str(granted)}")
                    
                    # Tentar obter features
                    try:
                        features = granted.getFeature()
                        print(f"      Features: {features}")
                    except Exception:
                        pass
                else:
                    print("[-] getGrantedLicensesConverted() retornou null")
            except Exception as e:
                print(f"[-] Decriptação falhou: {e}")

        # 4. Análise do formato do arquivo (Python puro)
        print("\n[*] Análise do formato do arquivo (Python puro)...")
        analyze_binary_format(license_str, bytes(privKey_hw.getEncoded()))

        return True

    except Exception as e:
        import traceback
        print(f"[-] Erro na JVM: {e}")
        traceback.print_exc()
        return False
    finally:
        if jpype.isJVMStarted():
            jpype.shutdownJVM()


def analyze_binary_format(license_b64: str, priv_key_der: bytes):
    """Analisa e tenta decriptar o formato binário usando pycryptodome."""
    from Crypto.PublicKey import RSA
    from Crypto.Signature import pkcs1_15
    from Crypto.Hash import SHA1
    from Crypto.Cipher import PKCS1_v1_5

    decoded = base64.b64decode(license_b64)
    print(f"  Total bytes: {len(decoded)}")

    # Parse header
    version = struct.unpack('>I', decoded[0:4])[0]
    block_len = struct.unpack('>I', decoded[4:8])[0]
    print(f"  Version: {version}")
    print(f"  Block1 length: {block_len} bytes")

    if block_len > 0 and 8 + block_len <= len(decoded):
        block1 = decoded[8 : 8 + block_len]
        rest   = decoded[8 + block_len :]
        print(f"  Block1 ({block_len} bytes): {block1[:16].hex()}...")
        print(f"  Rest ({len(rest)} bytes): {rest[:16].hex()}...")

        # Carregar chave privada derivada
        priv_key = RSA.import_key(priv_key_der)
        print(f"\n  Chave privada RSA: {priv_key.size_in_bits()} bits")

        # Tentar decriptar block1 com PKCS1 v1.5
        print("  Tentando decriptar block1 com RSA/PKCS1v1.5...")
        try:
            cipher = PKCS1_v1_5.new(priv_key)
            sentinel = b'\x00' * 32
            plaintext = cipher.decrypt(block1, sentinel)
            if plaintext != sentinel:
                print(f"  [+] Block1 DECRIPTADO ({len(plaintext)} bytes): {plaintext[:64].hex()}")
                try:
                    print(f"      ASCII: {plaintext[:64].decode('utf-8', errors='replace')!r}")
                except Exception:
                    pass
            else:
                print("  [-] Decriptação falhou (sentinel retornado)")
        except Exception as e:
            print(f"  [-] Erro: {e}")

        # Verificar assinatura
        print("  Tentando verificar assinatura SHA1withRSA (block1=assinatura, rest=dados)...")
        try:
            server_pub = RSA.import_key(base64.b64decode(SERVER_PUBLIC_KEY_B64))
            h = SHA1.new(rest[:min(len(rest), 10000)])
            pkcs1_15.verify(h, block1)
            print("  [+] Assinatura VÁLIDA!")
        except Exception as e:
            print(f"  [-] Verificação falhou (tentativa 1): {e}")

        # Tentar com block1 como dados e rest como assinatura
        print("  Tentando com block1=dados, rest=assinatura...")
        if len(rest) >= 256:
            try:
                sig_candidate = rest[:256]
                data_candidate = block1
                server_pub = RSA.import_key(base64.b64decode(SERVER_PUBLIC_KEY_B64))
                h = SHA1.new(data_candidate)
                pkcs1_15.verify(h, sig_candidate)
                print("  [+] Assinatura VÁLIDA! (block1=dados, rest[:256]=assinatura)")
            except Exception as e:
                print(f"  [-] Verificação falhou (tentativa 2): {e}")


def main():
    print("=" * 60)
    print(" BUDS2 License JVM Decriptor")
    print(" jpype + BUDS2 JRE")
    print("=" * 60)

    try:
        import jpype
        success = run_with_jpype()
        if not success:
            print("\n[!] Falha na execução via JVM.")
    except ImportError:
        print("[-] jpype não instalado: pip install jpype1")


if __name__ == "__main__":
    main()
