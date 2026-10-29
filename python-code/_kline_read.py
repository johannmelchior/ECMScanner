"""
_kline_read.py — Monitor K-Line via AVR  (usa CMD_KLINE_RX_BULK = 0x14)

Uma única transação USB lê até 28 bytes K-Line de forma contínua.
Isso é muito mais eficiente que o byte-by-byte anterior (16ms/byte).

Uso:
    python _kline_read.py              # leitura com bulk (default)
    python _kline_read.py --raw        # sem compressão de bytes repetidos
    python _kline_read.py --no-wake    # pula wakeup (sniff passivo)
    python _kline_read.py --no-bulk    # fallback byte-a-byte legacy
"""
import serial
import struct
import time
import sys
import collections

PORT    = "COM7"
BAUD    = 500_000
SYNC_USB = 0x5A

CMD_GET_INFO   = 0x01
CMD_KLINE_WAKE = 0x03
CMD_KLINE_RX   = 0x12
CMD_KLINE_BULK = 0x14
CMD_REBOOT     = 0x05  # reset via WDT → reinicia no bootloader

RSP_OK      = 0xA5
RSP_ERR     = 0x7F

# Parâmetros bulk: primeiro byte timeout / inter-byte timeout / máx bytes
BULK_FIRST_TIMEOUT_MS = 50   # aguarda até 50ms pelo primeiro byte do frame
BULK_INTER_TIMEOUT_MS = 4    # até 4ms entre bytes da mesma rajada
BULK_MAX_BYTES        = 28   # cabe em USB_PACKET_MAX_PAYLOAD (32 − 4 header)

# Gap de tempo entre bursts para separar frames lógicos
FRAME_GAP_MS = 6.0

# Padrões de sincronização Yamaha (normal e invertido bit-a-bit)
SYNC_PATTERNS = {
    "YAMAHA_T1": bytes([0x55, 0x01]),
    "YAMAHA_T2": bytes([0x55, 0x02]),
    "YAMAHA_I1": bytes([0xAA, 0xFE]),
    "YAMAHA_I2": bytes([0xAA, 0xFD]),
}

# ---------------------------------------------------------------------------
# Protocolo USB-AVR
# ---------------------------------------------------------------------------

def _cs(cmd: int, payload: bytes) -> int:
    cs = len(payload) ^ cmd
    for b in payload:
        cs ^= b
    return cs & 0xFF


def send_pkt(ser: serial.Serial, cmd: int, payload: bytes = b"") -> None:
    pkt = bytes([SYNC_USB, len(payload), cmd]) + payload + bytes([_cs(cmd, payload)])
    ser.write(pkt)


def recv_pkt(ser: serial.Serial, expected_cmd: int, timeout: float = 1.0):
    deadline = time.monotonic() + timeout
    state = "sync"
    plen = cmd = 0
    payload = bytearray()
    cs_run = 0
    while time.monotonic() < deadline:
        raw = ser.read(1)
        if not raw:
            continue
        v = raw[0]
        if state == "sync":
            if v == SYNC_USB:
                state = "len"
        elif state == "len":
            plen = v; cs_run = v; payload.clear(); state = "cmd"
        elif state == "cmd":
            cmd = v; cs_run ^= v
            state = "payload" if plen else "cs"
        elif state == "payload":
            payload.append(v); cs_run ^= v
            if len(payload) >= plen:
                state = "cs"
        elif state == "cs":
            if v == cs_run and cmd == expected_cmd:
                return bytes(payload)
            state = "sync"
    return None


def get_info(ser: serial.Serial):
    for _ in range(5):
        ser.reset_input_buffer()
        time.sleep(0.05)
        send_pkt(ser, CMD_GET_INFO)
        r = recv_pkt(ser, CMD_GET_INFO, timeout=2.0)
        if r and len(r) >= 3:
            return r[1], r[2]
        time.sleep(0.2)
    return None, None


