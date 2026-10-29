#!/usr/bin/env python3
"""Test ELM327 K-Line protocols"""
import serial
import time
import sys

def test_protocol(port, protocol_num, baud=38400, timeout=1):
    """Test a specific ATSP protocol"""
    try:
        ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.3)
        
        # Set protocol
        cmd = f"ATSP{protocol_num}"
        ser.write((cmd + "\r").encode("ascii"))
        response = ""
        start = time.time()
        while time.time() - start < 2:
            if ser.in_waiting:
                c = ser.read(1).decode("ascii", errors="ignore")
                response += c
                if ">" in response:
                    break
        
        print(f"\n  ATSP{protocol_num}:")
        print(f"    Resposta: {response.strip()}")
        
        # Try to query OBD
        if "OK" in response or "?" not in response:
            print(f"    Testando 0100 (query PID)...")
            ser.write(("0100" + "\r").encode("ascii"))
            response = ""
            start = time.time()
            while time.time() - start < 3:
                if ser.in_waiting:
                    c = ser.read(1).decode("ascii", errors="ignore")
                    response += c
                    if ">" in response:
                        break
            
            result = response.strip()
            print(f"    Resultado: {result[:100]}")
            if "UNABLE" not in result and "ERROR" not in result:
                print(f"    ✓ Protocolo ATSP{protocol_num} SUCESSO!")
                return True
        
        ser.close()
        return False
        
    except Exception as e:
        print(f"  Erro: {e}")
        return False

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
    
    print(f"Testando protocolos K-Line em {port}...")
    print("=" * 50)
    
    for protocol in [3, 4, 5, 0]:
        if test_protocol(port, protocol):
            print(f"\n✓ Protocolo ATSP{protocol} está funcionando!")
            break
    
    print("\n" + "=" * 50)
