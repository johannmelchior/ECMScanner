"""Ligacao serie Yamaha no estilo YDS, reconstruida por engenharia inversa.

Analise estatica de ``C:\\Program Files\\YDS\\YDS.exe`` (Delphi, Ghidra 12.1.4)
mostra que o Yamaha Diagnostic System **nao** fala KWP2000 no elo PC<->caixa.
Esse elo e um protocolo orientado a byte, 9600 8N1:

===========================  =============================================
Funcao                       Comportamento
===========================  =============================================
``FUN_0046ebe0``             abre ``COM%d``; leitura nao bloqueante,
                             escrita com 20 s de timeout
``FUN_0046f140``             DCB: 8N1, sem flow control, DTR/RTS activos
``FUN_0046eeb0``             envia 1 byte (WriteFile de 1 byte)
``FUN_0046efc0``             recebe 1 byte com timeout, via ClearCommError
``FUN_00479570``             PurgeComm -> TX 1 byte -> RX eco -> RX resposta
                             (3 tentativas, 110 ms por byte)
``FUN_004798f0``             abertura: 300 baud + 0x1C, depois 9600 e o
                             handshake FD E5 E5 FE FF FE FF
``FUN_0047a120``             escada de enderecos F0 EF EE ED EC E4 E3 E2 E1 E0
===========================  =============================================

Nenhuma constante ``10400`` (0x28A0) nem ``15625`` (0x3D09) existe no binario:
a unica constante de baud na zona de comunicacao e ``0x2580`` = 9600.

Este modulo implementa esse elo sobre o transporte AVR. Como o AVR liga
directamente a K-Line, o eco pode ou nao existir (eco do proprio UART em
barramento de um fio, eco da ECU, ou nenhum); :meth:`YdsByteLink.exchange`
detecta-o sozinho e fixa o modo depois da primeira troca inequivoca.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

# --- constantes extraidas do YDS.exe ---------------------------------------

YDS_WAKE_BAUD = 300
"""Baud usado so para injectar o byte de wake-up (FUN_004798f0)."""

YDS_WORK_BAUD = 9600
"""Baud de trabalho (0x2580 em todos os call sites de FUN_0046ebe0)."""

YDS_WAKE_BYTE = 0x1C
"""Byte injectado a 300 baud antes de reabrir a 9600."""

YDS_BYTE_TIMEOUT_MS = 110
"""``PUSH 0x6E`` antes de cada troca de byte."""

YDS_ATTEMPTS = 3
"""Repeticoes de FUN_00479570 (FUN_00479730 usa apenas 1)."""

YDS_HANDSHAKE = (0xFD, 0xE5, 0xE5, 0xFE, 0xFF, 0xFE, 0xFF)
"""Sequencia de abertura observada em FUN_004798f0."""

YDS_E5_ANSWERS = {0xEF: 0, 0xED: 1}
"""Resposta a 0xE5 -> variante do equipamento (self+0x4C)."""

YDS_ADDRESS_LADDER = (0xF0, 0xEF, 0xEE, 0xED, 0xEC, 0xE4, 0xE3, 0xE2, 0xE1, 0xE0)
"""Ordem de sondagem do endereco do modulo (FUN_0047a120)."""

# --- resultados ------------------------------------------------------------

EX_OK = "ok"                      # eco + resposta obtidos
EX_OK_NO_ECHO = "ok-sem-eco"      # transporte sem eco; o 1o byte e a resposta
EX_TIMEOUT = "timeout"            # nada chegou dentro do timeout
EX_NO_RESPONSE = "sem-resposta"   # veio o eco mas nao veio a resposta
EX_TX_ERROR = "erro-tx"           # o AVR recusou a transmissao


@dataclass
class ExchangeResult:
    status: str
    sent: int
    echo: Optional[int] = None
    response: Optional[int] = None
    attempts: int = 1
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (EX_OK, EX_OK_NO_ECHO)

    def __bool__(self) -> bool:
        return self.ok

    def describe(self) -> str:
        if self.response is not None:
            txt = f"0x{self.sent:02X} -> 0x{self.response:02X}"
            if self.echo is not None:
                txt += f" (eco 0x{self.echo:02X})"
            if self.attempts > 1:
                txt += f" [{self.attempts}x]"
            return txt
        return f"0x{self.sent:02X} -> {self.status}"


@dataclass
class YdsSession:
    ok: bool
    variant: Optional[int] = None
    module_address: Optional[int] = None
    module_ident: Optional[int] = None
    ident_fe: Optional[int] = None
    ident_ff: Optional[int] = None
    echo_required: Optional[bool] = None
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


class YdsByteLink:
    """Elo byte-a-byte do YDS sobre um ``AvrTransport``."""

    def __init__(
        self,
        transport,
        log: Optional[Callable[[str], None]] = None,
        byte_timeout_ms: int = YDS_BYTE_TIMEOUT_MS,
        attempts: int = YDS_ATTEMPTS,
        echo_mode: Optional[bool] = None,
    ) -> None:
        self.t = transport
        self._log = log or (lambda _s: None)
        self.byte_timeout_ms = int(byte_timeout_ms)
        self.attempts = max(1, int(attempts))
        self.echo_mode = echo_mode
        self.last_good_response: Optional[int] = None

    # -- baixo nivel --------------------------------------------------------

    def _emit(self, text: str) -> None:
        try:
            self._log(text)
        except Exception:
            pass

    def purge(self, rounds: int = 2) -> None:
        """Equivalente ao PurgeComm do YDS: esvazia o buffer de recepcao."""
        for _ in range(max(1, rounds)):
            try:
                self.t.kline_rx_bulk(
                    first_timeout_ms=1, inter_timeout_ms=0, max_bytes=8
                )
            except Exception:
                pass

    def _read_byte(self, timeout_ms: int) -> Optional[int]:
        try:
            value = self.t.kline_rx_byte(timeout_ms)
        except Exception:
            return None
        return value

    def exchange(
        self,
        value: int,
        timeout_ms: Optional[int] = None,
        attempts: Optional[int] = None,
    ) -> ExchangeResult:
        """PurgeComm -> TX 1 byte -> RX eco -> RX resposta (FUN_00479570)."""
        value &= 0xFF
        timeout_ms = self.byte_timeout_ms if timeout_ms is None else int(timeout_ms)
        attempts = self.attempts if attempts is None else max(1, int(attempts))
        result = ExchangeResult(EX_TIMEOUT, value)

        for attempt in range(1, attempts + 1):
            self.purge()
            try:
                self.t.kline_tx_byte(value)
            except Exception as exc:
                result = ExchangeResult(EX_TX_ERROR, value, attempts=attempt,
                                        detail=str(exc))
                continue

            first = self._read_byte(timeout_ms)
            if first is None:
                result = ExchangeResult(EX_TIMEOUT, value, attempts=attempt)
                continue

            if self.echo_mode is False:
                # Transporte sem eco: o primeiro byte ja e a resposta.
                self.last_good_response = first
                return ExchangeResult(EX_OK_NO_ECHO, value, None, first,
                                      attempt)

            if first == value:
                self.echo_mode = True
                second = self._read_byte(timeout_ms)
                if second is None:
                    result = ExchangeResult(EX_NO_RESPONSE, value, first, None,
                                            attempt)
                    continue
                self.last_good_response = second
                return ExchangeResult(EX_OK, value, first, second, attempt)

            # O primeiro byte difere do enviado: nao ha eco neste transporte.
            if self.echo_mode is None:
                self.echo_mode = False
            self.last_good_response = first
            return ExchangeResult(EX_OK_NO_ECHO, value, None, first, attempt)

        return result

    # -- camada de sessao ---------------------------------------------------

    def wakeup(
        self,
        wake_baud: int = YDS_WAKE_BAUD,
        work_baud: int = YDS_WORK_BAUD,
        wake_byte: int = YDS_WAKE_BYTE,
    ) -> None:
        """Abre a 300 baud, injecta 0x1C e volta aos 9600 (FUN_004798f0)."""
        self._emit(f"  KLINE_SET_BAUD {wake_baud} (wake-up) ... ")
        self.t.kline_set_baud(wake_baud)
        self._emit("OK\n")
        time.sleep(0.05)

        self.purge()
        self._emit(f"> TX wake 0x{wake_byte:02X} @ {wake_baud} baud ... ")
        self.t.kline_tx_byte(wake_byte)
        self._emit("OK\n")
        # 0x1C a 300 baud ocupa 10 bits = 33 ms; o AVR ja espera por TXC,
        # mas deixamos a linha assentar antes de mudar de baud.
        time.sleep(0.04)
        self.purge()

        self._emit(f"  KLINE_SET_BAUD {work_baud} ... ")
        self.t.kline_set_baud(work_baud)
        self._emit("OK\n")
        time.sleep(0.05)
        self.purge()

    def handshake(self) -> YdsSession:
        """Sequencia FD E5 E5 FE FF FE FF com verificacao de eco/repeticao."""
        self._emit("  handshake YDS: FD E5 E5 FE FF FE FF\n")

        result = self.exchange(YDS_HANDSHAKE[0])
        self._emit(f"    0xFD  {result.describe()}\n")
        if not result.ok:
            return YdsSession(False, detail=f"sem resposta a 0xFD ({result.status})",
                              echo_required=self.echo_mode)

        variants = []
        for _ in range(2):
            result = self.exchange(0xE5)
            self._emit(f"    0xE5  {result.describe()}\n")
            if not result.ok:
                return YdsSession(False, detail=f"sem resposta a 0xE5 ({result.status})",
                                  echo_required=self.echo_mode)
            variant = YDS_E5_ANSWERS.get(result.response)
            if variant is None:
                return YdsSession(
                    False,
                    detail=(f"0xE5 respondeu 0x{result.response:02X}; "
                            "esperado 0xEF ou 0xED"),
                    echo_required=self.echo_mode,
                )
            variants.append(variant)

        if len(set(variants)) != 1:
            return YdsSession(False, detail="0xE5 respondeu de forma inconsistente",
                              echo_required=self.echo_mode)

        first_fe = self.exchange(0xFE)
        self._emit(f"    0xFE  {first_fe.describe()}\n")
        first_ff = self.exchange(0xFF)
        self._emit(f"    0xFF  {first_ff.describe()}\n")
        if not (first_fe.ok and first_ff.ok):
            return YdsSession(False, variant=variants[-1],
                              detail="sem resposta a 0xFE/0xFF",
                              echo_required=self.echo_mode)

        again_fe = self.exchange(0xFE)
        self._emit(f"    0xFE  {again_fe.describe()}\n")
        if again_fe.response != first_fe.response:
            return YdsSession(False, variant=variants[-1],
                              detail=(f"0xFE nao repetiu (0x{first_fe.response:02X} "
                                      f"vs {self._hex(again_fe.response)})"),
                              echo_required=self.echo_mode)

        again_ff = self.exchange(0xFF)
        self._emit(f"    0xFF  {again_ff.describe()}\n")
        if again_ff.response != first_ff.response:
            return YdsSession(False, variant=variants[-1],
                              detail=(f"0xFF nao repetiu (0x{first_ff.response:02X} "
                                      f"vs {self._hex(again_ff.response)})"),
                              echo_required=self.echo_mode)

        return YdsSession(True, variant=variants[-1],
                          ident_fe=first_fe.response, ident_ff=first_ff.response,
                          echo_required=self.echo_mode)

    def probe_address(self) -> tuple:
        """Escada F0..E0 (FUN_0047a120); devolve (endereco, resultado)."""
        for candidate in YDS_ADDRESS_LADDER:
            result = self.exchange(candidate)
            self._emit(f"    0x{candidate:02X}  {result.describe()}\n")
            if result.ok:
                return candidate, result
        return None, None

    def open_session(self, probe: bool = True) -> YdsSession:
        """Abertura completa: wake-up, handshake e (opcional) escada."""
        self.wakeup()
        session = self.handshake()
        if not session.ok or not probe:
            return session

        self._emit("  escada de enderecos YDS:\n")
        address, result = self.probe_address()
        if address is None:
            session.ok = False
            session.detail = "nenhum endereco da escada respondeu"
            return session
        session.module_address = address
        session.module_ident = result.response
        return session

    # -- camada de comandos -------------------------------------------------

    def send_sequence(self, values: Iterable[int],
                      timeout_ms: Optional[int] = None) -> list:
        """Envia varios bytes, um a um, devolvendo as respostas obtidas.

        O YDS so escreve 1 byte de cada vez (a unica chamada a WriteFile esta
        em FUN_0046eeb0), por isso um "comando" e uma sequencia de trocas.
        """
        responses = []
        for value in values:
            result = self.exchange(value, timeout_ms=timeout_ms)
            if not result.ok:
                break
            responses.append(result.response)
        return responses

    def ping(self, value: int = 0xFE) -> bool:
        """Verifica se o modulo continua a responder."""
        expected = self.last_good_response
        result = self.exchange(value, attempts=1)
        if not result.ok:
            return False
        if result.sent == value and expected is not None:
            # Nao comparamos por igualdade: 0xFE/0xFF sao bytes de identidade
            # cujo valor pode variar; basta haver resposta.
            return True
        return True

    @staticmethod
    def _hex(value: Optional[int]) -> str:
        return "--" if value is None else f"0x{value:02X}"
