"""
serial_bridge.py -- Bridge serial bidirecional com echo-cancel e keepalive
===========================================================================
Senta entre o YDS (Yamaha Diagnostic Software) e o AVR/ECM fisico.

Arquitetura:
    YDS --> [COM_VIRTUAL] <-bridge-> [COM_FISICO] --> AVR --> ECM

FUNCIONALIDADES CHAVE:
  - Echo cancellation: suprime o eco half-duplex K-Line antes de reenviar ao YDS.
    No K-Line, todo byte TX aparece como RX no barramento (bus half-duplex).
    Sem esse filtro, o YDS recebe seus proprios bytes de volta e falha no handshake.
  - TesterPresent keepalive: apos detectar a sequencia de init do YDS (por padrao
    'FD' repetido), injeta automaticamente TesterPresent no ECM para manter a
    sessao diagnostica viva mesmo que o YDS nao tenha completado a conexao.

Uso:
    python serial_bridge.py --virtual COM10 --physical COM7 --baud 1000000
    python serial_bridge.py --virtual COM10 --physical COM7 --baud 1000000 --no-echo-cancel
    python serial_bridge.py --virtual COM10 --physical COM7 --baud 1000000 --keepalive-byte FD --keepalive-ms 2000

Saida em tempo real:
    >> = YDS -> ECM (azul)
    << = ECM -> YDS (verde)
    ~~ = keepalive injetado (amarelo)
    [ECHO] = byte suprimido como eco K-Line (cinza, so em --verbose)

Ctrl+C para parar.
"""

import argparse
import sys
import os
import time
import threading
import queue
from collections import deque
from datetime import datetime

try:
    import serial
except ImportError:
    print("ERRO: pyserial nao instalado. Rode: pip install pyserial")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Echo Cancellation
# ---------------------------------------------------------------------------
class EchoFilter:
    """
    Filtra o eco half-duplex do barramento K-Line.

    No K-Line, todo byte transmitido pelo PC aparece de volta como RX
    (barramento open-drain / half-duplex). O YDS nao espera receber seus
    proprios bytes: isso confunde o handshake e impede a conexao.

    Uso:
        filter.sent(byte)      -- registra byte enviado ao K-Line
        filter.is_echo(byte)   -- True se o byte e eco de TX (deve ser suprimido)
    """
    def __init__(self, window_s: float = 0.25):
        # fila de (timestamp, byte) para bytes TX pendentes de eco
        self._queue: deque = deque()
        self._window = window_s
        self._lock   = threading.Lock()
        self.suppressed = 0

    def sent(self, byte_val: int) -> None:
        with self._lock:
            self._queue.append((time.monotonic(), byte_val))

    def is_echo(self, byte_val: int) -> bool:
        now = time.monotonic()
        with self._lock:
            # descarta entradas expiradas
            while self._queue and (now - self._queue[0][0]) > self._window:
                self._queue.popleft()
            # verifica correspondencia com o proximo eco esperado
            if self._queue and self._queue[0][1] == byte_val:
                self._queue.popleft()
                self.suppressed += 1
                return True
        return False


# ---------------------------------------------------------------------------
# TesterPresent Keepalive
# ---------------------------------------------------------------------------
class KeepaliveInjector:
    """
    Injeta bytes de TesterPresent no ECM periodicamente para manter
    a sessao diagnostica viva, mesmo que o YDS nao tenha completado a conexao.

    A injecao ocorre apenas apos a sessao ser iniciada (chamada a arm())
    e e suspensa durante atividade TX do YDS.
    """
    def __init__(self, frame: bytes, interval_s: float, echo_filter: EchoFilter):
        self._frame      = frame
        self._interval   = interval_s
        self._echo_filter = echo_filter
        self._armed      = threading.Event()
        self._stop       = threading.Event()
        self._last_tx    = 0.0   # ultimo momento de atividade YDS
        self._port: 'serial.Serial | None' = None
        self._lock       = threading.Lock()
        self.injected    = 0
        self._logger     = None
        self._t_start    = 0.0
        self._thread     = threading.Thread(target=self._run, daemon=True,
                                             name='keepalive')

    def start(self, port: 'serial.Serial', logger=None, t_start: float = 0.0) -> None:
        self._port    = port
        self._logger  = logger
        self._t_start = t_start
        self._thread.start()

    def arm(self) -> None:
        """Chama quando a sessao de init for detectada."""
        if not self._armed.is_set():
            print(_color('  [KEEPALIVE] Sessao detectada -- keepalive ativo', _YELLOW))
        self._armed.set()
        self._last_tx = time.monotonic()

    def notify_tx(self) -> None:
        """Notifica que YDS enviou dado (reinicia janela de silencio)."""
        self._last_tx = time.monotonic()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._armed.wait(timeout=1.0)
            if self._stop.is_set():
                break
            if not self._armed.is_set():
                continue

            time.sleep(self._interval)
            if self._stop.is_set():
                break

            # So injeta se o YDS estiver silencioso
            idle_s = time.monotonic() - self._last_tx
            if idle_s < 0.5:
                continue

            port = self._port
            if port is None or not port.is_open:
                continue

            try:
                port.write(self._frame)
                # registra no filtro de eco (ECM vai ecoar esses bytes)
                for b in self._frame:
                    self._echo_filter.sent(b)
                self.injected += 1
                hex_s = ' '.join('%02X' % b for b in self._frame)
                msg = '~~ [%3d] %s  |keepalive|' % (len(self._frame), hex_s)
                print(_color(msg, _YELLOW))
                if self._logger:
                    self._logger.log('KA', self._frame, time.monotonic() - self._t_start)
            except Exception:
                pass


