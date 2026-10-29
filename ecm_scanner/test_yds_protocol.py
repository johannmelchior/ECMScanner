"""Testes do elo serie YDS (``yds_protocol``) contra um transporte falso.

Correr:  python -m unittest test_yds_protocol -v
"""

import unittest
from unittest import mock

import yds_protocol as yds


class FakeTransport:
    """Transporte AVR simulado; ``responder`` diz o que o modulo devolve."""

    def __init__(self, responder, echo=True):
        self.responder = responder
        self.echo = echo
        self.rx = []
        self.baud = None
        self.events = []

    # -- API usada por YdsByteLink -----------------------------------------
    def kline_set_baud(self, baud):
        self.baud = baud
        self.events.append(("baud", baud))

    def kline_tx_byte(self, value):
        self.events.append(("tx", value, self.baud))
        if self.echo:
            self.rx.append(value)
        answer = self.responder(value)
        if answer is not None:
            self.rx.append(answer)

    def kline_rx_byte(self, timeout_ms):
        return self.rx.pop(0) if self.rx else None

    def kline_rx_bulk(self, first_timeout_ms=1, inter_timeout_ms=0, max_bytes=28):
        self.rx.clear()
        return b""


def standard_responder(e5=0xEF, fe=0x11, ff=0x22, ladder=0xF0):
    """Responde como um equipamento Yamaha saudavel."""

    def respond(value):
        if value == 0xFD:
            return 0x00
        if value == 0xE5:
            return e5
        if value == 0xFE:
            return fe
        if value == 0xFF:
            return ff
        if value == ladder and 0xE0 <= value <= 0xF0:
            return 0xAA
        return None

    return respond


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(yds.time, "sleep", lambda _s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_echo_transport(self):
        link = yds.YdsByteLink(FakeTransport(standard_responder(), echo=True))
        result = link.exchange(0xFD)
        self.assertEqual(result.status, yds.EX_OK)
        self.assertEqual(result.echo, 0xFD)
        self.assertEqual(result.response, 0x00)
        self.assertIs(link.echo_mode, True)

    def test_no_echo_transport(self):
        link = yds.YdsByteLink(FakeTransport(standard_responder(), echo=False))
        result = link.exchange(0xFD)
        self.assertEqual(result.status, yds.EX_OK_NO_ECHO)
        self.assertIsNone(result.echo)
        self.assertEqual(result.response, 0x00)
        self.assertIs(link.echo_mode, False)

    def test_timeout_retries_three_times(self):
        transport = FakeTransport(lambda _v: None, echo=False)
        link = yds.YdsByteLink(transport)
        result = link.exchange(0xFD)
        self.assertEqual(result.status, yds.EX_TIMEOUT)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len([e for e in transport.events if e[0] == "tx"]), 3)

    def test_echo_without_answer(self):
        link = yds.YdsByteLink(FakeTransport(lambda _v: None, echo=True))
        result = link.exchange(0xFD)
        self.assertEqual(result.status, yds.EX_NO_RESPONSE)
        self.assertEqual(result.echo, 0xFD)


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(yds.time, "sleep", lambda _s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_variant_a(self):
        link = yds.YdsByteLink(FakeTransport(standard_responder(e5=0xEF)))
        session = link.handshake()
        self.assertTrue(session.ok, session.detail)
        self.assertEqual(session.variant, 0)
        self.assertEqual(session.ident_fe, 0x11)
        self.assertEqual(session.ident_ff, 0x22)
        self.assertIs(session.echo_required, True)

    def test_variant_b(self):
        link = yds.YdsByteLink(FakeTransport(standard_responder(e5=0xED)))
        session = link.handshake()
        self.assertTrue(session.ok, session.detail)
        self.assertEqual(session.variant, 1)

    def test_rejects_unexpected_e5_answer(self):
        link = yds.YdsByteLink(FakeTransport(standard_responder(e5=0x00)))
        session = link.handshake()
        self.assertFalse(session.ok)
        self.assertIn("0xEF", session.detail)
        self.assertIn("0xED", session.detail)

    def test_rejects_non_repeating_fe(self):
        seen = {"fe": 0}

        def responder(value):
            if value == 0xFE:
                seen["fe"] += 1
                return 0x11 if seen["fe"] == 1 else 0x12
            return standard_responder()(value)

        link = yds.YdsByteLink(FakeTransport(responder))
        session = link.handshake()
        self.assertFalse(session.ok)
        self.assertIn("0xFE", session.detail)

    def test_handshake_sequence_on_the_wire(self):
        transport = FakeTransport(standard_responder())
        link = yds.YdsByteLink(transport)
        link.handshake()
        sent = [e[1] for e in transport.events if e[0] == "tx"]
        self.assertEqual(sent, list(yds.YDS_HANDSHAKE))


class SessionTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(yds.time, "sleep", lambda _s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_wakeup_sends_0x1c_at_300_baud_then_9600(self):
        transport = FakeTransport(standard_responder())
        link = yds.YdsByteLink(transport)
        link.wakeup()
        bauds = [e[1] for e in transport.events if e[0] == "baud"]
        self.assertEqual(bauds, [yds.YDS_WAKE_BAUD, yds.YDS_WORK_BAUD])
        wake = [e for e in transport.events if e[0] == "tx"]
        self.assertEqual(wake[0][1], yds.YDS_WAKE_BYTE)
        self.assertEqual(wake[0][2], yds.YDS_WAKE_BAUD)

    def test_open_session_probes_ladder(self):
        transport = FakeTransport(standard_responder(ladder=0xEE))
        link = yds.YdsByteLink(transport)
        session = link.open_session()
        self.assertTrue(session.ok, session.detail)
        self.assertEqual(session.module_address, 0xEE)
        self.assertEqual(session.module_ident, 0xAA)

    def test_open_session_fails_without_ladder_answer(self):
        transport = FakeTransport(standard_responder(ladder=None))
        link = yds.YdsByteLink(transport)
        session = link.open_session()
        self.assertFalse(session.ok)
        self.assertIn("escada", session.detail)

    def test_send_sequence_collects_answers(self):
        link = yds.YdsByteLink(FakeTransport(standard_responder()))
        self.assertEqual(link.send_sequence([0xFD, 0xE5]), [0x00, 0xEF])

    def test_ping(self):
        link = yds.YdsByteLink(FakeTransport(standard_responder()))
        self.assertTrue(link.ping(0xFE))
        self.assertFalse(yds.YdsByteLink(FakeTransport(lambda _v: None)).ping(0xFE))


if __name__ == "__main__":
    unittest.main()
