from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass
from typing import Optional

import serial
import serial.tools.list_ports


SYNC = 0x5A
DEFAULT_BAUDRATE = 1000000
MAX_PAYLOAD = 32

RSP_OK = 0xA5
RSP_ERR = 0x7F
RSP_NO_DATA = 0xA6


class AvrCommand(enum.IntEnum):
    GET_INFO = 0x01
    SET_MODE = 0x02
    KLINE_WAKEUP = 0x03
    GET_MODE = 0x04
    REBOOT = 0x05  # reset via WDT → reinicia no bootloader (BOOTRST=0)
    KLINE_SET_BAUD = 0x10
    KLINE_TX_BYTE = 0x11
    KLINE_RX_BYTE = 0x12
    KLINE_TX_FRAME = 0x13  # envia frame inteiro atomicamente com detecção de bus-idle
    KLINE_RX_BULK  = 0x14  # lê múltiplos bytes K-Line em uma única transação USB
    KLINE_WAIT_HIGH = 0x15
    KLINE_GET_STATUS = 0x16
    KLINE_RX_BULK_RAW = 0x17  # como 0x14 mas inclui bytes com FE — para diagnóstico de baud
    KLINE_KEEPALIVE   = 0x18  # keepalive autônomo no firmware (TesterPresent periódico)
    CAN_SET_BITRATE = 0x20
    CAN_TX_STD = 0x21
    CAN_RX_POLL = 0x22
    CAN_GET_STATUS = 0x23
    CAN_RX_AUTO = 0x24  # push autônomo de frames RX sem requisição
    # Bootloader FT245 (0x70–0x75) — só válidos quando AVR está em modo bootloader
    BL_GET_INFO   = 0x70
    BL_ERASE_APP  = 0x71
    BL_WRITE_PAGE = 0x72
    BL_READ_PAGE  = 0x73
    BL_VERIFY_CRC = 0x74
    BL_JUMP_APP   = 0x75


class InterfaceMode(enum.IntEnum):
    IDLE = 0x00
    KLINE = 0x01
    CAN = 0x02


class KlineSignalState(enum.IntEnum):
    LOW = 0x00
    HIGH = 0x01
    COMMUNICATING = 0x02


@dataclass
class AvrPacket:
    command: int
    payload: bytes


@dataclass
class CanFrame:
    can_id: int
    data: bytes


@dataclass
class KlineSignalStatus:
    state: KlineSignalState
    high_ms: int
    low_ms: int
    edge_count: int
    rx_byte_count: int

    @property
    def state_name(self) -> str:
        if self.state == KlineSignalState.HIGH:
            return "high_or_open"
        return self.state.name.lower()

    @property
    def is_low(self) -> bool:
        return self.state == KlineSignalState.LOW

    @property
    def is_high(self) -> bool:
        return self.state == KlineSignalState.HIGH

    @property
    def is_communicating(self) -> bool:
        return self.state == KlineSignalState.COMMUNICATING


@dataclass
class CanStatus:
    status: int
    rx_error_counter: int
    tx_error_counter: int
    error_code_capture: int
    arbitration_lost_capture: int
    error_warning_limit: int
    rx_message_count: int
    bitrate_kbps: int

    @property
    def bus_off(self) -> bool:
        return bool(self.status & 0x80)

    @property
    def error_warning(self) -> bool:
        return bool(self.status & 0x40)

    @property
    def tx_complete(self) -> bool:
        return bool(self.status & 0x08)

    @property
    def tx_buffer_free(self) -> bool:
        return bool(self.status & 0x04)

    @property
    def data_overrun(self) -> bool:
        return bool(self.status & 0x02)

    @property
    def rx_buffer_has_data(self) -> bool:
        return bool(self.status & 0x01)


class AvrProtocolError(RuntimeError):
    pass