# Cores ANSI (funciona no Windows Terminal / PowerShell moderno)
_RESET  = '\x1b[0m'
_BLUE   = '\x1b[94m'
_GREEN  = '\x1b[92m'
_YELLOW = '\x1b[93m'
_RED    = '\x1b[91m'
_GRAY   = '\x1b[90m'

def _color(s, c):
    return c + s + _RESET

def hex_dump(data: bytes, prefix: str, color: str) -> str:
    """Formata bytes como hex + ASCII numa linha."""
    hex_s   = ' '.join('%02X' % b for b in data)
    ascii_s = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
    return _color('%s [%3d] %-47s  |%s|' % (prefix, len(data), hex_s, ascii_s), color)


class BridgeLogger:
    """Grava log binario e texto simultaneamente."""

    def __init__(self, base_path: str):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.bin_path = base_path + '_' + ts + '.bin'
        self.txt_path = base_path + '_' + ts + '.txt'
        self._bin = open(self.bin_path, 'wb')
        self._txt = open(self.txt_path, 'w', encoding='utf-8')
        self._lock = threading.Lock()
        print('  Log binario : %s' % self.bin_path)
        print('  Log texto   : %s' % self.txt_path)

    def log(self, direction: str, data: bytes, t: float):
        """direction: 'TX' (YDS->ECM) ou 'RX' (ECM->YDS)."""
        with self._lock:
            # Binario: [4 bytes timestamp_ms LE] [1 byte dir: 0=TX 1=RX] [1 byte len] [data]
            t_ms = int(t * 1000) & 0xFFFFFFFF
            dir_byte = 0 if direction == 'TX' else 1
            entry = (t_ms.to_bytes(4, 'little') +
                     bytes([dir_byte, len(data)]) +
                     data)
            self._bin.write(entry)
            self._bin.flush()

            # Texto
            hex_s   = ' '.join('%02X' % b for b in data)
            ascii_s = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
            prefix = direction if direction != 'KA' else '~~'
            line = '[%010.3f] %s [%3d] %s  |%s|\n' % (t, prefix, len(data), hex_s, ascii_s)
            self._txt.write(line)
            self._txt.flush()

    def close(self):
        self._bin.close()
        self._txt.close()


