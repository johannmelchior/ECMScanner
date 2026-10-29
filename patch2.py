with open('ecm_scanner/main.py', 'rb') as f:
    data = f.read()

old = (
    b'                try:\r\n'
    b'                    # Envia o frame inteiro atomicamente dentro do AVR.\r\n'
    b'                    # O AVR aguarda o bus ficar ocioso (idle_timeout_ms=50ms) antes de TX,\r\n'
    b'                    # evitando colis\xc3\x83\xc2\xa3o com frames ECM\xc3\xa2\xe2\x80\xa0\xe2\x80\x99painel que ocupam o bus a 48 Hz.\r\n'
    b'                    frame_bytes = bytes(frame)\r\n'
    b'                    t.kline_tx_frame(frame_bytes, idle_timeout_ms=50)\r\n'
    b'                    # Log the keepalive TX frame to CSV\r\n'
    b'                    self._kline_record("TX", frame)\r\n'
    b'                    # Collect and log ECU response (up to 10 bytes, 100 ms timeout each)\r\n'
    b'                    rx_buf = []\r\n'
    b'                    for _ in range(10):\r\n'
    b'                        b = t.kline_rx_byte(100)\r\n'
    b'                        if b is None:\r\n'
    b'                            break\r\n'
    b'                        rx_buf.append(b)\r\n'
    b'                    if rx_buf:\r\n'
    b'                        self._kline_record("RX", rx_buf)\r\n'
    b'                except Exception:\r\n'
    b'                    # Transport error on a single keepalive cycle: exit the thread but do NOT\r\n'
    b'                    # clear _kline_active. The K-Line session may still be alive; the user can\r\n'
    b'                    # re-enable the checkbox to restart keepalive without losing the session.\r\n'
    b'                    break\r\n'
    b'                finally:\r\n'
    b'                    self._kline_session_lock.release()\r\n'
)

new = (
    b'                try:\r\n'
    b'                    # Envia o frame inteiro atomicamente dentro do AVR.\r\n'
    b'                    # idle_timeout_ms=200: aguarda ate 200 ms para o bus ficar ocioso,\r\n'
    b'                    # suficiente para o ECU terminar qualquer frame periodico a 10400 baud.\r\n'
    b'                    frame_bytes = bytes(frame)\r\n'
    b'                    t.kline_tx_frame(frame_bytes, idle_timeout_ms=200)\r\n'
    b'                    # Log the keepalive TX frame to CSV\r\n'
    b'                    self._kline_record("TX", frame)\r\n'
    b'                    # Collect and log ECU response (up to 10 bytes, 100 ms timeout each)\r\n'
    b'                    rx_buf = []\r\n'
    b'                    for _ in range(10):\r\n'
    b'                        b = t.kline_rx_byte(100)\r\n'
    b'                        if b is None:\r\n'
    b'                            break\r\n'
    b'                        rx_buf.append(b)\r\n'
    b'                    if rx_buf:\r\n'
    b'                        self._kline_record("RX", rx_buf)\r\n'
    b'                except Exception as _ka_err:\r\n'
    b'                    # Transient error (bus busy, timeout): log and retry next cycle.\r\n'
    b'                    # Only abort if transport is gone or session was closed.\r\n'
    b'                    if self.avr_transport is None or not self._kline_active:\r\n'
    b'                        break\r\n'
    b'                    self._avr_log(f"  [keepalive] erro transitorio: {_ka_err} - tentando novamente\\n")\r\n'
    b'                    # continue to next sleep cycle\r\n'
    b'                finally:\r\n'
    b'                    self._kline_session_lock.release()\r\n'
)

if old in data:
    data = data.replace(old, new, 1)
    with open('ecm_scanner/main.py', 'wb') as f:
        f.write(data)
    print('OK')
else:
    print('NOT FOUND')
    # Debug: show surrounding bytes
    idx = data.find(b'idle_timeout_ms=50')
    if idx >= 0:
        print(repr(data[idx-200:idx+200]))