class AvrTransport:
    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = 0.2):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        # None = não testado ainda; True/False = firmware suporta CMD 0x13
        self._tx_frame_supported: Optional[bool] = None

    @staticmethod
    def list_serial_ports() -> list[str]:
        return [port.device for port in serial.tools.list_ports.comports()]

    def connect(self) -> None:
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    def __enter__(self) -> "AvrTransport":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_serial(self) -> serial.Serial:
        if not self.ser or not self.ser.is_open:
            raise AvrProtocolError("Serial not connected")
        return self.ser

    def _checksum(self, command: int, payload: bytes) -> int:
        checksum = len(payload) ^ command
        for value in payload:
            checksum ^= value
        return checksum & 0xFF

    def send_packet(self, command: int, payload: bytes = b"") -> None:
        if len(payload) > MAX_PAYLOAD:
            raise AvrProtocolError(f"Payload too large: {len(payload)}")

        ser = self._require_serial()
        frame = bytes([SYNC, len(payload), command]) + payload + bytes([self._checksum(command, payload)])
        ser.write(frame)

    def receive_packet(self, expected_command: Optional[int] = None, timeout: float = 1.0) -> AvrPacket:
        ser = self._require_serial()
        deadline = time.monotonic() + timeout
        state = "sync"
        payload_len = 0
        command = 0
        payload = bytearray()
        checksum = 0

        while time.monotonic() < deadline:
            raw = ser.read(1)
            if not raw:
                continue

            value = raw[0]

            if state == "sync":
                if value == SYNC:
                    state = "len"
                continue

            if state == "len":
                payload_len = value
                if payload_len > MAX_PAYLOAD:
                    state = "sync"
                    continue
                checksum = payload_len
                payload.clear()
                state = "cmd"
                continue

            if state == "cmd":
                command = value
                checksum ^= command
                state = "payload" if payload_len else "checksum"
                continue

            if state == "payload":
                payload.append(value)
                checksum ^= value
                if len(payload) >= payload_len:
                    state = "checksum"
                continue

            if state == "checksum":
                if value != checksum:
                    state = "sync"
                    payload_len = 0
                    command = 0
                    payload.clear()
                    checksum = 0
                    continue
                if expected_command is not None and command != expected_command:
                    # Ignore asynchronous/spurious frames and keep waiting for the requested command.
                    state = "sync"
                    payload_len = 0
                    command = 0
                    payload.clear()
                    checksum = 0
                    continue
                # Some USB-serial bridges can echo the host request frame.
                # Ignore empty frames and keep waiting for the real AVR reply payload.
                if expected_command is not None and payload_len == 0:
                    state = "sync"
                    payload_len = 0
                    command = 0
                    payload.clear()
                    checksum = 0
                    continue
                return AvrPacket(command=command, payload=bytes(payload))

        raise TimeoutError("Timed out waiting for AVR response")

    def request(self, command: int, payload: bytes = b"", timeout: float = 1.0) -> AvrPacket:
        with self._lock:
            self.send_packet(command, payload)
            return self.receive_packet(expected_command=command, timeout=timeout)

    def poll_unsolicited(self) -> "AvrPacket | None":
        """Non-blocking poll for unsolicited packets from the AVR (e.g. CMD_DEBUG_TICK).
        Returns an AvrPacket if one is available, or None if the port is busy or empty.
        Safe to call from any thread; skips silently if a request is in progress.
        """
        if not self._lock.acquire(blocking=False):
            return None  # request in progress — don't touch the serial port
        try:
            return self.receive_packet(expected_command=None, timeout=0.015)
        except (TimeoutError, Exception):
            return None
        finally:
            self._lock.release()

    @staticmethod
    def _expect_status(payload: bytes) -> int:
        if not payload:
            raise AvrProtocolError("Empty payload in AVR response")
        return payload[0]

    def get_info(self) -> dict[str, int]:
        packet = self.request(AvrCommand.GET_INFO)
        status = self._expect_status(packet.payload)
        if status != RSP_OK or len(packet.payload) < 3:
            raise AvrProtocolError(f"GET_INFO failed: {packet.payload.hex(' ')}")
        return {
            "status": status,
            "proto_version": packet.payload[1],
            "mode": packet.payload[2],
        }

    def set_mode(self, mode: InterfaceMode) -> None:
        packet = self.request(AvrCommand.SET_MODE, bytes([int(mode)]))
        if self._expect_status(packet.payload) != RSP_OK:
            raise AvrProtocolError(f"SET_MODE failed: {packet.payload.hex(' ')}")

    def get_mode(self) -> InterfaceMode:
        packet = self.request(AvrCommand.GET_MODE)
        if len(packet.payload) < 2 or packet.payload[0] != RSP_OK:
            raise AvrProtocolError(f"GET_MODE failed: {packet.payload.hex(' ')}")
        return InterfaceMode(packet.payload[1])

    def kline_set_baud(self, baud: int) -> None:
        payload = bytes([baud & 0xFF, (baud >> 8) & 0xFF])
        packet = self.request(AvrCommand.KLINE_SET_BAUD, payload)
        if self._expect_status(packet.payload) != RSP_OK:
            raise AvrProtocolError(f"KLINE_SET_BAUD failed: {packet.payload.hex(' ')}")

    def kline_wakeup(self) -> None:
        packet = self.request(AvrCommand.KLINE_WAKEUP)
        if self._expect_status(packet.payload) != RSP_OK:
            raise AvrProtocolError(f"KLINE_WAKEUP failed: {packet.payload.hex(' ')}")

    def kline_tx_byte(self, value: int) -> None:
        packet = self.request(AvrCommand.KLINE_TX_BYTE, bytes([value & 0xFF]))
        if self._expect_status(packet.payload) != RSP_OK:
            raise AvrProtocolError(f"KLINE_TX_BYTE failed: {packet.payload.hex(' ')}")

    def kline_tx_frame(self, frame: bytes, idle_timeout_ms: int = 50) -> None:
        """
        Envia o frame K-Line inteiro atomicamente dentro do AVR.
        O AVR aguarda o barramento ficar ocioso por >= 11 bit-periods
        (idle_timeout_ms=0 transmite imediatamente sem esperar).

        Se o firmware instalado não suportar CMD 0x13 (firmware antigo),
        faz fallback automático para byte-a-byte via KLINE_TX_BYTE.
        """
        if self._tx_frame_supported is not False:
            # Tenta usar o comando atômico (firmware novo)
            try:
                payload = bytes([idle_timeout_ms & 0xFF]) + bytes(frame)
                usb_timeout = max(1.0, (idle_timeout_ms + len(frame) * 2) / 1000.0 + 0.5)
                packet = self.request(AvrCommand.KLINE_TX_FRAME, payload, timeout=usb_timeout)
                if self._expect_status(packet.payload) == RSP_OK:
                    self._tx_frame_supported = True
                    return
                # RSP_ERR = firmware reconheceu o comando mas bus ficou ocupado
                self._tx_frame_supported = True
                raise AvrProtocolError(f"KLINE_TX_FRAME: bus ocupado (idle timeout={idle_timeout_ms}ms)")
            except (TimeoutError, AvrProtocolError):
                if self._tx_frame_supported is None:
                    # Primeira tentativa falhou — firmware provavelmente antigo, usa fallback
                    self._tx_frame_supported = False
                else:
                    raise  # já confirmamos suporte; erro real

        # Fallback: firmware antigo — envia byte a byte (sem detecção de bus-idle)
        for b in frame:
            self.kline_tx_byte(b)

    def kline_keepalive_start(self, frame: bytes, interval_ms: int = 1500) -> None:
        """Start firmware-side K-Line keepalive (TesterPresent sent autonomously by AVR)."""
        payload = bytes([
            1,
            interval_ms & 0xFF,
            (interval_ms >> 8) & 0xFF,
        ]) + bytes(frame)
        packet = self.request(AvrCommand.KLINE_KEEPALIVE, payload, timeout=1.0)
        if self._expect_status(packet.payload) != RSP_OK:
            raise AvrProtocolError("KLINE_KEEPALIVE start failed")

    def kline_keepalive_stop(self) -> None:
        """Stop firmware-side K-Line keepalive (best-effort)."""
        try:
            self.request(AvrCommand.KLINE_KEEPALIVE, bytes([0]), timeout=1.0)
        except Exception:
            pass

    def kline_rx_byte(self, timeout_ms: int = 100) -> Optional[int]:
        payload = bytes([timeout_ms & 0xFF, (timeout_ms >> 8) & 0xFF])
        packet = self.request(AvrCommand.KLINE_RX_BYTE, payload, timeout=max(1.0, timeout_ms / 1000.0 + 0.5))
        if len(packet.payload) < 2:
            raise AvrProtocolError(f"KLINE_RX_BYTE malformed response: {packet.payload.hex(' ')}")
        if packet.payload[0] == RSP_OK:
            return packet.payload[1]
        if packet.payload[0] == RSP_ERR:
            return None
        raise AvrProtocolError(f"KLINE_RX_BYTE failed: {packet.payload.hex(' ')}")

    def kline_rx_bulk(
        self,
        first_timeout_ms: int = 50,
        inter_timeout_ms: int = 4,
        max_bytes: int = 28,
    ) -> bytes:
        if max_bytes <= 0:
            max_bytes = 28
        if max_bytes > 28:
            max_bytes = 28

        payload = bytes([
            first_timeout_ms & 0xFF,
            (first_timeout_ms >> 8) & 0xFF,
            inter_timeout_ms & 0xFF,
            (inter_timeout_ms >> 8) & 0xFF,
            max_bytes & 0xFF,
        ])
        wait_timeout = max(1.0, (first_timeout_ms + max_bytes * max(inter_timeout_ms, 1)) / 1000.0 + 0.5)
        packet = self.request(AvrCommand.KLINE_RX_BULK, payload, timeout=wait_timeout)
        if len(packet.payload) < 2 or packet.payload[0] != RSP_OK:
            raise AvrProtocolError(f"KLINE_RX_BULK failed: {packet.payload.hex(' ')}")

        count = packet.payload[1]
        chunk = packet.payload[2:2 + count]
        if len(chunk) != count:
            raise AvrProtocolError(f"KLINE_RX_BULK malformed response: {packet.payload.hex(' ')}")
        return chunk

    def kline_rx_bulk_raw(
        self,
        first_timeout_ms: int = 50,
        inter_timeout_ms: int = 4,
        max_bytes: int = 26,
    ) -> tuple:
        """Raw K-Line bulk read including bytes with UART framing errors.

        Returns (raw_bytes: bytes, error_count: int).
        raw_bytes contains all received bytes regardless of FE/DOR.
        error_count is how many of them had framing errors.
        Useful only for baud-rate diagnosis.
        """
        if max_bytes <= 0:
            max_bytes = 26
        if max_bytes > 26:
            max_bytes = 26

        payload = bytes([
            first_timeout_ms & 0xFF,
            (first_timeout_ms >> 8) & 0xFF,
            inter_timeout_ms & 0xFF,
            (inter_timeout_ms >> 8) & 0xFF,
            max_bytes & 0xFF,
        ])
        wait_timeout = max(1.0, (first_timeout_ms + max_bytes * max(inter_timeout_ms, 1)) / 1000.0 + 0.5)
        packet = self.request(AvrCommand.KLINE_RX_BULK_RAW, payload, timeout=wait_timeout)
        if len(packet.payload) < 3 or packet.payload[0] != RSP_OK:
            raise AvrProtocolError(f"KLINE_RX_BULK_RAW failed: {packet.payload.hex(' ')}")
        count     = packet.payload[1]
        err_count = packet.payload[2]
        raw       = packet.payload[3:3 + count]
        if len(raw) != count:
            raise AvrProtocolError(f"KLINE_RX_BULK_RAW malformed: {packet.payload.hex(' ')}")
        return raw, err_count

    def kline_wait_high(self, timeout_ms: int = 30000, stable_ms: int = 20) -> bool:
        payload = bytes([
            timeout_ms & 0xFF,
            (timeout_ms >> 8) & 0xFF,
            stable_ms & 0xFF,
            (stable_ms >> 8) & 0xFF,
        ])
        wait_timeout = max(2.0, timeout_ms / 1000.0 + 1.0)
        packet = self.request(AvrCommand.KLINE_WAIT_HIGH, payload, timeout=wait_timeout)
        if not packet.payload:
            raise AvrProtocolError("KLINE_WAIT_HIGH returned empty payload")
        if packet.payload[0] == RSP_OK:
            return True
        if packet.payload[0] == RSP_ERR:
            return False
        raise AvrProtocolError(f"KLINE_WAIT_HIGH failed: {packet.payload.hex(' ')}")

    def kline_get_status(self, observe_ms: int = 120) -> KlineSignalStatus:
        payload = bytes([
            observe_ms & 0xFF,
            (observe_ms >> 8) & 0xFF,
        ])
        wait_timeout = max(1.0, observe_ms / 1000.0 + 0.8)
        packet = self.request(AvrCommand.KLINE_GET_STATUS, payload, timeout=wait_timeout)
        if len(packet.payload) < 8 or packet.payload[0] != RSP_OK:
            raise AvrProtocolError(f"KLINE_GET_STATUS failed: {packet.payload.hex(' ')}")
        return KlineSignalStatus(
            state=KlineSignalState(packet.payload[1]),
            high_ms=packet.payload[2] | (packet.payload[3] << 8),
            low_ms=packet.payload[4] | (packet.payload[5] << 8),
            edge_count=packet.payload[6],
            rx_byte_count=packet.payload[7],
        )

    def can_set_bitrate(self, kbps: int) -> None:
        payload = bytes([kbps & 0xFF, (kbps >> 8) & 0xFF])
        packet = self.request(AvrCommand.CAN_SET_BITRATE, payload)
        if self._expect_status(packet.payload) != RSP_OK:
            raise AvrProtocolError(f"CAN_SET_BITRATE failed: {packet.payload.hex(' ')}")

    def can_tx_std(self, can_id: int, data: bytes) -> None:
        if can_id < 0 or can_id > 0x7FF:
            raise ValueError("Standard CAN ID must be between 0x000 and 0x7FF")
        if len(data) > 8:
            raise ValueError("CAN payload must be at most 8 bytes")

        payload = bytes([can_id & 0xFF, (can_id >> 8) & 0x07, len(data)]) + data
        packet = self.request(AvrCommand.CAN_TX_STD, payload)
        if self._expect_status(packet.payload) != RSP_OK:
            raise AvrProtocolError(f"CAN_TX_STD failed: {packet.payload.hex(' ')}")

    def can_rx_poll(self) -> Optional[CanFrame]:
        packet = self.request(AvrCommand.CAN_RX_POLL)
        if not packet.payload:
            raise AvrProtocolError("CAN_RX_POLL returned empty payload")
        if packet.payload[0] == RSP_NO_DATA:
            return None
        if packet.payload[0] != RSP_OK or len(packet.payload) < 4:
            raise AvrProtocolError(f"CAN_RX_POLL failed: {packet.payload.hex(' ')}")

        can_id = packet.payload[1] | ((packet.payload[2] & 0x07) << 8)
        dlc = packet.payload[3]
        data = packet.payload[4 : 4 + dlc]
        return CanFrame(can_id=can_id, data=data)

    def can_get_status(self) -> CanStatus:
        packet = self.request(AvrCommand.CAN_GET_STATUS)
        if len(packet.payload) < 10 or packet.payload[0] != RSP_OK:
            raise AvrProtocolError(f"CAN_GET_STATUS failed: {packet.payload.hex(' ')}")

        return CanStatus(
            status=packet.payload[1],
            rx_error_counter=packet.payload[2],
            tx_error_counter=packet.payload[3],
            error_code_capture=packet.payload[4],
            arbitration_lost_capture=packet.payload[5],
            error_warning_limit=packet.payload[6],
            rx_message_count=packet.payload[7],
            bitrate_kbps=packet.payload[8] | (packet.payload[9] << 8),
        )

    # ------------------------------------------------------------------
    # Bootloader FT245 (0x70–0x75)
    # Somente válidos quando o AVR está no modo bootloader.
    # ------------------------------------------------------------------

    _BL_CHUNK_DATA = 29  # MAX_PAYLOAD(31) - 3 bytes de cabeçalho write_page

    def bl_get_info(self) -> dict:
        """Retorna informações do bootloader: version, page_size, app_pages, boot_start."""
        packet = self.request(AvrCommand.BL_GET_INFO, timeout=3.0)
        p = packet.payload
        if len(p) < 7 or p[0] != RSP_OK:
            raise AvrProtocolError(f"BL_GET_INFO failed: {p.hex(' ')}")
        return {
            "version":    p[1],
            "page_size":  p[2] | (p[3] << 8),
            "app_pages":  p[4],
            "boot_start": p[5] | (p[6] << 8),
        }

    def bl_erase_app(self) -> None:
        """Apaga toda a seção de aplicação (60 páginas × 256 bytes)."""
        packet = self.request(AvrCommand.BL_ERASE_APP, timeout=15.0)
        if not packet.payload or packet.payload[0] != RSP_OK:
            raise AvrProtocolError(f"BL_ERASE_APP failed: {packet.payload.hex(' ')}")

    def bl_write_page(self, page_num: int, data: bytes) -> None:
        """
        Grava uma página completa (256 bytes) enviando em chunks de 29 bytes.
        page_num: 0–59 (área de aplicação).
        data: exatamente 256 bytes.
        """
        if len(data) != 256:
            raise ValueError(f"bl_write_page: esperado 256 bytes, recebeu {len(data)}")
        offset = 0
        while offset < 256:
            chunk = data[offset: offset + self._BL_CHUNK_DATA]
            payload = bytes([page_num, offset, len(chunk)]) + chunk
            packet = self.request(AvrCommand.BL_WRITE_PAGE, payload, timeout=5.0)
            if not packet.payload or packet.payload[0] != RSP_OK:
                raise AvrProtocolError(
                    f"BL_WRITE_PAGE failed page={page_num} offset={offset}: {packet.payload.hex(' ')}"
                )
            offset += len(chunk)

    def bl_verify_crc(self, byte_addr: int, length: int, expected_crc: int) -> bool:
        """Verifica CRC16-CCITT de uma faixa da flash. Retorna True se OK."""
        import struct
        payload = struct.pack("<HHH", byte_addr, length, expected_crc)
        packet = self.request(AvrCommand.BL_VERIFY_CRC, payload, timeout=5.0)
        p = packet.payload
        if len(p) < 1:
            raise AvrProtocolError("BL_VERIFY_CRC: resposta vazia")
        return p[0] == RSP_OK

    def bl_jump_app(self) -> None:
        """Salta para a aplicação. Não espera resposta (AVR reseta para app)."""
        self.send_packet(AvrCommand.BL_JUMP_APP)