def do_wakeup(ser: serial.Serial) -> bool:
    print("  Enviando wakeup K-Line (5-baud Yamaha)...")
    send_pkt(ser, CMD_KLINE_WAKE)
    r = recv_pkt(ser, CMD_KLINE_WAKE, timeout=4.0)
    ok = bool(r and r[0] == RSP_OK)
    print("  Wakeup OK" if ok else "  Wakeup sem confirmacao")
    return ok

# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------

def _detect_sync(frame: bytes) -> str:
    for name, pat in SYNC_PATTERNS.items():
        if frame[:len(pat)] == pat or pat in frame:
            return name
    inv = bytes(b ^ 0xFF for b in frame)
    for name, pat in SYNC_PATTERNS.items():
        if inv[:len(pat)] == pat or pat in inv:
            return "INV_" + name
    return ""


def _checksum_ok(frame: bytes) -> str:
    if len(frame) < 2:
        return ""
    xr = 0
    for b in frame:
        xr ^= b
    if xr == 0:
        return "XOR=0"
    s = sum(frame[:-1]) & 0xFF
    if s == frame[-1]:
        return "SUM"
    if ((~s) & 0xFF) == frame[-1]:
        return "~SUM"
    return ""


def _fmt_frame(frame: bytes, raw: bool) -> str:
    if raw:
        return " ".join(f"{b:02X}" for b in frame)
    parts = []
    i = 0
    while i < len(frame):
        b = frame[i]
        run = 1
        while i + run < len(frame) and frame[i + run] == b:
            run += 1
        if run >= 4:
            parts.append(f"[{run}x{b:02X}]")
        else:
            parts.extend(f"{b:02X}" for _ in range(run))
        i += run
    return " ".join(parts)

# ---------------------------------------------------------------------------
# Loop de leitura — BULK
# ---------------------------------------------------------------------------

