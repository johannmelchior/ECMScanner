import argparse
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ModuleNotFoundError:
    serial = None


DEFAULT_BAUDRATES = [38400, 9600, 115200]
DEFAULT_PROTOCOLS = ["3", "4", "5", "0"]
PROMPT = ">"


def list_serial_ports():
    if serial is None:
        return []
    return list(serial.tools.list_ports.comports())


def print_serial_ports():
    ports = list_serial_ports()
    if not ports:
        print("Nenhuma porta serial encontrada.")
        return 1

    print("Portas seriais disponiveis:")
    for port in ports:
        hwid = f" [{port.hwid}]" if port.hwid else ""
        desc = f" - {port.description}" if port.description else ""
        print(f"  {port.device}{desc}{hwid}")
    return 0


def open_serial(port_name, baudrate, timeout):
    if serial is None:
        raise RuntimeError("pyserial nao esta instalado")
    return serial.Serial(port=port_name, baudrate=baudrate, timeout=timeout, write_timeout=timeout)


def flush_input(ser):
    try:
        ser.reset_input_buffer()
    except Exception:
        pass


def read_until_prompt(ser, timeout=3.0):
    deadline = time.time() + timeout
    chunks = []

    while time.time() < deadline:
        waiting = ser.in_waiting
        if waiting:
            data = ser.read(waiting).decode(errors="ignore")
            chunks.append(data)
            if PROMPT in data or PROMPT in "".join(chunks):
                break
        else:
            time.sleep(0.05)

    raw = "".join(chunks)
    normalized = raw.replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip() and line.strip() != PROMPT]
    return raw, lines


def send_command(ser, command, timeout=3.0, settle=0.15):
    flush_input(ser)
    ser.write((command + "\r").encode("ascii"))
    ser.flush()
    time.sleep(settle)
    raw, lines = read_until_prompt(ser, timeout=timeout)
    return {
        "command": command,
        "raw": raw,
        "lines": lines,
        "ok": any(line.upper() == "OK" for line in lines),
    }


def print_result(result):
    print(f"\n> {result['command']}")
    if result["lines"]:
        for line in result["lines"]:
            print(f"  {line}")
    elif result["raw"]:
        print(f"  {result['raw'].strip()}")
    else:
        print("  <sem resposta>")


def detect_basic_link(ser):
    base_commands = ["ATZ", "ATE0", "ATL0", "ATS0", "ATH1"]
    results = []

    for command in base_commands:
        timeout = 5.0 if command == "ATZ" else 2.0
        result = send_command(ser, command, timeout=timeout)
        results.append(result)
        print_result(result)

    return results


def try_protocols(ser, protocols):
    print("\nValidando protocolos OBD/K-Line via ELM...")
    attempts = []

    for protocol in protocols:
        set_result = send_command(ser, f"ATSP{protocol}", timeout=2.5)
        attempts.append((protocol, "ATSP", set_result))
        print_result(set_result)

        query_result = send_command(ser, "0100", timeout=4.0, settle=0.25)
        attempts.append((protocol, "0100", query_result))
        print_result(query_result)

        if has_obd_payload(query_result["lines"]):
            print(f"\nResposta valida detectada com protocolo ATSP{protocol}.")
            dpn_result = send_command(ser, "ATDPN", timeout=2.0)
            attempts.append((protocol, "ATDPN", dpn_result))
            print_result(dpn_result)
            return True, attempts

    return False, attempts


def has_obd_payload(lines):
    for line in lines:
        upper = line.upper()
        if upper.startswith("41 ") or upper.startswith("7E8") or upper.startswith("SEARCHING"):
            return True
    return False


def auto_detect_port_name(explicit_port=None):
    if explicit_port:
        return explicit_port

    ports = list_serial_ports()
    preferred_terms = ["bluetooth", "obd", "serial over bluetooth", "standard serial over bluetooth link"]

    for port in ports:
        haystack = " ".join(filter(None, [port.device, port.name, port.description, port.manufacturer])).lower()
        if any(term in haystack for term in preferred_terms):
            return port.device

    return None


def try_baudrates(port_name, baudrates, timeout, protocols):
    last_error = None

    for baudrate in baudrates:
        print(f"\nAbrindo {port_name} em {baudrate} baud...")
        try:
            with open_serial(port_name, baudrate, timeout) as ser:
                time.sleep(1.5)
                detect_basic_link(ser)
                success, _attempts = try_protocols(ser, protocols)
                return 0 if success else 2
        except serial.SerialException as exc:
            last_error = exc
            print(f"Falha ao abrir/usar {port_name} em {baudrate}: {exc}")

    if last_error is not None:
        print(f"\nNao foi possivel validar o ELM em {port_name}: {last_error}")
        return 1

    return 1


def build_parser():
    parser = argparse.ArgumentParser(
        description="Valida conexao inicial com ELM327 Bluetooth/serial e testa protocolos OBD basicos."
    )
    parser.add_argument("--port", help="Porta COM do ELM327, ex.: COM7")
    parser.add_argument(
        "--baud",
        type=int,
        action="append",
        dest="baudrates",
        help="Baudrate para teste. Pode ser repetido. Padrao: 38400, 9600, 115200",
    )
    parser.add_argument(
        "--protocol",
        action="append",
        dest="protocols",
        help="Protocolo ELM a testar via ATSPx. Pode repetir. Padrao: 3, 4, 5, 0",
    )
    parser.add_argument("--timeout", type=float, default=1.0, help="Timeout serial em segundos. Padrao: 1.0")
    parser.add_argument("--list-ports", action="store_true", help="Lista portas seriais e sai")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if serial is None:
        print("Dependencia ausente: pyserial")
        print("Instale com: pip install pyserial")
        return 1

    if args.list_ports:
        return print_serial_ports()

    port_name = auto_detect_port_name(args.port)
    if not port_name:
        print("Nao foi possivel detectar automaticamente a porta do ELM.")
        print("Use --list-ports para listar as COMs e depois rode com --port COMx.")
        return 1

    baudrates = args.baudrates or DEFAULT_BAUDRATES
    protocols = args.protocols or DEFAULT_PROTOCOLS

    print(f"Porta selecionada: {port_name}")
    print(f"Baudrates de teste: {', '.join(str(rate) for rate in baudrates)}")
    print(f"Protocolos ATSP a testar: {', '.join(protocols)}")

    return try_baudrates(port_name, baudrates, args.timeout, protocols)


if __name__ == "__main__":
    sys.exit(main())