class SerialBridge:
    # Sequencia de init que o YDS envia para abrir sessao diagnostica.
    # Quando detectada, o keepalive e armado.
    # Padrao YDS Yamaha: 0x1C (endereco ECM) + 0xFD (comando sessao)
    INIT_TRIGGER = bytes([0x1C])

    def __init__(self, virtual_port: str, physical_port: str,
                 baud: int, logger: 'BridgeLogger | None',
                 echo_cancel: bool = True,
                 keepalive_frame: bytes = bytes([0xFD]),
                 keepalive_ms: int = 2000,
                 verbose: bool = False,
                 wake_300_byte: int | None = None):
        self.vport  = virtual_port
        self.pport  = physical_port
        self.baud   = baud
        self.logger = logger
        self.echo_cancel   = echo_cancel
        self.verbose       = verbose
        # YDS: o byte de wake-up (0x1C) tem de sair a 300 baud e o resto a
        # 9600 (FUN_004798f0). O com0com nao transporta a mudanca de DCB, por
        # isso o bridge reproduz o baud na porta fisica.
        self.wake_300_byte = wake_300_byte
        self._stop  = threading.Event()
        self.t_start = time.monotonic()

        self.bytes_tx = 0
        self.bytes_rx = 0
        self.frames_tx = 0
        self.frames_rx = 0

        self._echo  = EchoFilter(window_s=0.25)
        self._keepalive = KeepaliveInjector(
            frame=keepalive_frame,
            interval_s=keepalive_ms / 1000.0,
            echo_filter=self._echo,
        )

        # buffer para detectar sequencia de init
        self._init_buf: deque = deque(maxlen=len(self.INIT_TRIGGER) + 1)
        self._session_active = False

    def _now(self) -> float:
        return time.monotonic() - self.t_start

    def _check_init_trigger(self, byte_val: int) -> None:
        """Detecta sequencia de init do YDS e arma keepalive."""
        self._init_buf.append(byte_val)
        buf = bytes(self._init_buf)
        if self.INIT_TRIGGER in buf:
            if not self._session_active:
                self._session_active = True
                self._keepalive.arm()

    def _write_physical(self, dst: serial.Serial, data: bytes) -> None:
        """Escreve na porta fisica, respeitando o wake-up a 300 baud do YDS."""
        if self.wake_300_byte is None or self.wake_300_byte not in data:
            dst.write(data)
            return

        chunk = bytearray()
        for b in data:
            if b == self.wake_300_byte:
                if chunk:
                    dst.write(bytes(chunk))
                    dst.flush()
                    chunk.clear()
                dst.baudrate = 300
                dst.write(bytes([b]))
                dst.flush()
                time.sleep(0.005)
                dst.baudrate = self.baud
            else:
                chunk.append(b)
        if chunk:
            dst.write(bytes(chunk))

    def _forward_tx(self, src: serial.Serial, dst: serial.Serial) -> None:
        """Loop TX: YDS -> ECM.  Registra bytes no echo filter."""
        while not self._stop.is_set():
            try:
                data = src.read(256)
            except (serial.SerialException, OSError) as e:
                if not self._stop.is_set():
                    print(_color('\n  [TX] Porta fechou: %s' % e, _RED))
                    self._stop.set()
                break
            if not data:
                continue

            t = self._now()
            self._keepalive.notify_tx()

            # registra cada byte no filtro de eco antes de enviar
            if self.echo_cancel:
                for b in data:
                    self._echo.sent(b)

            # detecta sequencia de init
            for b in data:
                self._check_init_trigger(b)

            try:
                self._write_physical(dst, data)
            except (serial.SerialException, OSError) as e:
                if not self._stop.is_set():
                    print(_color('\n  [TX] Erro ao escrever: %s' % e, _RED))
                    self._stop.set()
                break

            self.bytes_tx  += len(data)
            self.frames_tx += 1

            print(hex_dump(data, '>>', _BLUE))
            if self.logger:
                self.logger.log('TX', data, t)

    def _forward_rx(self, src: serial.Serial, dst: serial.Serial) -> None:
        """Loop RX: ECM -> YDS.  Filtra ecos K-Line antes de repassar."""
        while not self._stop.is_set():
            try:
                data = src.read(256)
            except (serial.SerialException, OSError) as e:
                if not self._stop.is_set():
                    print(_color('\n  [RX] Porta fechou: %s' % e, _RED))
                    self._stop.set()
                break
            if not data:
                continue

            t = self._now()

            if self.echo_cancel:
                filtered = bytearray()
                echoed   = bytearray()
                for b in data:
                    if self._echo.is_echo(b):
                        echoed.append(b)
                    else:
                        filtered.append(b)
                if echoed and self.verbose:
                    print(_color('[ECHO] %s' % ' '.join('%02X'%b for b in echoed), _GRAY))
                data = bytes(filtered)
                if not data:
                    continue

            try:
                dst.write(data)
            except (serial.SerialException, OSError) as e:
                if not self._stop.is_set():
                    print(_color('\n  [RX] Erro ao escrever: %s' % e, _RED))
                    self._stop.set()
                break

            self.bytes_rx  += len(data)
            self.frames_rx += 1

            print(hex_dump(data, '<<', _GREEN))
            if self.logger:
                self.logger.log('RX', data, t)

    def run(self):
        print()
        print('=' * 72)
        print('  SERIAL BRIDGE  %s (virtual) <-> %s (fisico)  @ %d baud' % (
              self.vport, self.pport, self.baud))
        print('  >> = YDS -> ECM    << = ECM -> YDS    ~~ = keepalive injetado')
        print('  Echo cancel : %s' % ('ON' if self.echo_cancel else 'OFF'))
        print('  Keepalive   : %s  (intervalo %.1fs)' % (
              ' '.join('%02X' % b for b in self._keepalive._frame),
              self._keepalive._interval))
        print('  Ctrl+C para parar')
        print('=' * 72)
        print()

        try:
            v_ser = serial.Serial(self.vport,  self.baud, timeout=0.05)
        except serial.SerialException as e:
            print(_color('ERRO ao abrir %s: %s' % (self.vport, e), _RED))
            sys.exit(1)

        try:
            p_ser = serial.Serial(self.pport, self.baud, timeout=0.05)
        except serial.SerialException as e:
            v_ser.close()
            print(_color('ERRO ao abrir %s: %s' % (self.pport, e), _RED))
            sys.exit(1)

        print('  %s aberto OK' % self.vport)
        print('  %s aberto OK' % self.pport)
        print()

        self._keepalive.start(p_ser, logger=self.logger, t_start=self.t_start)

        t_tx = threading.Thread(
            target=self._forward_tx,
            args=(v_ser, p_ser),
            daemon=True, name='tx')
        t_rx = threading.Thread(
            target=self._forward_rx,
            args=(p_ser, v_ser),
            daemon=True, name='rx')

        t_tx.start()
        t_rx.start()

        try:
            while not self._stop.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self._stop.set()
            self._keepalive.stop()
            try:
                v_ser.close()
            except Exception:
                pass
            try:
                p_ser.close()
            except Exception:
                pass
            t_tx.join(timeout=1.0)
            t_rx.join(timeout=1.0)

        elapsed = time.monotonic() - self.t_start
        print()
        print('=' * 72)
        print('  PARADO  --  %.1fs' % elapsed)
        print('  TX (YDS->ECM): %d bytes em %d chunks' % (self.bytes_tx, self.frames_tx))
        print('  RX (ECM->YDS): %d bytes em %d chunks' % (self.bytes_rx, self.frames_rx))
        print('  Ecos suprimidos : %d' % self._echo.suppressed)
        print('  Keepalives inj.  : %d' % self._keepalive.injected)
        print('=' * 72)

        if self.logger:
            self.logger.close()


