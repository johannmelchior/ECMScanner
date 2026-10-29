"""
Patch main.py:
1. Yamaha init: replace Python thread keepalive with firmware keepalive
2. Kawasaki init: same
3. toggle_keep_alive: use firmware start/stop for AVR K-Line
"""

with open('ecm_scanner/main.py', 'rb') as f:
    data = f.read()

patches = []

# ---- Patch 1: Yamaha init ----
old1 = (
    b'                self._kline_active = True\r\n'
    b'                self._kline_proto = "yamaha"\r\n'
    b'                threading.Thread(target=self._kline_keepalive_loop, daemon=True).start()\r\n'
    b'                self._avr_log("  Keepalive iniciado (TesterPresent 3E 01 a cada 1.5s)\\n")\r\n'
)
new1 = (
    b'                self._kline_active = True\r\n'
    b'                self._kline_proto = "yamaha"\r\n'
    b'                if self.kwp_keep_alive_var.get():\r\n'
    b'                    try:\r\n'
    b'                        _ka_frame = bytes([0x82, 0x11, 0xF1, 0x3E, 0x01, 0xC3])\r\n'
    b'                        t.kline_keepalive_start(_ka_frame, interval_ms=1500)\r\n'
    b'                        self._avr_log("  Keepalive iniciado no firmware (TesterPresent a cada 1.5s)\\n")\r\n'
    b'                    except Exception as _ka_e:\r\n'
    b'                        self._avr_log(f"  Keepalive firmware nao suportado ({_ka_e}); sem keepalive\\n")\r\n'
    b'                else:\r\n'
    b'                    self._avr_log("  Keepalive desativado (marque Keep-Alive para manter sessao)\\n")\r\n'
)
if old1 in data:
    data = data.replace(old1, new1, 1)
    patches.append('Patch 1 (Yamaha init) OK')
else:
    patches.append('Patch 1 (Yamaha init) FAIL')

# ---- Patch 2: Kawasaki init ----
old2 = (
    b'                self._kline_active = True\r\n'
    b'                self._kline_proto = "kawasaki"\r\n'
    b'                if self.kwp_keep_alive_var.get():\r\n'
    b'                    threading.Thread(target=self._kline_keepalive_loop, daemon=True).start()\r\n'
    b'                    self._avr_log("  Keepalive iniciado (TesterPresent 3E 01 a cada 1.5s)\\n")\r\n'
    b'                else:\r\n'
    b'                    self._avr_log("  Keepalive desativado (marque Keep-Alive para manter sessao)\\n")\r\n'
)
new2 = (
    b'                self._kline_active = True\r\n'
    b'                self._kline_proto = "kawasaki"\r\n'
    b'                if self.kwp_keep_alive_var.get():\r\n'
    b'                    try:\r\n'
    b'                        _ka_frame = bytes([0x82, 0x13, 0xF1, 0x3E, 0x01, 0xC5])\r\n'
    b'                        t.kline_keepalive_start(_ka_frame, interval_ms=1500)\r\n'
    b'                        self._avr_log("  Keepalive iniciado no firmware (TesterPresent a cada 1.5s)\\n")\r\n'
    b'                    except Exception as _ka_e:\r\n'
    b'                        self._avr_log(f"  Keepalive firmware nao suportado ({_ka_e}); sem keepalive\\n")\r\n'
    b'                else:\r\n'
    b'                    self._avr_log("  Keepalive desativado (marque Keep-Alive para manter sessao)\\n")\r\n'
)
if old2 in data:
    data = data.replace(old2, new2, 1)
    patches.append('Patch 2 (Kawasaki init) OK')
else:
    patches.append('Patch 2 (Kawasaki init) FAIL')

# ---- Patch 3: toggle_keep_alive AVR K-Line branch ----
old3 = (
    b'    def toggle_keep_alive(self):\r\n'
    b'        if self.kwp_keep_alive_var.get():\r\n'
    b'            # AVR K-Line mode: start the K-Line TesterPresent thread if session is alive\r\n'
    b'            if (self.connection_mode == "AVR"\r\n'
    b'                    and self.avr_bus_var.get() == "K-Line"\r\n'
    b'                    and self._kline_active):\r\n'
    b'                if self._kline_keepalive_dead.is_set():\r\n'
    b'                    threading.Thread(target=self._kline_keepalive_loop, daemon=True).start()\r\n'
    b'                    self._avr_log("Keepalive K-Line iniciado (TesterPresent 3E 01).\\n")\r\n'
    b'                return\r\n'
    b'            # CAN / serial modes: use the generic keep_alive_loop\r\n'
    b'            self.keep_alive_thread = threading.Thread(target=self.keep_alive_loop, daemon=True)\r\n'
    b'            self.keep_alive_thread.start()\r\n'
    b'            self.console_textbox.insert("end", "Keep-Alive Started.\\n")\r\n'
    b'        else:\r\n'
    b'            self._avr_log("Keep-Alive desativado.\\n")\r\n'
)
new3 = (
    b'    def toggle_keep_alive(self):\r\n'
    b'        enabled = self.kwp_keep_alive_var.get()\r\n'
    b'        if (self.connection_mode == "AVR"\r\n'
    b'                and self.avr_bus_var.get() == "K-Line"\r\n'
    b'                and self._kline_active):\r\n'
    b'            # AVR K-Line: delega keepalive ao firmware\r\n'
    b'            t = self.avr_transport\r\n'
    b'            if t is not None:\r\n'
    b'                if enabled:\r\n'
    b'                    try:\r\n'
    b'                        ecu_addr = 0x11 if self._kline_proto == "yamaha" else 0x13\r\n'
    b'                        chk = (0x82 + ecu_addr + 0xF1 + 0x3E + 0x01) & 0xFF\r\n'
    b'                        _ka_frame = bytes([0x82, ecu_addr, 0xF1, 0x3E, 0x01, chk])\r\n'
    b'                        t.kline_keepalive_start(_ka_frame, interval_ms=1500)\r\n'
    b'                        self._avr_log("Keepalive K-Line iniciado no firmware (TesterPresent 3E 01).\\n")\r\n'
    b'                    except Exception as _e:\r\n'
    b'                        self._avr_log(f"Keepalive firmware erro: {_e}\\n")\r\n'
    b'                else:\r\n'
    b'                    t.kline_keepalive_stop()\r\n'
    b'                    self._avr_log("Keepalive K-Line parado no firmware.\\n")\r\n'
    b'            return\r\n'
    b'        # CAN / serial modes: use the generic keep_alive_loop\r\n'
    b'        if enabled:\r\n'
    b'            self.keep_alive_thread = threading.Thread(target=self.keep_alive_loop, daemon=True)\r\n'
    b'            self.keep_alive_thread.start()\r\n'
    b'            self.console_textbox.insert("end", "Keep-Alive Started.\\n")\r\n'
    b'        else:\r\n'
    b'            self._avr_log("Keep-Alive desativado.\\n")\r\n'
)
if old3 in data:
    data = data.replace(old3, new3, 1)
    patches.append('Patch 3 (toggle_keep_alive) OK')
else:
    patches.append('Patch 3 (toggle_keep_alive) FAIL')

with open('ecm_scanner/main.py', 'wb') as f:
    f.write(data)

for p in patches:
    print(p)
