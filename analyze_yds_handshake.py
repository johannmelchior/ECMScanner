#!/usr/bin/env python3
"""
Analyze YDS handshake and ECM response using pcapng file.
Focus: TX vs RX timing, first commands, error detection.
"""
import subprocess
import sys
import json
from pathlib import Path
from collections import defaultdict
import re

def extract_ftdi_packets(pcap_file):
    """Extract all FTDI RX/TX packets from pcapng using tshark."""
    tshark = r'C:\Program Files\Wireshark\tshark.exe'
    
    # Extract RX packets (device -> host)
    cmd_rx = [
        tshark, '-r', str(pcap_file),
        '-Y', 'ftdi-ft.if_a_rx_payload',
        '-T', 'fields',
        '-E', 'separator=,',
        '-E', 'quote=n',
        '-e', 'frame.number',
        '-e', 'frame.time_relative',
        '-e', 'ftdi-ft.line_status',
        '-e', 'ftdi-ft.if_a_rx_payload'
    ]
    
    # Extract TX packets (host -> device)
    cmd_tx = [
        tshark, '-r', str(pcap_file),
        '-Y', 'ftdi-ft.if_a_tx_payload',
        '-T', 'fields',
        '-E', 'separator=,',
        '-E', 'quote=n',
        '-e', 'frame.number',
        '-e', 'frame.time_relative',
        '-e', 'ftdi-ft.if_a_tx_payload'
    ]
    
    rx_lines = subprocess.check_output(cmd_rx, text=True).strip().split('\n')
    tx_lines = subprocess.check_output(cmd_tx, text=True).strip().split('\n')
    
    rx = []
    for line in rx_lines:
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) >= 4 and parts[3]:
            rx.append({
                'frame': int(parts[0]),
                'time': float(parts[1]),
                'line_status': parts[2],
                'payload': parts[3].upper(),
                'pkt_len': len(parts[3]) // 2
            })
    
    tx = []
    for line in tx_lines:
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) >= 3 and parts[2]:
            tx.append({
                'frame': int(parts[0]),
                'time': float(parts[1]),
                'payload': parts[2].upper(),
                'pkt_len': len(parts[2]) // 2
            })
    
    return sorted(rx, key=lambda x: x['time']), sorted(tx, key=lambda x: x['time'])

def analyze_handshake(rx, tx):
    """Analyze first exchange between YDS and ECM."""
    print("=" * 80)
    print("YDS HANDSHAKE ANALYSIS")
    print("=" * 80)
    print()
    
    if not tx:
        print("[!] NO TX PACKETS FOUND - YDS may not have written to COM10")
        print()
    else:
        print(f"[+] Total TX packets: {len(tx)}")
        print(f"[+] Total RX packets: {len(rx)}")
        print()
        
        # First TX from YDS
        first_tx = tx[0]
        print(f"[TX] First YDS command at t={first_tx['time']:.3f}s, frame {first_tx['frame']}")
        print(f"     Payload ({first_tx['pkt_len']} bytes): {first_tx['payload']}")
        print(f"     ASCII: {decode_ascii(first_tx['payload'])}")
        print()
        
        # First RX after YDS TX
        first_rx_after_tx = None
        for r in rx:
            if r['time'] > first_tx['time']:
                first_rx_after_tx = r
                break
        
        if first_rx_after_tx:
            gap = first_rx_after_tx['time'] - first_tx['time']
            print(f"[RX] First ECM response at t={first_rx_after_tx['time']:.3f}s (gap={gap*1000:.1f}ms), frame {first_rx_after_tx['frame']}")
            print(f"     Payload ({first_rx_after_tx['pkt_len']} bytes): {first_rx_after_tx['payload']}")
            print()
        else:
            print("[!] NO RX FOUND after first TX!")
            print()
    
    # Byte-level analysis
    print("=" * 80)
    print("BYTE PATTERNS IN TX")
    print("=" * 80)
    
    all_tx_bytes = ''.join([p['payload'] for p in tx])
    
    patterns = [
        ('1C FD FD FD', '1CFDFDFD'),  # YDS init
        ('1C FD', '1CFD'),             # YDS command
        ('FD', 'FD'),                  # TesterPresent
        ('00', '00'),                  # ACK
    ]
    
    for name, pat in patterns:
        count = len(re.findall(pat, all_tx_bytes)) // 2 if len(pat) > 2 else all_tx_bytes.count(pat)
        print(f"  {name:20} : {count}")
    
    print()
    print("=" * 80)
    print("BYTE PATTERNS IN RX")
    print("=" * 80)
    
    all_rx_bytes = ''.join([p['payload'] for p in rx])
    
    patterns_rx = [
        ('E0/E3 stream', 'E0|E3'),
        ('60/63 stream', '60|63'),
        ('F0/7C', 'F0|7C'),
        ('20', '20'),
    ]
    
    for name, pat in patterns_rx:
        count = len(re.findall(pat, all_rx_bytes))
        print(f"  {name:20} : {count}")
    
    print()
    
    # Timeline
    print("=" * 80)
    print("TIMELINE (First 10 packets)")
    print("=" * 80)
    print()
    
    all_packets = []
    for r in rx:
        all_packets.append(('RX', r['time'], r['frame'], r['pkt_len'], r['payload'][:16]))
    for t in tx:
        all_packets.append(('TX', t['time'], t['frame'], t['pkt_len'], t['payload'][:16]))
    
    all_packets.sort(key=lambda x: x[1])
    
    for dir, time, frame, pkt_len, payload in all_packets[:20]:
        print(f"  {time:8.3f}s  [{dir}] frame {frame:4d}  {pkt_len:2d} bytes  {payload}")
    
    print()

def decode_ascii(hex_str):
    """Try to decode hex as ASCII, show printable chars."""
    result = []
    for i in range(0, len(hex_str), 2):
        byte = int(hex_str[i:i+2], 16)
        if 32 <= byte < 127:
            result.append(chr(byte))
        else:
            result.append(f'[{hex_str[i:i+2]}]')
    return ''.join(result)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyze_yds_handshake.py <pcapng_file>")
        sys.exit(1)
    
    pcap = Path(sys.argv[1])
    if not pcap.exists():
        print(f"Error: {pcap} not found")
        sys.exit(1)
    
    print(f"\nAnalyzing: {pcap}")
    print()
    
    rx, tx = extract_ftdi_packets(pcap)
    analyze_handshake(rx, tx)
