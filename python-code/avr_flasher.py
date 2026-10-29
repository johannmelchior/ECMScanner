#!/usr/bin/env python3
"""
avr_flasher.py — Uploader de firmware para ATmega162 via bootloader FT245
==========================================================================
Usa o mesmo protocolo SYNC/LEN/CMD/PAYLOAD/XOR do firmware principal.
Não precisa de ICSP — conecta pela porta USB normal.

Uso básico:
    python avr_flasher.py --port COM5 --hex build/firmware_avr.hex

Opções:
    --port PORT         Porta serial (ex: COM5)
    --baud BAUD         Velocidade (padrão: 500000)
    --hex FILE          Arquivo Intel HEX para gravar
    --verify            Faz leitura e verificação CRC após gravação (padrão: sim)
    --no-verify         Pula verificação
    --jump              Salta para aplicação após gravação
    --info              Apenas mostra informações do bootloader e sai
    --timeout SECS      Timeout de entrada no bootloader (padrão: 3.0s)
"""

import argparse
import struct
import sys
import time
from pathlib import Path

import serial

# ---------------------------------------------------------------------------
# Constantes de protocolo
# ---------------------------------------------------------------------------
SYNC = 0x5A
MAX_PAYLOAD = 31

BL_CMD_GET_INFO   = 0x70
BL_CMD_ERASE_APP  = 0x71
BL_CMD_WRITE_PAGE = 0x72
BL_CMD_READ_PAGE  = 0x73
BL_CMD_VERIFY_CRC = 0x74
BL_CMD_JUMP_APP   = 0x75

# Comando do firmware principal para disparar WDT reset (entra no bootloader)
CMD_APP_REBOOT    = 0x05

RSP_OK  = 0xA5
RSP_ERR = 0x7F

FLASH_PAGE_BYTES = 128
CHUNK_DATA_SIZE  = 28   # 31 (BL_MAX_PAYLOAD) − 3 bytes de header (page, offset, size)


# ---------------------------------------------------------------------------
# Protocolo
# ---------------------------------------------------------------------------

def _checksum(length: int, cmd: int, payload: bytes) -> int:
    cs = length ^ cmd
    for b in payload:
        cs ^= b
    return cs & 0xFF


def send_packet(ser: serial.Serial, cmd: int, payload: bytes = b"") -> None:
    frame = bytes([SYNC, len(payload), cmd]) + payload + bytes([_checksum(len(payload), cmd, payload)])
    ser.write(frame)


def recv_packet(ser: serial.Serial, timeout: float = 2.0) -> tuple[int, bytes]:
    """Retorna (cmd, payload) ou lança TimeoutError."""
    state = "sync"
    payload_len = 0
    cmd = 0
    payload = bytearray()
    cs_running = 0
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        raw = ser.read(1)
        if not raw:
            continue
        b = raw[0]

        if state == "sync":
            if b == SYNC:
                state = "len"
        elif state == "len":
            payload_len = b
            cs_running = b
            payload.clear()
            state = "cmd"
        elif state == "cmd":
            cmd = b
            cs_running ^= b
            state = "payload" if payload_len else "checksum"
        elif state == "payload":
            payload.append(b)
            cs_running ^= b
            if len(payload) >= payload_len:
                state = "checksum"
        elif state == "checksum":
            if b == cs_running:
                return cmd, bytes(payload)
            # checksum ruim — reinicia
            state = "sync"

    raise TimeoutError(f"Timeout aguardando resposta do bootloader (cmd={cmd:#04x})")


def request(ser: serial.Serial, cmd: int, payload: bytes = b"", timeout: float = 5.0) -> bytes:
    send_packet(ser, cmd, payload)
    rcmd, rpayload = recv_packet(ser, timeout=timeout)
    if rcmd != cmd:
        raise RuntimeError(f"Resposta inesperada: cmd={rcmd:#04x}, esperado={cmd:#04x}")
    if not rpayload or rpayload[0] == RSP_ERR:
        raise RuntimeError(f"Bootloader retornou RSP_ERR para cmd={cmd:#04x}")
    return rpayload


# ---------------------------------------------------------------------------
# Parsing Intel HEX
# ---------------------------------------------------------------------------

def parse_hex(path: str) -> dict[int, bytes]:
    """
    Retorna dict {byte_address: bytes} com todos os registros de dados.
    Suporta HEX tipo I8HEX (32KB max para ATmega162).
    """
    segments: dict[int, bytearray] = {}
    base = 0

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            data = bytes.fromhex(line[1:])
            bc   = data[0]  # byte count
            addr = (data[1] << 8) | data[2]
            rtype = data[3]

            if rtype == 0x00:  # data
                abs_addr = base + addr
                if abs_addr not in segments:
                    segments[abs_addr] = bytearray()
                segments[abs_addr].extend(data[4 : 4 + bc])
            elif rtype == 0x02:  # extended segment address
                base = ((data[4] << 8) | data[5]) << 4
            elif rtype == 0x04:  # extended linear address
                base = ((data[4] << 8) | data[5]) << 16
            elif rtype == 0x01:  # EOF
                break

    return {addr: bytes(data) for addr, data in segments.items()}