def main():
    parser = argparse.ArgumentParser(
        description='Bridge serial bidirecional com echo-cancel e keepalive (YDS <-> AVR/ECM)')
    parser.add_argument('--virtual',  default='COM10',
                        help='Porta virtual lado YDS. Padrao: COM10')
    parser.add_argument('--physical', default='COM7',
                        help='Porta fisica do AVR. Padrao: COM7')
    parser.add_argument('--baud',     type=int, default=None,
                        help='Baud rate da porta fisica. Padrao: 9600 com --yds, senao 1000000')
    parser.add_argument('--yds',      action='store_true',
                        help='Predefinicoes para o YDS Yamaha: 9600 baud, sem keepalive, '
                             'sem echo-cancel e wake 0x1C a 300 baud')
    parser.add_argument('--log',      default='C:\\Temp\\yds_bridge',
                        help='Prefixo do arquivo de log. Padrao: C:\\Temp\\yds_bridge')
    parser.add_argument('--no-log',   dest='log', action='store_const', const=None,
                        help='Desabilita gravacao de log')
    parser.add_argument('--no-echo-cancel', dest='echo_cancel', action='store_false',
                        default=True,
                        help='Desabilita filtragem de eco K-Line (nao recomendado)')
    parser.add_argument('--keepalive-byte', default='FD',
                        help='Byte(s) hex de TesterPresent (ex: "FD" ou "1C FD"). Padrao: FD')
    parser.add_argument('--keepalive-ms', type=int, default=2000,
                        help='Intervalo do keepalive em ms. Padrao: 2000')
    parser.add_argument('--no-keepalive', dest='keepalive', action='store_false',
                        default=True,
                        help='Desabilita injecao automatica de keepalive')
    parser.add_argument('--verbose', action='store_true',
                        help='Mostra bytes de eco suprimidos')
    args = parser.parse_args()

    if args.yds:
        # O YDS abre o equipamento a 9600 8N1 e injecta 0x1C a 300 baud.
        if args.baud is None:
            args.baud = 9600
        args.echo_cancel = False
        args.keepalive = False
        args.wake_300_byte = 0x1C
    else:
        if args.baud is None:
            args.baud = 1000000
        args.wake_300_byte = None

    # parse keepalive frame
    keepalive_frame = bytes([int(x, 16) for x in args.keepalive_byte.split()])
    if not args.keepalive:
        keepalive_frame = b''
        args.keepalive_ms = 999999

    logger = None
    if args.log:
        import os
        os.makedirs(os.path.dirname(args.log) or '.', exist_ok=True)
        logger = BridgeLogger(args.log)

    bridge = SerialBridge(
        virtual_port=args.virtual,
        physical_port=args.physical,
        baud=args.baud,
        logger=logger,
        echo_cancel=args.echo_cancel,
        keepalive_frame=keepalive_frame,
        keepalive_ms=args.keepalive_ms,
        verbose=args.verbose,
        wake_300_byte=args.wake_300_byte,
    )
    bridge.run()


if __name__ == '__main__':
    main()