def read_loop_bulk(ser: serial.Serial, raw: bool) -> None:
    print(f"Modo BULK: first={BULK_FIRST_TIMEOUT_MS}ms inter={BULK_INTER_TIMEOUT_MS}ms max={BULK_MAX_BYTES}B/req")
    print(f"{'Tempo':>10}  {'#':>5}  {'Len':>3}  Conteúdo")
    print("-" * 100)

    frame_buf   = bytearray()
    last_bulk_t = time.monotonic()
    t_start     = time.monotonic()
    frame_count = 0
    total_bytes = 0
    silent_count = 0
    byte_hist   = collections.Counter()

    # Payload bulk: first_to (2B LE) | inter_to (2B LE) | max_bytes (1B)
    bulk_payload = struct.pack("<HHB",
                               BULK_FIRST_TIMEOUT_MS,
                               BULK_INTER_TIMEOUT_MS,
                               BULK_MAX_BYTES)

    def flush_frame(now: float) -> None:
        nonlocal frame_count
        if not frame_buf:
            return
        fr      = bytes(frame_buf)
        elapsed = now - t_start
        tags    = []
        sync    = _detect_sync(fr)
        cs      = _checksum_ok(fr)
        if sync:
            tags.append(f"[{sync}]")
        if cs:
            tags.append(f"[{cs}]")
        extra = "  " + " ".join(tags) if tags else ""
        # Se invertido, mostra também a versão decodificada
        if "INV_" in sync:
            inv = bytes(b ^ 0xFF for b in fr)
            extra += "\n" + " " * 30 + "→ INV: " + " ".join(f"{b:02X}" for b in inv)
        print(f"[{elapsed:9.3f}s]  #{frame_count:04d}  {len(fr):3d}  {_fmt_frame(fr, raw)}{extra}")
        frame_buf.clear()
        frame_count += 1

    try:
        while True:
            send_pkt(ser, CMD_KLINE_BULK, bulk_payload)
            resp = recv_pkt(ser, CMD_KLINE_BULK,
                            timeout=(BULK_FIRST_TIMEOUT_MS + BULK_MAX_BYTES * 2) / 1000 + 0.5)
            now = time.monotonic()

            if resp and len(resp) >= 2 and resp[0] == RSP_OK:
                n     = resp[1]
                chunk = resp[2 : 2 + n]
                gap_ms = (now - last_bulk_t) * 1000.0

                if n > 0:
                    if frame_buf and gap_ms > FRAME_GAP_MS:
                        flush_frame(now)
                    frame_buf.extend(chunk)
                    for b in chunk:
                        byte_hist[b] += 1
                    total_bytes += n
                    last_bulk_t  = now
                    silent_count = 0
                else:
                    # Nenhum byte neste burst — flush se há dados pendentes
                    silent_count += 1
                    if frame_buf and (now - last_bulk_t) * 1000 > FRAME_GAP_MS * 3:
                        flush_frame(now)
                    if silent_count == 10:
                        print(f"[{now - t_start:9.3f}s]  -- bus silencioso --")
                        silent_count = 0
            else:
                if frame_buf:
                    flush_frame(now)

    except KeyboardInterrupt:
        flush_frame(time.monotonic())

    elapsed = time.monotonic() - t_start
    print()
    print(f"Total: {frame_count} frames, {total_bytes} bytes em {elapsed:.1f}s  "
          f"({total_bytes / elapsed:.0f} bytes/s)")

    if byte_hist:
        most_cnt = byte_hist.most_common(1)[0][1]
        print("\nTop 10 bytes mais frequentes:")
        for val, cnt in byte_hist.most_common(10):
            bar = "█" * (cnt * 30 // most_cnt)
            pct = cnt * 100 / total_bytes
            print(f"  0x{val:02X}  {cnt:6d}×  {pct:5.1f}%  {bar}")
        dom, dom_cnt = byte_hist.most_common(1)[0]
        if dom_cnt > total_bytes * 0.4:
            print(f"\n  AVISO: 0x{dom:02X} domina ({dom_cnt * 100 / total_bytes:.0f}%).")
            print(f"  Invertido = 0x{dom ^ 0xFF:02X}. Verifique polaridade do transceiver K-Line.")

# ---------------------------------------------------------------------------
# Loop legacy byte-a-byte (fallback)
# ---------------------------------------------------------------------------

def read_loop_legacy(ser: serial.Serial, raw: bool) -> None:
    print(f"Modo LEGACY byte-a-byte (timeout=25ms)")
    print(f"{'Tempo':>10}  {'#':>5}  {'Len':>3}  Conteúdo")
    print("-" * 100)

    frame_buf   = bytearray()
    last_byte_t = time.monotonic()
    t_start     = time.monotonic()
    frame_count = 0
    total_bytes = 0
    silent_run  = 0
    byte_hist   = collections.Counter()

    def flush_frame(now: float) -> None:
        nonlocal frame_count
        if not frame_buf:
            return
        fr      = bytes(frame_buf)
        elapsed = now - t_start
        tags    = []
        if _detect_sync(fr):
            tags.append(f"[{_detect_sync(fr)}]")
        if _checksum_ok(fr):
            tags.append(f"[{_checksum_ok(fr)}]")
        extra = "  " + " ".join(tags) if tags else ""
        print(f"[{elapsed:9.3f}s]  #{frame_count:04d}  {len(fr):3d}  {_fmt_frame(fr, raw)}{extra}")
        frame_buf.clear()
        frame_count += 1

    try:
        while True:
            send_pkt(ser, CMD_KLINE_RX, struct.pack("<H", 25))
            resp = recv_pkt(ser, CMD_KLINE_RX, timeout=0.15)
            now  = time.monotonic()

            if resp and len(resp) >= 2 and resp[0] == RSP_OK:
                b      = resp[1]
                gap_ms = (now - last_byte_t) * 1000.0
                if frame_buf and gap_ms > FRAME_GAP_MS:
                    flush_frame(now)
                frame_buf.append(b)
                byte_hist[b] += 1
                total_bytes  += 1
                last_byte_t   = now
                silent_run    = 0
            else:
                silent_run += 1
                if frame_buf and (now - last_byte_t) * 1000 > FRAME_GAP_MS * 4:
                    flush_frame(now)
                if silent_run == 100:
                    print(f"[{now - t_start:9.3f}s]  -- bus silencioso --")
                    silent_run = 0

    except KeyboardInterrupt:
        flush_frame(time.monotonic())

    elapsed = time.monotonic() - t_start
    print(f"\nTotal: {frame_count} frames, {total_bytes} bytes em {elapsed:.1f}s")

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    no_wake  = "--no-wake"  in sys.argv
    raw      = "--raw"      in sys.argv
    no_bulk  = "--no-bulk"  in sys.argv

    ser = serial.Serial(PORT, BAUD, timeout=0.04)
    time.sleep(0.2)
    ser.reset_input_buffer()
    print(f"Conectado: {PORT} @ {BAUD} baud")

    version, mode = get_info(ser)
    if version is None:
        print("ERRO: AVR nao respondeu GET_INFO")
        ser.close()
        return

    mode_names = {0: "IDLE", 1: "KLINE", 2: "CAN"}
    print(f"Firmware v{version:#04x}  modo={mode_names.get(mode, f'?{mode}')}")

    if mode != 1:
        print(f"AVR em modo {mode_names.get(mode, str(mode))} — esperado KLINE (1)")
        ser.close()
        return

    if not no_wake:
        do_wakeup(ser)
        time.sleep(0.1)

    ser.reset_input_buffer()
    print(f"\nMonitorando K-Line  |  Ctrl+C para parar")
    if not raw:
        print("Dica: [NxVV] = run de N bytes iguais. --raw mostra tudo expandido.")

    try:
        if no_bulk:
            read_loop_legacy(ser, raw)
        else:
            read_loop_bulk(ser, raw)
    finally:
        ser.close()


if __name__ == "__main__":
    main()
import serial
import struct
import time
import sys
import collections

PORT    = "COM7"
BAUD    = 500_000
SYNC_USB = 0x5A

CMD_GET_INFO   = 0x01
CMD_KLINE_WAKE = 0x03
CMD_KLINE_RX   = 0x12

RSP_OK      = 0xA5
RSP_ERR     = 0x7F
RSP_NO_DATA = 0xA6

# Timeout por byte K-Line enviado ao AVR (ms).
# Menor = mais rápido, mas perde bytes no inter-frame gap.
RX_TIMEOUT_MS = 25

# Gap entre bytes (ms) que separa frames distintos.
FRAME_GAP_MS = 8.0

# Padrões Yamaha conhecidos (normal e invertido)
SYNC_PATTERNS = {
    "YAMAHA_N1" : bytes([0x55, 0x01]),
    "YAMAHA_N2" : bytes([0x55, 0x02]),
    "YAMAHA_I1" : bytes([0xAA, 0xFE]),   # 55 01 invertido bit-a-bit
    "YAMAHA_I2" : bytes([0xAA, 0xFD]),   # 55 02 invertido
    "KWP_FAST"  : bytes([0x55, 0x10]),   # KWP2000 fast-init typical
}

# ---------------------------------------------------------------------------
# Protocolo USB-AVR
# ---------------------------------------------------------------------------

def _cs(cmd: int, payload: bytes) -> int:
    cs = len(payload) ^ cmd
    for b in payload:
        cs ^= b
    return cs & 0xFF


def send_pkt(ser: serial.Serial, cmd: int, payload: bytes = b"") -> None:
    pkt = bytes([SYNC_USB, len(payload), cmd]) + payload + bytes([_cs(cmd, payload)])
    ser.write(pkt)


def recv_pkt(ser: serial.Serial, expected_cmd: int, timeout: float = 1.0):
    deadline = time.monotonic() + timeout
    state = "sync"
    plen = cmd = 0
    payload = bytearray()
    cs_run = 0
    while time.monotonic() < deadline:
        raw = ser.read(1)
        if not raw:
            continue
        v = raw[0]
        if state == "sync":
            if v == SYNC_USB:
                state = "len"
        elif state == "len":
            plen = v; cs_run = v; payload.clear(); state = "cmd"
        elif state == "cmd":
            cmd = v; cs_run ^= v
            state = "payload" if plen else "cs"
        elif state == "payload":
            payload.append(v); cs_run ^= v
            if len(payload) >= plen:
                state = "cs"
        elif state == "cs":
            if v == cs_run and cmd == expected_cmd:
                return bytes(payload)
            state = "sync"
    return None


def get_info(ser: serial.Serial):
    for _ in range(5):
        ser.reset_input_buffer()
        time.sleep(0.05)
        send_pkt(ser, CMD_GET_INFO)
        r = recv_pkt(ser, CMD_GET_INFO, timeout=2.0)
        if r and len(r) >= 3:
            return r[1], r[2]
        time.sleep(0.2)
    return None, None


def do_wakeup(ser: serial.Serial) -> bool:
    print("  Enviando wakeup K-Line (5-baud)...")
    send_pkt(ser, CMD_KLINE_WAKE)
    r = recv_pkt(ser, CMD_KLINE_WAKE, timeout=4.0)
    ok = bool(r and r[0] == RSP_OK)
    print("  Wakeup OK" if ok else "  Wakeup sem confirmacao (ECM pode estar desligado)")
    return ok

# ---------------------------------------------------------------------------
# Análise de frame
# ---------------------------------------------------------------------------

def _detect_sync(frame: bytes) -> str:
    for name, pat in SYNC_PATTERNS.items():
        if frame[:len(pat)] == pat:
            return name
        if len(frame) >= len(pat) and pat in frame:
            return name + "(mid)"
    # Verifica versão invertida bit-a-bit
    inv = bytes(b ^ 0xFF for b in frame)
    for name, pat in SYNC_PATTERNS.items():
        if inv[:len(pat)] == pat:
            return "INV_" + name
        if len(inv) >= len(pat) and pat in inv:
            return "INV_" + name + "(mid)"
    return ""


def _fmt_frame(frame: bytes, raw: bool) -> str:
    if raw:
        return " ".join(f"{b:02X}" for b in frame)
    parts = []
    i = 0
    while i < len(frame):
        b = frame[i]
        run = 1
        while i + run < len(frame) and frame[i + run] == b:
            run += 1
        if run >= 4:
            parts.append(f"[{run}x{b:02X}]")
        else:
            parts.extend(f"{b:02X}" for _ in range(run))
        i += run
    return " ".join(parts)


def _checksum_valid(frame: bytes) -> str:
    """Testa algumas variantes de checksum comuns."""
    if len(frame) < 2:
        return ""
    # XOR de todos os bytes = 0 ?
    xor_all = 0
    for b in frame:
        xor_all ^= b
    if xor_all == 0:
        return "[XOR=0 OK]"
    # Soma dos N-1 bytes & 0xFF == último byte ?
    s = sum(frame[:-1]) & 0xFF
    if s == frame[-1]:
        return "[SUM OK]"
    # Complemento da soma
    if ((~s) & 0xFF) == frame[-1]:
        return "[~SUM OK]"
    return ""

# ---------------------------------------------------------------------------
# Loop de leitura
# ---------------------------------------------------------------------------

def read_loop(ser: serial.Serial, raw: bool) -> None:
    print()
    print(f"{'Tempo':>10}  {'#':>5}  {'Len':>3}  Conteúdo")
    print("-" * 110)

    frame_buf   = bytearray()
    last_byte_t = time.monotonic()
    t_start     = time.monotonic()
    frame_count = 0
    total_bytes = 0
    no_data_run = 0
    byte_hist   = collections.Counter()

    def flush_frame(now: float) -> None:
        nonlocal frame_count
        if not frame_buf:
            return
        fr  = bytes(frame_buf)
        elapsed = now - t_start
        sync_tag = _detect_sync(fr)
        cs_tag   = _checksum_valid(fr)
        tag = ""
        if sync_tag:
            tag += f" [{sync_tag}]"
        if cs_tag:
            tag += f" {cs_tag}"
        # Inverted dump se parece invertido
        inv_str = ""
        if "INV_" in sync_tag:
            inv = bytes(b ^ 0xFF for b in fr)
            inv_str = "\n" + " " * 20 + "INV: " + " ".join(f"{b:02X}" for b in inv)
        content = _fmt_frame(fr, raw)
        print(f"[{elapsed:9.3f}s]  #{frame_count:04d}  {len(fr):3d}  {content}{tag}{inv_str}")
        frame_buf.clear()
        frame_count += 1

    try:
        while True:
            send_pkt(ser, CMD_KLINE_RX, struct.pack("<H", RX_TIMEOUT_MS))
            resp = recv_pkt(ser, CMD_KLINE_RX, timeout=0.15)
            now = time.monotonic()

            if resp and len(resp) >= 2 and resp[0] == RSP_OK:
                b = resp[1]
                gap_ms = (now - last_byte_t) * 1000.0

                if frame_buf and gap_ms > FRAME_GAP_MS:
                    flush_frame(now)

                frame_buf.append(b)
                byte_hist[b] += 1
                total_bytes += 1
                last_byte_t = now
                no_data_run = 0
            else:
                no_data_run += 1
                # Flush se ficou muito tempo sem dado
                if frame_buf and (now - last_byte_t) > 0.12:
                    flush_frame(now)
                if no_data_run == 120:
                    elapsed = now - t_start
                    print(f"[{elapsed:9.3f}s]  -- bus silencioso (nenhum byte em ~3s) --")

    except KeyboardInterrupt:
        now = time.monotonic()
        flush_frame(now)
        elapsed = now - t_start

    print()
    print(f"Total: {frame_count} frames, {total_bytes} bytes em {elapsed:.1f}s")

    if byte_hist:
        print("\nTop 10 valores mais frequentes:")
        for val, cnt in byte_hist.most_common(10):
            bar = "█" * min(40, cnt * 40 // byte_hist.most_common(1)[0][1])
            pct = cnt * 100 / total_bytes
            print(f"  0x{val:02X} ({val:3d})  {cnt:6d}x  {pct:5.1f}%  {bar}")

        dominant = byte_hist.most_common(1)[0][0]
        if byte_hist.most_common(1)[0][1] > total_bytes * 0.5:
            inv = dominant ^ 0xFF
            print(f"\n  NOTA: 0x{dominant:02X} domina o bus. Invertido = 0x{inv:02X}.")
            print(f"  Se o sinal K-Line estiver invertido, use '--invert' ou verifique o transceiver.")

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    no_wake = "--no-wake" in sys.argv
    raw     = "--raw"     in sys.argv

    ser = serial.Serial(PORT, BAUD, timeout=0.04)
    time.sleep(0.2)
    ser.reset_input_buffer()
    print(f"Conectado: {PORT} @ {BAUD} baud")

    version, mode = get_info(ser)
    if version is None:
        print("ERRO: AVR nao respondeu GET_INFO")
        ser.close()
        return

    mode_names = {0: "IDLE", 1: "KLINE", 2: "CAN"}
    print(f"Firmware v{version:#04x}  modo={mode_names.get(mode, f'?{mode}')}")

    if mode != 1:
        print(f"AVR em modo {mode_names.get(mode, str(mode))} — esperado KLINE (1)")
        ser.close()
        return

    if not no_wake:
        do_wakeup(ser)
        time.sleep(0.1)

    ser.reset_input_buffer()
    print(f"\nMonitorando K-Line (gap_frame={FRAME_GAP_MS}ms, rx_timeout={RX_TIMEOUT_MS}ms)")
    print("Ctrl+C para parar e ver estatísticas")
    if not raw:
        print("Nota: runs de 4+ bytes iguais são comprimidos: [NxVV]")

    read_loop(ser, raw)
    ser.close()


if __name__ == "__main__":
    main()