def hex_to_pages(hex_path: str, page_size: int = FLASH_PAGE_BYTES) -> dict[int, bytes]:
    """
    Converte um HEX em um dict {page_number: bytes(page_size)}.
    Páginas não presentes no HEX são preenchidas com 0xFF.
    """
    segments = parse_hex(hex_path)

    # Achata em flat array
    flat: dict[int, int] = {}
    for addr, data in segments.items():
        for i, b in enumerate(data):
            flat[addr + i] = b

    if not flat:
        return {}

    max_addr = max(flat.keys())
    pages: dict[int, bytes] = {}

    for addr, b in flat.items():
        page_num = addr // page_size
        off      = addr % page_size
        if page_num not in pages:
            pages[page_num] = bytearray([0xFF] * page_size)
        pages[page_num][off] = b  # type: ignore[index]

    return {p: bytes(d) for p, d in pages.items()}


# ---------------------------------------------------------------------------
# CRC16-CCITT (para verificação)
# ---------------------------------------------------------------------------

def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
        crc &= 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Operações de alto nível
# ---------------------------------------------------------------------------

def bl_get_info(ser: serial.Serial) -> dict:
    payload = request(ser, BL_CMD_GET_INFO, timeout=3.0)
    # RSP_OK | version | page_size_L | page_size_H | app_pages | boot_start_L | boot_start_H
    if len(payload) < 7:
        raise RuntimeError(f"GET_INFO: resposta truncada ({payload.hex()})")
    return {
        "version":    payload[1],
        "page_size":  payload[2] | (payload[3] << 8),
        "app_pages":  payload[4],
        "boot_start": payload[5] | (payload[6] << 8),
    }


