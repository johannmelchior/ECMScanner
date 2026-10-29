#!/usr/bin/env python3
"""Quick ELM327 test - minimal communication"""
import serial
import time
import sys

def quick_test(port, baud=38400, timeout=0.5):
    try:
        print(f"Conectando em {port} @ {baud} baud...")
        ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.5)
        
        # Test basic commands
        commands = [
            ("ATZ", "Reset"),
            ("ATE0", "Echo OFF"),
            ("ATL0", "Headers OFF"), 
            ("ATS0", "Spaces OFF"),
            ("ATH1", "Headers ON"),
            ("ATDPN", "Show Protocol"),
        ]
        
        for cmd, description in commands:
            print(f"\n> {cmd} ({description})")
            ser.write((cmd + "\r").encode("ascii"))
            response = ""
            start = time.time()
            while time.time() - start < 1.0:
                if ser.in_waiting:
                    response += ser.read(1).decode("ascii", errors="ignore")
                    if ">" in response:
                        break
            print(f"  {response.strip()}")
        
        ser.close()
        print("\n✓ ELM327 testado com sucesso em", port)
        return True
        
    except Exception as e:
        print(f"✗ Erro em {port}: {e}")
        return False

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
    quick_test(port)