def bl_enter(ser: serial.Serial, timeout: float = 3.0) -> dict:
    """
    Envia BL_GET_INFO repetidamente até resposta (bootloader em janela de ~2s).
    Retorna info do bootloader ou lança TimeoutError.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            send_packet(ser, BL_CMD_GET_INFO)
            _, rpayload = recv_packet(ser, timeout=0.3)
            if rpayload and rpayload[0] == RSP_OK and len(rpayload) >= 7:
                return {
                    "version":    rpayload[1],
                    "page_size":  rpayload[2] | (rpayload[3] << 8),
                    "app_pages":  rpayload[4],
                    "boot_start": rpayload[5] | (rpayload[6] << 8),
                }
        except (TimeoutError, RuntimeError):
            pass
        time.sleep(0.05)
    raise TimeoutError("Bootloader não respondeu. Verifique se o AVR foi resetado e a porta está correta.")


def _app_reboot(ser: serial.Serial) -> bool:
    """
    Envia CMD_REBOOT (0x05) ao firmware principal.
    O firmware pode estar emitindo bytes de debug fora do enquadramento, então
    não dependemos de ACK para prosseguir com a troca para o bootloader.
    """
    try:
        send_packet(ser, CMD_APP_REBOOT)
        ser.flush()
        return True
    except (serial.SerialException, OSError):
        pass
    return False


def bl_erase(ser: serial.Serial) -> None:
    print("  Apagando flash da aplicação...", end=" ", flush=True)
    request(ser, BL_CMD_ERASE_APP, timeout=15.0)
    print("OK")


def bl_write_pages(ser: serial.Serial, pages: dict[int, bytes], app_max_page: int, page_size: int) -> int:
    """Grava as páginas. Retorna total de bytes gravados."""
    total_pages = len(pages)
    written = 0
    written_bytes = 0

    for page_num in sorted(pages.keys()):
        if page_num >= app_max_page:
            print(f"  AVISO: página {page_num} fora da área de aplicação — ignorada")
            continue

        page_data = pages[page_num]
        assert len(page_data) == page_size

        # Envia a página em chunks de CHUNK_DATA_SIZE bytes
        offset = 0
        while offset < page_size:
            chunk = page_data[offset: offset + CHUNK_DATA_SIZE]
            payload = bytes([page_num, offset, len(chunk)]) + chunk
            request(ser, BL_CMD_WRITE_PAGE, payload, timeout=5.0)
            offset += len(chunk)

        written += 1
        written_bytes += page_size
        pct = int(written * 100 / total_pages)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  Gravando  [{bar}] {pct:3d}%  (pág {page_num:02d}/{app_max_page - 1:02d})", end="", flush=True)

    print(f"\r  Gravando  [{'█'*20}] 100%  ({written} páginas, {written_bytes} bytes)        ")
    return written_bytes


def bl_verify(ser: serial.Serial, pages: dict[int, bytes], app_max_page: int, page_size: int) -> bool:
    """Verifica CRC16 página a página."""
    errors = 0
    total = sum(1 for p in pages if p < app_max_page)
    checked = 0

    for page_num in sorted(pages.keys()):
        if page_num >= app_max_page:
            continue

        expected_data = pages[page_num]
        byte_addr = page_num * page_size
        expected_crc = crc16(expected_data)

        payload = struct.pack("<HHH", byte_addr, page_size, expected_crc)
        try:
            # Usa send/recv diretamente — request() lança em RSP_ERR mas aqui
            # RSP_ERR pode ser apenas CRC mismatch (que tem dados embutidos).
            send_packet(ser, BL_CMD_VERIFY_CRC, payload)
            _, rsp = recv_packet(ser, timeout=5.0)
            # rsp = RSP_OK/ERR | actual_L | actual_H | expect_L | expect_H
            if len(rsp) >= 3:
                ok_flag  = rsp[0]
                actual_crc = rsp[1] | (rsp[2] << 8)
                if ok_flag != RSP_OK or actual_crc != expected_crc:
                    print(f"\r  ERRO pág {page_num}: "
                          f"esperado={expected_crc:#06x} device={actual_crc:#06x}")
                    errors += 1
            else:
                print(f"\r  ERRO pág {page_num}: resposta truncada ({rsp.hex()})")
                errors += 1
        except (TimeoutError, RuntimeError) as e:
            print(f"\r  ERRO pág {page_num}: {e}")
            errors += 1

        checked += 1
        pct = int(checked * 100 / total)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  Verificando[{bar}] {pct:3d}%", end="", flush=True)

    print(f"\r  Verificando[{'█'*20}] 100%  {'OK' if errors == 0 else f'FALHOU ({errors} erros)'}   ")
    return errors == 0


def bl_jump(ser: serial.Serial) -> None:
    send_packet(ser, BL_CMD_JUMP_APP)
    print("  Saltando para aplicação...")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Uploader FT245 para ATmega162 via bootloader")
    parser.add_argument("--port",       required=True,  help="Porta serial (ex: COM5)")
    parser.add_argument("--baud",       type=int, default=500000, help="Baudrate (padrão: 500000)")
    parser.add_argument("--hex",        dest="hex_file", help="Arquivo Intel HEX para gravar")
    parser.add_argument("--verify",     action="store_true", default=True,  help="Verifica após gravação")
    parser.add_argument("--no-verify",  dest="verify", action="store_false", help="Pula verificação")
    parser.add_argument("--jump",       action="store_true", default=True,  help="Salta para app após gravar")
    parser.add_argument("--no-jump",    dest="jump",   action="store_false", help="Fica no bootloader")
    parser.add_argument("--info",       action="store_true", help="Apenas mostra info e sai")
    parser.add_argument("--timeout",    type=float, default=3.0, help="Timeout de entrada (s)")
    args = parser.parse_args()

    if not args.info and not args.hex_file:
        parser.error("Informe --hex FILE ou --info")

    print(f"Conectando em {args.port} @ {args.baud} baud...")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"ERRO: {e}")
        return 1

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print(f"Conectando ao bootloader (timeout={args.timeout:.0f}s)...")
    try:
        info = bl_enter(ser, timeout=0.4)
    except TimeoutError:
        if _app_reboot(ser):
            print("  Reboot enviado para a aplicacao — reabrindo porta...")
        else:
            print("  Aplicacao nao respondeu reboot — tentando mesmo assim apos reabrir a porta...")

        ser.close()
        time.sleep(0.12)

        try:
            ser = serial.Serial(args.port, args.baud, timeout=0.1)
        except serial.SerialException as e:
            print(f"ERRO: {e}")
            return 1

        ser.reset_input_buffer()
        ser.reset_output_buffer()

        try:
            info = bl_enter(ser, timeout=args.timeout)
        except TimeoutError as e:
            print(f"ERRO: {e}")
            ser.close()
            return 1

    print(f"\nBootloader v{info['version']} detectado:")
    print(f"  Tamanho de página : {info['page_size']} bytes")
    print(f"  Páginas de app    : {info['app_pages']} ({info['app_pages'] * info['page_size']} bytes)")
    print(f"  Boot section start: 0x{info['boot_start']:04X}")

    if args.info:
        ser.close()
        return 0

    # Carrega HEX
    print(f"\nCarregando {args.hex_file}...")
    try:
        pages = hex_to_pages(args.hex_file, page_size=info["page_size"])
    except Exception as e:
        print(f"ERRO ao ler HEX: {e}")
        ser.close()
        return 1

    app_max_page = info["app_pages"]
    app_pages = {p: d for p, d in pages.items() if p < app_max_page}

    if not app_pages:
        print("ERRO: HEX não contém dados na área de aplicação.")
        ser.close()
        return 1

    print(f"  {len(app_pages)} páginas a gravar  ({len(app_pages) * info['page_size']} bytes)\n")

    # Apaga
    bl_erase(ser)

    # Grava
    bl_write_pages(ser, app_pages, app_max_page, info["page_size"])

    # Verifica
    if args.verify:
        ok = bl_verify(ser, app_pages, app_max_page, info["page_size"])
        if not ok:
            print("\nGravação FALHOU — verificação com erros.")
            ser.close()
            return 1
    else:
        print("  Verificação pulada (--no-verify)")

    print("\nFirmware gravado com sucesso!")

    if args.jump:
        bl_jump(ser)

    ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
