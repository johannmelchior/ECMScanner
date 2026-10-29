import customtkinter as ctk
import serial
import serial.tools.list_ports
import threading
import time
import socket
try:
    from avr_interface import AvrTransport, InterfaceMode
    AVR_IMPORT_ERROR = None
except Exception as avr_import_exc:
    AvrTransport = None
    InterfaceMode = None
    AVR_IMPORT_ERROR = str(avr_import_exc)
try:
    from yds_protocol import YdsByteLink, YDS_WAKE_BAUD
    YDS_IMPORT_ERROR = None
except Exception as yds_import_exc:
    YdsByteLink = None
    YDS_WAKE_BAUD = 300
    YDS_IMPORT_ERROR = str(yds_import_exc)
try:
    import can
    CAN_IMPORT_ERROR = None
except Exception as can_import_exc:
    can = None
    CAN_IMPORT_ERROR = str(can_import_exc)
from tkinter import ttk
from tkinter import filedialog
import tkinter as tk
import math
import csv
import os
import json
from datetime import datetime
from collections import deque

class ToolTip:
    """
    A robust ToolTip class for Tkinter/CustomTkinter widgets.
    Displays text in a small popup window after a hovering delay.
    """
    def __init__(self, widget, text, delay=1000):
        """
        :param widget: The widget to attach the tooltip to.
        :param text: The text to display in the tooltip.
        :param delay: Delay in milliseconds before showing the tooltip (default 2000ms).
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.id = None
        # Use add='+' to avoid overwriting existing bindings
        self.widget.bind("<Enter>", self.on_enter, add="+")
        self.widget.bind("<Leave>", self.on_leave, add="+")
        self.widget.bind("<ButtonPress>", self.on_leave, add="+")

    def on_enter(self, event=None):
        self.schedule_tooltip()

    def on_leave(self, event=None):
        self.hide_tooltip()
        self.cancel_schedule()

    def schedule_tooltip(self):
        self.cancel_schedule()
        self.id = self.widget.after(self.delay, self.show_tooltip)

    def cancel_schedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def show_tooltip(self):
        if self.tooltip_window or not self.text:
            return
        
        # Calculate position near the mouse cursor
        x = self.widget.winfo_pointerx() + 15
        y = self.widget.winfo_pointery() + 15

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        # Ensure it stays on top
        self.tooltip_window.attributes("-topmost", True)
        
        # Tooltip styling
        label = tk.Label(
            self.tooltip_window, 
            text=self.text, 
            background="#ffffe0",  # Light yellow background
            foreground="#000000",  # Black text
            relief="solid", 
            borderwidth=1,
            font=("Arial", "10", "normal"),
            padx=5,
            pady=3,
            wraplength=300,        # Wrap text if it's too long
            justify="left"
        )
        label.pack()

    def hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

BRP_DTC_DB_PATH = os.path.join(os.path.dirname(__file__), "brp_dtc_codes.json")
YAMAHA_DTC_DB_PATH = os.path.join(os.path.dirname(__file__), "yamaha_dtc_codes.json")
YAMAHA_YDS_DB_PATH = os.path.join(os.path.dirname(__file__), "yamaha_yds_items.json")
BRP_MODULES_DB_PATH = os.path.join(os.path.dirname(__file__), "brp_modules_from_edb.json")
GPS_DIDS_MAPPING_PATH = os.path.join(os.path.dirname(__file__), "gps_dids_mapping.json")
BRP_DTC_BY_MODEL_PATH = os.path.join(os.path.dirname(__file__), "brp_dtc_by_model.json")


def _normalize_dtc_db(raw_db):
    normalized = {}
    for code, payload in raw_db.items():
        if isinstance(payload, dict):
            normalized[code] = {
                "desc": str(payload.get("desc", "Unknown Fault")),
                "sol": str(payload.get("sol", "")),
            }
        else:
            normalized[code] = {"desc": str(payload), "sol": ""}
    return normalized


def _load_dtc_json_file(path, label):
    if not os.path.exists(path):
        print(f"Warning: {label} DTC JSON not found: {path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except Exception as exc:
        print(f"Warning: Failed to load {label} DTC JSON: {exc}")
        return {}

    return _normalize_dtc_db(payload)


def load_dtc_databases():
    brp = _load_dtc_json_file(BRP_DTC_DB_PATH, "BRP")
    yamaha = _load_dtc_json_file(YAMAHA_DTC_DB_PATH, "Yamaha")
    return brp, yamaha


def load_yamaha_yds_db():
    """Dicionario YDS (363 parametros Yamaha) gerado por tools/extract_yds_db.py."""
    if not os.path.exists(YAMAHA_YDS_DB_PATH):
        print(f"Warning: Yamaha YDS items JSON not found: {YAMAHA_YDS_DB_PATH}")
        return {}
    try:
        with open(YAMAHA_YDS_DB_PATH, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except Exception as exc:
        print(f"Warning: Failed to load Yamaha YDS items JSON: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def lookup_dtc_entry(db, code):
    entry = db.get(code, {})
    if isinstance(entry, dict):
        return entry
    return {"desc": str(entry), "sol": ""}


def lookup_dtc_desc(db, code, fallback):
    return lookup_dtc_entry(db, code).get("desc", fallback)


# --- Codigos de falha Yamaha ------------------------------------------------
# A Yamaha nao usa codigos OBD-II. O YDS apresenta o DTC como numero decimal
# (01..99) e a tabela yamaha_dtc_codes.json usa esse formato. Modelos com
# CAN/OBD-II podem expor P/B/C/U de 5 caracteres, que sao aceitos em paralelo.

YAMAHA_DTC_MIN = 1
YAMAHA_DTC_MAX = 99


def normalize_yamaha_code(raw):
    """Normaliza um codigo Yamaha.

    :returns: (codigo, formato) onde formato e "yds", "obd" ou "raw".
              "yds" -> duas posicoes decimais (ex. "07");
              "obd" -> P/B/C/U de 5 caracteres (modelos com CAN).
    """
    code = str(raw if raw is not None else "").strip().upper()
    if not code:
        return "", "raw"
    if code.isdigit():
        value = int(code)
        if YAMAHA_DTC_MIN <= value <= YAMAHA_DTC_MAX:
            return "%02d" % value, "yds"
        return code, "raw"
    if len(code) == 5 and code[0] in "PCBU" and code[1:].isalnum():
        return code, "obd"
    return code, "raw"


def describe_yamaha_code(raw):
    """Descricao de um codigo Yamaha a partir da tabela YDS.

    :returns: {"desc", "sol", "source", "code"}
    """
    code, fmt = normalize_yamaha_code(raw)
    if fmt == "yds":
        entry = lookup_dtc_entry(YAMAHA_DTC_DB, code)
        if entry:
            return {"desc": entry.get("desc", ""),
                    "sol": entry.get("sol", ""),
                    "source": "yds", "code": code}
        return {"desc": "Codigo YDS sem descricao na base (consulte o manual de servico)",
                "sol": "", "source": "yds", "code": code}
    if fmt == "obd":
        entry = lookup_dtc_entry(YAMAHA_DTC_DB, code)
        return {"desc": f"[OBD] {entry.get('desc', 'codigo sem descricao na base')}",
                "sol": entry.get("sol", ""), "source": "obd", "code": code}
    return {"desc": "Codigo desconhecido", "sol": "", "source": "raw", "code": code}


def load_brp_dtc_by_model():
    """Base DTC com dimensao de modelo (gerada por tools/build_brp_dtc_by_model.py).

    Estrutura: {"models": {chave: {display, modules, dtcs: {codigo: {desc, ecu}}}}}.
    Devolve {} quando o ficheiro nao existe -- a app cai na base global.
    """
    if not os.path.exists(BRP_DTC_BY_MODEL_PATH):
        print(f"Warning: BRP DTC-by-model JSON not found: {BRP_DTC_BY_MODEL_PATH}")
        return {"models": {}}
    try:
        with open(BRP_DTC_BY_MODEL_PATH, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except Exception as exc:
        print(f"Warning: Failed to load BRP DTC-by-model JSON: {exc}")
        return {"models": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), dict):
        print(f"Warning: Unexpected BRP DTC-by-model JSON layout: {BRP_DTC_BY_MODEL_PATH}")
        return {"models": {}}
    return payload


def rank_brp_models(model_db, modules, codes=()):
    """Modelos candidatos ordenados por pontuacao: [(score, chave), ...]."""
    models = (model_db or {}).get("models") or {}
    modules = {m for m in (modules or ()) if m}
    codes = {c for c in (codes or ()) if c}
    if not models or not modules:
        return []

    scored = []
    for key, model in models.items():
        model_modules = set(model.get("modules") or ())
        if not model_modules:
            continue
        hit = len(modules & model_modules)
        coverage = hit / len(modules)          # quanto dos nossos ECUs o modelo tem
        if coverage < 0.5:
            continue
        precision = hit / len(model_modules)    # quanto do modelo ja vimos
        score = 0.6 * coverage + 0.4 * precision
        if codes:
            known = sum(1 for c in codes if c in (model.get("dtcs") or {}))
            score = 0.5 * score + 0.5 * (known / len(codes))
        scored.append((score, key))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored


def resolve_brp_model_by_vin(model_db, vin):
    """Identifica o modelo pelo VIN usando o prefixo mais longo que exista na base.

    :returns: (chave_do_modelo | None, prefixo_usado)
    """
    index = (model_db or {}).get("vin_index") or {}
    vin = (vin or "").strip().upper()
    if not index or len(vin) < 6:
        return None, ""
    for length in range(len(vin), 5, -1):
        keys = index.get(vin[:length])
        if keys:
            return keys[0], vin[:length]
    return None, ""


def resolve_brp_model(model_db, modules, codes=()):
    """Identifica o modelo a partir dos modulos que responderam e dos DTCs lidos.

    Muitos modelos partilham o mesmo conjunto de ECUs (ex.: Cluster+DPS+ECM), por
    isso a cobertura de modulos sozinha nao chega: a fracao de codigos conhecidos
    pelo modelo desempata.

    :returns: (chave_do_modelo | None, confianca 0..1, n_candidatos)
              n_candidatos > 1 significa empate -- nao se escolhe arbitrariamente.
    """
    ranked = rank_brp_models(model_db, modules, codes)
    if not ranked:
        return None, 0.0, 0
    best_score, best_key = ranked[0]
    contenders = sum(1 for score, _ in ranked if abs(score - best_score) <= 0.01)
    return best_key, best_score, contenders


def load_module_response_ids():
    fallback = [0x7E8, 0x7E9, 0x7BA, 0x7BD, 0x7AE, 0x7BB]
    if not os.path.exists(BRP_MODULES_DB_PATH):
        print(f"Warning: BRP modules JSON not found: {BRP_MODULES_DB_PATH}")
        return fallback

    try:
        with open(BRP_MODULES_DB_PATH, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
        entries = payload.get("modules_by_response_id", {})
        ids = []
        for key in entries.keys():
            if isinstance(key, str) and key.lower().startswith("0x"):
                ids.append(int(key, 16))
        return sorted(set(ids)) if ids else fallback
    except Exception as exc:
        print(f"Warning: Failed to load module response IDs: {exc}")
        return fallback


def load_module_map():
    """Returns (resp_id->name dict, list of (req_id, name) for polling)."""
    resp_map = {}   # {int_resp_id: "ECM", ...}
    poll_list = []  # [(int_req_id, "ECM"), ...]
    # Modules that support UDS DTC reading (skip config keys, GPS-only, etc.)
    SKIP_NAMES = {"CCK", "GPSCAN", "GPSCan", "RFComm", "GPS"}
    if not os.path.exists(BRP_MODULES_DB_PATH):
        return resp_map, poll_list
    try:
        with open(BRP_MODULES_DB_PATH, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
        entries = payload.get("modules_by_response_id", {})
        for resp_key, info in entries.items():
            resp_id = int(resp_key, 16)
            names = info.get("short_names", [])
            # Use the first short name as canonical
            name = names[0] if names else "?"
            # Skip non-diagnostic modules
            if any(s in name for s in SKIP_NAMES):
                continue
            resp_map[resp_id] = name
            for req_key in info.get("request_ids", []):
                req_id = int(req_key, 16)
                poll_list.append((req_id, name))
    except Exception as exc:
        print(f"Warning: load_module_map failed: {exc}")
    return resp_map, poll_list


BRP_DTC_DB, YAMAHA_DTC_DB = load_dtc_databases()
YAMAHA_YDS_DB = load_yamaha_yds_db()
KNOWN_MODULE_RESP_IDS = load_module_response_ids()
MODULE_RESP_NAME_MAP, MODULE_DTC_POLL_LIST = load_module_map()
BRP_DTC_BY_MODEL = load_brp_dtc_by_model()

class ThermometerGauge(tk.Canvas):
    def __init__(self, parent, width=120, height=250, min_val=0, max_val=120, unit="Â°C", title="", color="#00ff00"):
        super().__init__(parent, width=width, height=height, bg="#2b2b2b", highlightthickness=0)
        self.width = width
        self.height = height
        self.min_val = min_val
        self.max_val = max_val
        self.unit = unit
        self.title_text = title
        self.main_color = color
        self.current_val = min_val

        # Geometry
        self.bulb_radius = 25
        self.cx = width / 2
        self.cy_bulb = height - 40
        self.stem_width = 20
        self.top_y = 50
        self.bottom_y = self.cy_bulb - self.bulb_radius + 5
        
        self.draw_background()
        self.set_value(min_val)

    def draw_background(self):
        self.delete("bg")
        # Title
        self.create_text(self.cx, 20, text=self.title_text, fill="white", font=("Arial", 10, "bold"), tags="bg")
        
        # Stem Background
        self.create_rectangle(self.cx - self.stem_width/2, self.top_y, 
                              self.cx + self.stem_width/2, self.bottom_y, 
                              fill="#444", outline="#666", tags="bg")
        
        # Bulb Background
        self.create_oval(self.cx - self.bulb_radius, self.cy_bulb - self.bulb_radius, 
                         self.cx + self.bulb_radius, self.cy_bulb + self.bulb_radius, 
                         fill="#444", outline="#666", tags="bg")

        # Ticks
        steps = 5
        step_val = (self.max_val - self.min_val) / steps
        total_height = self.bottom_y - self.top_y
        
        for i in range(steps + 1):
            val = self.min_val + i * step_val
            pct = i / steps
            y = self.bottom_y - (pct * total_height)
            
            # Tick line
            self.create_line(self.cx - 15, y, self.cx - 25, y, fill="#aaa", width=1, tags="bg")
            self.create_text(self.cx - 35, y, text=f"{int(val)}", fill="#aaa", font=("Arial", 8), anchor="e", tags="bg")
            
            # High Marker
            if i == steps:
                self.create_text(self.cx + 25, y, text="HI", fill="red", font=("Arial", 8, "bold"), anchor="w", tags="bg")

    def set_value(self, val):
        self.current_val = val
        self.delete("liquid")
        self.delete("text")
        
        # Clip
        disp_val = max(self.min_val, min(val, self.max_val))
        
        pct = (disp_val - self.min_val) / (self.max_val - self.min_val)
        total_height = self.bottom_y - self.top_y
        fill_height = pct * total_height
        liquid_top = self.bottom_y - fill_height
        
        # Determine Color (Green -> normal, Red -> High)
        color = self.main_color
        if pct > 0.8: color = "#ff3333" # Red if high
        
        # Draw Liquid Stem
        self.create_rectangle(self.cx - self.stem_width/2 + 2, liquid_top, 
                              self.cx + self.stem_width/2 - 2, self.bottom_y + 5, 
                              fill=color, outline="", tags="liquid")
        
        # Draw Bulb Liquid
        self.create_oval(self.cx - self.bulb_radius + 2, self.cy_bulb - self.bulb_radius + 2, 
                         self.cx + self.bulb_radius - 2, self.cy_bulb + self.bulb_radius - 2, 
                         fill=color, outline="", tags="liquid")
        
        # Value Text inside Bulb
        self.create_text(self.cx, self.cy_bulb, text=f"{val:.1f}", fill="black", font=("Arial", 10, "bold"), tags="text")

class AnalogGauge(tk.Canvas):
    def __init__(self, parent, width=300, height=300, min_val=0, max_val=100, unit="", title="", color="#00aaff", zones=None, double_scale=False, outer_unit="", decimals=0):
        super().__init__(parent, width=width, height=height, bg="#2b2b2b", highlightthickness=0)
        self.width = width
        self.height = height
        self.cx = width / 2
        self.cy = height / 2
        self.radius = min(width, height) / 2 - 30
        
        self.min_val = min_val
        self.max_val = max_val
        self.unit = unit
        self.title_text = title
        self.main_color = color
        self.zones = zones # List of (start_val, end_val, color)
        self.double_scale = double_scale
        self.outer_unit = outer_unit
        self.decimals = decimals
        
        self.current_val = min_val
        self.min_registered = None
        self.max_registered = None
        
        # Angles: Start at 135 deg (SW), End at 45 deg (SE) -> Span 270 deg
        self.start_angle = 225
        self.extent = -270 # Clockwise
        
        self.draw_background()
        self.draw_needle()

    def val_to_angle(self, val):
        if val < self.min_val: val = self.min_val
        if val > self.max_val: val = self.max_val
        pct = (val - self.min_val) / (self.max_val - self.min_val)
        return self.start_angle + (pct * self.extent)

    def draw_background(self):
        self.delete("bg")
        
        # Draw Colored Zones Arcs
        if self.zones:
            for start_v, end_v, z_color in self.zones:
                angle_start = self.val_to_angle(start_v)
                angle_end = self.val_to_angle(end_v)
                # Tkinter arc start is CCW from East. Our angles are CCW from East (225 down to -45).
                # Extent is angle_end - angle_start.
                # Since extent is negative (-270), angle_end will be smaller than angle_start.
                
                # However, create_arc expects 'start' and 'extent'.
                # But if we want it to look contiguous, we must handle the arc drawing carefully.
                # Create arc draws CCW by default if extent is positive, CW if negative.
                # My self.extent is -270 (CW).
                
                z_extent = angle_end - angle_start
                self.create_arc(self.cx-self.radius, self.cy-self.radius, self.cx+self.radius, self.cy+self.radius,
                                start=angle_start, extent=z_extent, style="arc", outline=z_color, width=8, tags="bg")
        else:
             self.create_arc(self.cx-self.radius, self.cy-self.radius, self.cx+self.radius, self.cy+self.radius,
                        start=self.start_angle, extent=self.extent, style="arc", outline="#555", width=3, tags="bg")

        # Ticks (Inner - Primary Unit)
        steps = 10
        step_val = (self.max_val - self.min_val) / steps
        step_angle = self.extent / steps
        
        for i in range(steps + 1):
            val = self.min_val + i * step_val
            angle_deg = self.start_angle + i * step_angle
            angle_rad = math.radians(angle_deg)
            
            # Outer point (Inner Scale)
            r_out = self.radius - 5
            x_out = self.cx + r_out * math.cos(angle_rad)
            y_out = self.cy - r_out * math.sin(angle_rad) # Canvas Y inverted
            
            # Inner point
            r_in = self.radius - 15
            x_in = self.cx + r_in * math.cos(angle_rad)
            y_in = self.cy - r_in * math.sin(angle_rad)
            
            self.create_line(x_in, y_in, x_out, y_out, fill="white", width=2, tags="bg")
            
            # Text (Inner)
            r_text = self.radius - 30
            x_text = self.cx + r_text * math.cos(angle_rad)
            y_text = self.cy - r_text * math.sin(angle_rad)
            self.create_text(x_text, y_text, text=f"{int(val)}", fill="#aaa", font=("Arial", 8), tags="bg")

        # Ticks (Outer - Secondary Unit)
        if self.double_scale:
             # MAP Specific: Primary hPa (0-2000), Outer PSI (0-30 approx)
             # 1 hPa = 0.0145 PSI
             conv = 0.0145038
             max_psi = self.max_val * conv
             steps_psi = 6 # 0, 5, 10, 15, 20, 25, 30
             psi_step = 5
             
             count = int(max_psi / psi_step) + 1
             
             for i in range(count):
                 val_psi = i * psi_step
                 val_hpa = val_psi / conv
                 
                 angle_deg = self.val_to_angle(val_hpa)
                 angle_rad = math.radians(angle_deg)
                 
                 r_in = self.radius + 5
                 r_out = self.radius + 15
                 
                 x_in = self.cx + r_in * math.cos(angle_rad)
                 y_in = self.cy - r_in * math.sin(angle_rad)
                 x_out = self.cx + r_out * math.cos(angle_rad)
                 y_out = self.cy - r_out * math.sin(angle_rad)
                 
                 self.create_line(x_in, y_in, x_out, y_out, fill="cyan", width=2, tags="bg")
                 
                 r_text = self.radius + 25
                 x_text = self.cx + r_text * math.cos(angle_rad)
                 y_text = self.cy - r_text * math.sin(angle_rad)
                 
                 self.create_text(x_text, y_text, text=f"{int(val_psi)}", fill="cyan", font=("Arial", 8), tags="bg")
             
             # Outer Unit Label
             self.create_text(self.cx, self.cy - 50, text=self.outer_unit, fill="cyan", font=("Arial", 9, "bold"), tags="bg")

        # Title/Unit - Moved lower into the open gap
        self.create_text(self.cx, self.cy + 65, text=self.title_text, fill="white", font=("Arial", 12, "bold"), tags="bg")
        self.create_text(self.cx, self.cy + 85, text=self.unit, fill="#aaa", font=("Arial", 10), tags="bg")

        # Config Digital Readout (Lowered)
        self.value_text_id = self.create_text(self.cx, self.cy + 35, text=f"{self.min_val:.{self.decimals}f}", fill=self.main_color, font=("Arial", 20, "bold"), tags="bg")

    def val_to_angle(self, val):
        # Clip
        if val < self.min_val: val = self.min_val
        if val > self.max_val: val = self.max_val
        
        pct = (val - self.min_val) / (self.max_val - self.min_val)
        return self.start_angle + (pct * self.extent)

    def draw_needle(self):
        self.delete("needle")
        
        angle_deg = self.val_to_angle(self.current_val)
        angle_rad = math.radians(angle_deg)
        
        r_needle = self.radius - 10
        x_tip = self.cx + r_needle * math.cos(angle_rad)
        y_tip = self.cy - r_needle * math.sin(angle_rad)
        
        self.create_line(self.cx, self.cy, x_tip, y_tip, fill=self.main_color, width=4, smooth=True, tags="needle")
        self.create_oval(self.cx-5, self.cy-5, self.cx+5, self.cy+5, fill=self.main_color, outline="", tags="needle")
        
        # Digital Update
        self.itemconfigure(self.value_text_id, text=f"{self.current_val:.{self.decimals}f}")

        # Max/Min Markers
        if self.max_registered is not None:
             a_max = math.radians(self.val_to_angle(self.max_registered))
             xm = self.cx + self.radius * math.cos(a_max)
             ym = self.cy - self.radius * math.sin(a_max)
             self.create_line(self.cx, self.cy, xm, ym, fill="#ff0000", width=1, dash=(4,2), tags="needle")
        
        if self.min_registered is not None:
             a_min = math.radians(self.val_to_angle(self.min_registered))
             xm = self.cx + self.radius * math.cos(a_min)
             ym = self.cy - self.radius * math.sin(a_min)
             self.create_line(self.cx, self.cy, xm, ym, fill="#00ff00", width=1, dash=(4,2), tags="needle")

    def set_value(self, val):
        if val is None: val = 0 # Safety
        self.current_val = float(val)
        
        # DEBUG: Print only for Gate Gauge if possible, or transiently
        # print(f"AnalogGauge SetValue: {self.current_val} (Title: {self.title_text})")
        
        if self.min_registered is None or self.current_val < self.min_registered:
            self.min_registered = self.current_val
        if self.max_registered is None or self.current_val > self.max_registered:
            self.max_registered = self.current_val
            
        self.draw_needle()
    
    def reset_stats(self):
        self.min_registered = None
        self.max_registered = None
        self.draw_needle()

class VerticalBarWithMarker(tk.Canvas):
    def __init__(self, master, width=25, height=200, bg_color="#333333", fill_color="#ff00aa", marker_color="orange", **kwargs):
        super().__init__(master, width=width, height=height, bg=bg_color, highlightthickness=0, **kwargs)
        self.w = width
        self.h = height
        self.fill_color = fill_color
        self.marker_color = marker_color
        
        # Border
        # self.create_rectangle(0, 0, width-1, height-1, outline="#555")
        
        # Fill (Progress)
        self.fill_id = self.create_rectangle(0, self.h, self.w, self.h, fill=self.fill_color, width=0)
        
        # Marker (Oval dot)
        self.marker_id = self.create_oval(-5, self.h+5, -5, self.h+5, fill=self.marker_color, outline="white", width=1)
        
    def set_value(self, val_pct):
        # 0-100
        pct = max(0, min(100, val_pct)) / 100.0
        y_top = self.h * (1 - pct)
        self.coords(self.fill_id, 0, y_top, self.w, self.h)
        
    def set_marker(self, val_pct):
        # 0-100
        pct = max(0, min(100, val_pct)) / 100.0
        y_center = self.h * (1 - pct)
        r = 6
        # Draw a circle on top
        self.coords(self.marker_id, 2, y_center-r, self.w-2, y_center+r)
        self.tag_raise(self.marker_id) # Ensure on top

class ECMDiagnosticApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Configuration
        self.title("ECM Diagnostic Tool - ESP32 CAN")
        # Fit within a 1366x768 notebook screen (leave room for taskbar ~40px + title bar ~30px)
        self.geometry("1366x695")
        self.maxsize(1366, 700)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.ser = None
        self.tcp_socket = None
        self.can_bus = None
        self.avr_transport = None
        self._kline_session_lock = threading.Lock()  # prevents concurrent K-Line init threads
        self._kline_active = False       # True while a K-Line session is alive (drives keepalive)
        self._yds_link = None            # YdsByteLink when a YDS session is open
        self._yamaha_session = None      # YdsSession result of the last handshake
        self._last_can_status_time = 0.0     # monotonic timestamp of last CAN_GET_STATUS log
        self._kline_proto = None         # "yamaha" or "kawasaki" â€” used to pick correct ECU address
        self._kline_sniff_active = False  # True in passive bus-sniff mode (no TX, no wakeup)
        self._kline_sniff_stop = threading.Event()  # set to stop sniff thread
        self._kline_keepalive_dead = threading.Event()  # set when keepalive thread has fully exited
        self._kline_keepalive_dead.set()  # initially set (no thread running)
        self.is_connected = False
        self.is_replaying = False
        self.is_paused = False # Pause Flag
        self.current_replay_progress = 0.0
        self.current_replay_time_str = "--:--"
        self._avr_kline_buf = []  # raw K-Line byte accumulation buffer
        self.seek_request = None # Stores float 0-1 if user seeks
        self.read_thread = None
        self.stop_thread = False
        self.connection_mode = "Serial" # Serial or TCP or IXXAT or KVASER or AVR
        self.tcp_buffer = ""
        self.is_detecting_speed = False
        
        # CAN Data Storage
        # Format: {id_int: {"cnt": int, "dlc": int, "data": [bytes], "ts": float, "dt": float}}
        self.can_data = {}
        self.nodes_pos = {} # For Graph: {id_int: (x, y)}
        self.last_ui_update = 0
        
        # Recording & Plotting
        self.is_recording = False
        self.log_file = None
        self.log_writer = None
        self.current_log_filename = None
        self.selected_graph_id = None
        self.selected_graph_source = "can"
        self.graph_data_points = deque(maxlen=2000) # Store (ts, [byte0, byte1...]) - Increased history
        self.yamaha_graph_points = {}
        self.yamaha_seen_signals = {}
        self.yamaha_signal_buttons = {}
        self.current_signal_source = None
        self._yamaha_selector_signature = None
        self.raw_log_buffer = deque(maxlen=100) # For UI buffer
        
        # ISO-TP Buffer
        self.isotp_rx_buffer = []  # Bytes
        self.isotp_rx_len = 0
        self.isotp_active = False
        
        # Protocol Auto-Detection
        self.active_protocol = "AUTO" # "AUTO", "UDS", "KWP"
        self.detecting_protocol = False

        # OBD-II PIDs Definitions (Mode 01)
        self.obd_pids = {
            0x04: ("Calc Engine Load", lambda a,b,c,d: f"{a/2.55:.1f} %"),
            0x05: ("Engine Coolant Temp", lambda a,b,c,d: f"{a-40} Â°C"),
            0x0C: ("Engine RPM", lambda a,b,c,d: f"{(256*a+b)/4:.0f} rpm"),
            0x0D: ("Vehicle Speed", lambda a,b,c,d: f"{a} km/h"),
            0x0F: ("Intake Air Temp", lambda a,b,c,d: f"{a-40} Â°C"),
            0x10: ("MAF Air Flow", lambda a,b,c,d: f"{(256*a+b)/100:.2f} g/s"),
            0x11: ("Throttle Position", lambda a,b,c,d: f"{a/2.55:.1f} %"),
            0x33: ("Barometric Pressure", lambda a,b,c,d: f"{a} kPa"),
            0x42: ("Control Module Voltage", lambda a,b,c,d: f"{(256*a+b)/1000:.2f} V"),
            0x46: ("Ambient Air Temp", lambda a,b,c,d: f"{a-40} Â°C"),
        }

        # Grid Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar Frame (Left) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="ECM SCANNER", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(8, 4))

        # Connection Mode Selection
        self.mode_label = ctk.CTkLabel(self.sidebar_frame, text="Connection Mode:", anchor="w")
        self.mode_label.grid(row=1, column=0, padx=20, pady=(4, 0))
        
        self.mode_option = ctk.CTkSegmentedButton(self.sidebar_frame, values=["Serial", "TCP", "IXXAT", "KVASER", "AVR"], command=self.change_mode)
        self.mode_option.set("Serial")
        self.mode_option.grid(row=2, column=0, padx=20, pady=(3, 6))

        # --- Serial Widgets ---
        self.serial_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.serial_frame.grid(row=3, column=0, sticky="ew")
        
        self.port_label = ctk.CTkLabel(self.serial_frame, text="Select COM Port:", anchor="w")
        self.port_label.pack(padx=20, pady=(5, 0), anchor="w")
        
        self.port_option = ctk.CTkOptionMenu(self.serial_frame, values=self.get_serial_ports())
        self.port_option.pack(padx=20, pady=(5, 10), fill="x")
        
        self.refresh_btn = ctk.CTkButton(self.serial_frame, text="Refresh Ports", command=self.refresh_ports)
        self.refresh_btn.pack(padx=20, pady=5, fill="x")

        # --- AVR Sub-options (packed inside serial_frame, only visible in AVR mode) ---
        self.avr_sub_frame = ctk.CTkFrame(self.serial_frame, fg_color="transparent")
        # Not packed yet; shown/hidden by change_mode()

        avr_bus_label = ctk.CTkLabel(self.avr_sub_frame, text="AVR Bus:", anchor="w")
        avr_bus_label.pack(padx=20, pady=(8, 0), anchor="w")

        self.avr_bus_var = ctk.StringVar(value="CAN")
        self.avr_bus_seg = ctk.CTkSegmentedButton(
            self.avr_sub_frame,
            values=["K-Line", "CAN"],
            variable=self.avr_bus_var,
            command=self._on_avr_bus_change,
        )
        self.avr_bus_seg.pack(padx=20, pady=(2, 6), fill="x")

        # --- K-Line sub-options (speed + protocol combined) ---
        self.avr_kline_frame = ctk.CTkFrame(self.avr_sub_frame, fg_color="transparent")

        kl_combo_label = ctk.CTkLabel(self.avr_kline_frame, text="K-Line / Protocol:", anchor="w")
        kl_combo_label.pack(padx=20, pady=(0, 0), anchor="w")
        # O YDS original usa 9600 8N1 (unica constante de baud em todo o
        # YDS.exe); 10400 e 15625 ficam como opcoes para outros equipamentos.
        self._avr_kline_combo_var = ctk.StringVar(value="9600 - Yamaha")
        self.avr_kline_combo_opt = ctk.CTkOptionMenu(
            self.avr_kline_frame,
            variable=self._avr_kline_combo_var,
            values=[
                "9600 - Yamaha",
                "9600 - Kawasaki",
                "10400 - Yamaha",
                "15625 - Yamaha",
                "16040 - Yamaha",
                "10400 - Kawasaki",
            ],
        )
        self.avr_kline_combo_opt.pack(padx=20, pady=(2, 6), fill="x")

        # Ligacao Yamaha no estilo YDS: 300 baud + 0x1C, depois 9600 e o
        # handshake FD E5 E5 FE FF FE FF (ver docs/YDS_Protocol_Decompiled.md).
        self.yamaha_yds_link_var = ctk.BooleanVar(value=True)
        self.yamaha_yds_checkbox = ctk.CTkCheckBox(
            self.avr_kline_frame,
            text="Yamaha YDS link (9600, wake 0x1C, handshake)",
            variable=self.yamaha_yds_link_var,
            font=("Arial", 11),
        )
        self.yamaha_yds_checkbox.pack(padx=20, pady=(0, 6), anchor="w")

        # Compatibility shims so existing code using .get() keeps working
        class _KLineComboProxy:
            def __init__(self, combo_var, field):
                self._v = combo_var
                self._field = field  # "baud" or "proto"
            def get(self):
                parts = self._v.get().split(" - ", 1)
                return parts[0] if self._field == "baud" else (parts[1] if len(parts) > 1 else "Yamaha")

        self.avr_kline_baud_var = _KLineComboProxy(self._avr_kline_combo_var, "baud")
        self.avr_kline_proto_var = _KLineComboProxy(self._avr_kline_combo_var, "proto")

        # --- CAN sub-options ---
        self.avr_can_frame = ctk.CTkFrame(self.avr_sub_frame, fg_color="transparent")

        can_spd_label = ctk.CTkLabel(self.avr_can_frame, text="CAN Speed (kbps):", anchor="w")
        can_spd_label.pack(padx=20, pady=(0, 0), anchor="w")
        self.avr_can_kbps_var = ctk.StringVar(value="500")
        self.avr_can_kbps_opt = ctk.CTkOptionMenu(
            self.avr_can_frame,
            variable=self.avr_can_kbps_var,
            values=["Auto", "1000", "500", "250", "125"],
            command=self._on_avr_can_speed_change,
        )
        self.avr_can_kbps_opt.pack(padx=20, pady=(2, 6), fill="x")

        # Show CAN sub-options by default (matches initial avr_bus_var="CAN")
        self.avr_can_frame.pack(fill="x")

        # --- TCP Widgets ---
        self.tcp_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        # Initially hidden
        # self.tcp_frame.grid(row=3, column=0, sticky="ew") 

        self.ip_label = ctk.CTkLabel(self.tcp_frame, text="IP Address:", anchor="w")
        self.ip_label.pack(padx=20, pady=(0, 0), anchor="w")
        
        self.ip_entry = ctk.CTkEntry(self.tcp_frame, placeholder_text="192.168.4.1")
        self.ip_entry.insert(0, "192.168.4.1")
        self.ip_entry.pack(padx=20, pady=(0, 10), fill="x")

        self.tcp_port_label = ctk.CTkLabel(self.tcp_frame, text="Port:", anchor="w")
        self.tcp_port_label.pack(padx=20, pady=(0, 0), anchor="w")
        
        self.tcp_port_entry = ctk.CTkEntry(self.tcp_frame, placeholder_text="80")
        self.tcp_port_entry.insert(0, "8080")
        self.tcp_port_entry.pack(padx=20, pady=(0, 10), fill="x")

        # --- IXXAT Widgets ---
        self.ixxat_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")

        self.ixxat_channel_label = ctk.CTkLabel(self.ixxat_frame, text="IXXAT Channel:", anchor="w")
        self.ixxat_channel_label.pack(padx=20, pady=(0, 0), anchor="w")

        self.ixxat_channel_entry = ctk.CTkEntry(self.ixxat_frame, placeholder_text="0")
        self.ixxat_channel_entry.insert(0, "0")
        self.ixxat_channel_entry.pack(padx=20, pady=(0, 10), fill="x")

        self.ixxat_autospeed_btn = ctk.CTkButton(
            self.ixxat_frame,
            text="Auto Detect Speed",
            command=self.auto_detect_ixxat_speed,
        )
        self.ixxat_autospeed_btn.pack(padx=20, pady=(0, 10), fill="x")

        # --- KVASER Widgets ---
        self.kvaser_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")

        self.kvaser_channel_label = ctk.CTkLabel(self.kvaser_frame, text="KVASER Channel:", anchor="w")
        self.kvaser_channel_label.pack(padx=20, pady=(0, 0), anchor="w")

        self.kvaser_channel_entry = ctk.CTkEntry(self.kvaser_frame, placeholder_text="0")
        self.kvaser_channel_entry.insert(0, "0")
        self.kvaser_channel_entry.pack(padx=20, pady=(0, 10), fill="x")

        self.kvaser_autospeed_btn = ctk.CTkButton(
            self.kvaser_frame,
            text="Auto Detect Speed",
            command=self.auto_detect_kvaser_speed,
        )
        self.kvaser_autospeed_btn.pack(padx=20, pady=(0, 10), fill="x")

        # Baud Rate Selection
        self.baud_label = ctk.CTkLabel(self.sidebar_frame, text="CAN Bitrate (kbps):", anchor="w")
        self.baud_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.kbps_var = ctk.StringVar(value="500")
        self.kbps_option = ctk.CTkOptionMenu(self.sidebar_frame, variable=self.kbps_var, 
                                           values=["1000", "500", "250", "125", "100", "50", "20", "10"],
                                           command=self.set_can_speed)
        self.kbps_option.grid(row=5, column=0, padx=20, pady=(5, 10), sticky="ew")

        # ECU Init Buttons (BRP, Yamaha, Kawasaki)
        self.brp_label = ctk.CTkLabel(self.sidebar_frame, text="ECU Wake-Up/Init:", anchor="w")
        self.brp_label.grid(row=8, column=0, padx=20, pady=(4, 0), sticky="w")
        
        # Grid frame for 2x2 buttons
        self.brp_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.brp_frame.grid(row=9, column=0, sticky="ew", padx=10)
        self.brp_frame.columnconfigure(0, weight=1)
        self.brp_frame.columnconfigure(1, weight=1)
        
        # Row 0: BRP (Siemens / Bosch)
        self.siemens_btn = ctk.CTkButton(self.brp_frame, text="BRP\nSiemens", height=35, font=("Arial", 11),
                                        command=lambda: self.send_brp_init("Siemens"))
        self.siemens_btn.grid(row=0, column=0, padx=3, pady=3)

        self.bosch_btn = ctk.CTkButton(self.brp_frame, text="BRP\nBosch", height=35, font=("Arial", 11),
                                      command=lambda: self.send_brp_init("Bosch"))
        self.bosch_btn.grid(row=0, column=1, padx=3, pady=3)

        # Row 1: Yamaha / Kawasaki
        self.yamaha_btn = ctk.CTkButton(self.brp_frame, text="Yamaha\nAuto Init", height=35, font=("Arial", 11),
                                        command=self.send_yamaha_init)
        self.yamaha_btn.grid(row=1, column=0, padx=3, pady=3)

        self.kawasaki_btn = ctk.CTkButton(self.brp_frame, text="Kawasaki\nInit", height=35, font=("Arial", 11),
                                          command=self.send_kawasaki_init)
        self.kawasaki_btn.grid(row=1, column=1, padx=3, pady=3)

        # Row 2: Passive bus sniff (spans both columns)
        self.kline_sniff_btn = ctk.CTkButton(
            self.brp_frame, text="K-Line Sniff (passivo)", height=30,
            font=("Arial", 11), fg_color="#1a4a6e",
            command=self._kline_sniff_start,
        )
        self.kline_sniff_btn.grid(row=2, column=0, columnspan=2, padx=3, pady=(3, 0), sticky="ew")
        
        self.kwp_keep_alive_var = ctk.BooleanVar(value=True)
        self.keep_alive_chb = ctk.CTkCheckBox(self.sidebar_frame, text="Keep-Alive (1.5s)", variable=self.kwp_keep_alive_var, command=self.toggle_keep_alive)
        self.keep_alive_chb.grid(row=10, column=0, padx=20, pady=4, sticky="w")

        self.connect_btn = ctk.CTkButton(self.sidebar_frame, text="CONNECT", fg_color="green", font=ctk.CTkFont(weight="bold"), command=self.toggle_connection)
        self.connect_btn.grid(row=11, column=0, padx=20, pady=(8, 4))

        self.record_btn = ctk.CTkButton(self.sidebar_frame, text="START REC", fg_color="#444444", font=ctk.CTkFont(weight="bold"), command=self.toggle_recording)
        self.record_btn.grid(row=12, column=0, padx=20, pady=(0, 4))

        self.replay_btn = ctk.CTkButton(self.sidebar_frame, text="REPLAY LOG", fg_color="#222222", font=ctk.CTkFont(weight="bold"), command=self.toggle_replay)
        self.replay_btn.grid(row=13, column=0, padx=20, pady=(0, 4))

        # Replay Progress (Slider)
        self.replay_slider = ctk.CTkSlider(self.sidebar_frame, width=160, height=16, from_=0, to=1, command=self.on_replay_seek)
        self.replay_slider.grid(row=14, column=0, padx=20, pady=(0, 5))
        self.replay_slider.set(0)
        
        self.replay_label = ctk.CTkLabel(self.sidebar_frame, text="--:-- / --:--", font=("Arial", 10))
        self.replay_label.grid(row=15, column=0, padx=20, pady=(0, 4))
        
        # Pause/Resume Button
        self.pause_btn = ctk.CTkButton(self.sidebar_frame, text="PAUSE", fg_color="#444444", state="disabled", width=80, command=self.toggle_pause)
        self.pause_btn.grid(row=16, column=0, padx=20, pady=(0, 4))

        # Loop Replay Checkbox
        self.loop_replay = ctk.BooleanVar(value=False)
        self.loop_check = ctk.CTkCheckBox(self.sidebar_frame, text="Loop Replay", variable=self.loop_replay, font=("Arial", 10))
        self.loop_check.grid(row=17, column=0, padx=20, pady=(0, 8))



        # Status Label & Protocol
        self.conn_status_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.conn_status_frame.grid(row=7, column=0, padx=20, pady=4)
        
        self.status_label = ctk.CTkLabel(self.conn_status_frame, text="Status: Disconnected", text_color="gray")
        self.status_label.pack()
        

        # --- Main Frame (Right) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Tab View
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=0, column=0, padx=4, pady=2, sticky="nsew")
        self.tabview.add("Diagnostico BRP") # Tab 0
        self.tabview.add("Diagnostico Yamaha") # Tab Yamaha
        self.tabview.add("Monitor Trafego") # Tab 1
        self.tabview.add("Grafo Rede")      # Tab 2
        self.tabview.add("Grafo Sinais")    # Tab 3
        self.tabview.add("Log Bruto")       # Tab 4
        
        # --- TAB 0: BRP Diagnostics ---
        self.brp_tab = self.tabview.tab("Diagnostico BRP")
        
        # Create Sub-Tabs (ECM, IBR, IS, CLUSTER)
        self.brp_subtabs = ctk.CTkTabview(self.brp_tab)
        self.brp_subtabs.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.ecm_tab = self.brp_subtabs.add("ECM")
        self.ibr_tab = self.brp_subtabs.add("IBR-MON")
        self.ibr_module_tab = self.brp_subtabs.add("IBR-MODULE")
        self.gps_tab = self.brp_subtabs.add("GPS")
        self.is_tab = self.brp_subtabs.add("IS")
        self.cluster_tab = self.brp_subtabs.add("PAINEL")
        self.dtc_tab = self.brp_subtabs.add("DTC")
        
        # --- GPS Tab Setup ---
        self.gps_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.gps_tab, text="Modulo GPS (0x7AE)", font=("Arial", 16, "bold")).pack(pady=10)
        
        self.gps_info_frame = ctk.CTkFrame(self.gps_tab)
        self.gps_info_frame.pack(fill="x", padx=20, pady=10)
        
        self.gps_labels = {}
        
        # Left column: Hardware ID
        gps_grid_left = ctk.CTkFrame(self.gps_info_frame, fg_color="transparent")
        gps_grid_left.pack(side="left", padx=10)
        
        ctk.CTkLabel(gps_grid_left, text="Hardware Info", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        for i, (key, label) in enumerate([("part", "Part #: --"), ("cal", "Calib #: --"), ("hw", "HW #: --"), ("ser", "Serial #: --")], 1):
            lbl = ctk.CTkLabel(gps_grid_left, text=label, font=("Arial", 11))
            lbl.grid(row=i, column=0, sticky="w", pady=2)
            self.gps_labels[key] = lbl

        # Middle column: Position Data
        gps_grid_mid = ctk.CTkFrame(self.gps_info_frame, fg_color="transparent")
        gps_grid_mid.pack(side="left", padx=20)
        
        ctk.CTkLabel(gps_grid_mid, text="Posicao", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        for i, (key, label) in enumerate([
            ("lat", "Latitude: --"),
            ("lon", "Longitude: --"),
            ("alt", "Altitude: --"),
            ("hdop", "H.DOP: --")
        ], 1):
            lbl = ctk.CTkLabel(gps_grid_mid, text=label, font=("Arial", 11))
            lbl.grid(row=i, column=0, sticky="w", pady=2)
            self.gps_labels[key] = lbl

        # Right column: Motion Data
        gps_grid_right = ctk.CTkFrame(self.gps_info_frame, fg_color="transparent")
        gps_grid_right.pack(side="left", padx=20)
        
        ctk.CTkLabel(gps_grid_right, text="Movimento", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        for i, (key, label) in enumerate([
            ("speed", "Velocidade: --"),
            ("course", "Direcao: --"),
            ("sats", "Satelites: --"),
            ("fix", "Fix Status: --")
        ], 1):
            lbl = ctk.CTkLabel(gps_grid_right, text=label, font=("Arial", 11))
            lbl.grid(row=i, column=0, sticky="w", pady=2)
            self.gps_labels[key] = lbl

        # Buttons
        btn_frame = ctk.CTkFrame(self.gps_info_frame, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="Ler ID", width=90, command=self.read_gps_info).pack(side="top", pady=2)
        ctk.CTkButton(btn_frame, text="Ler Posicao", width=90, command=self.read_gps_position).pack(side="top", pady=2)
        ctk.CTkButton(btn_frame, text="Ler Tudo", width=90, command=self.read_gps_all).pack(side="top", pady=2)
        
        # --- Sub-Tab: ECM Content ---
        # Configure Grid: 2 Rows (Gauges) + Extras
        # Columns: 4 cols for Top Row (RPM, T_Intake, T_Eng, T_Exh)
        for i in range(4):
            self.ecm_tab.grid_columnconfigure(i, weight=1)
        
        # --- TOP ROW: Temp & RPM ---
        # Col 0: RPM
        self.rpm_frame = ctk.CTkFrame(self.ecm_tab, fg_color="transparent")
        self.rpm_frame.grid(row=1, column=0, padx=5, pady=2)
        
        # RPM Zones: Green (0-7500), Yellow (7500-8000), Red (8000-10000)
        rpm_zones = [(0, 7500, "#00cc00"), (7500, 8000, "#ffff00"), (8000, 10000, "#ff0000")]
        self.rpm_gauge = AnalogGauge(self.rpm_frame, width=185, height=185, min_val=0, max_val=10000, 
                                     title="RPM", unit="r/min", color="#ffffff", zones=rpm_zones)
        self.rpm_gauge.pack()

        # Col 1: Intake Temp (Thermometer)
        self.temp_intake_frame = ctk.CTkFrame(self.ecm_tab, fg_color="transparent")
        self.temp_intake_frame.grid(row=1, column=1, padx=5, pady=2)
        self.temp_intake_gauge = ThermometerGauge(self.temp_intake_frame, width=100, height=185, min_val=-20, max_val=110, title="T. Admissao", unit="Â°C", color="#33cc33")
        self.temp_intake_gauge.pack()

        # Col 2: Engine Temp (Thermometer)
        self.temp_eng_frame = ctk.CTkFrame(self.ecm_tab, fg_color="transparent")
        self.temp_eng_frame.grid(row=1, column=2, padx=5, pady=2)
        self.temp_eng_gauge = ThermometerGauge(self.temp_eng_frame, width=100, height=185, min_val=-20, max_val=130, title="T. Motor", unit="Â°C", color="#33cc33")
        self.temp_eng_gauge.pack()

        # Col 3: Exhaust Temp (Thermometer)
        self.temp_exh_frame = ctk.CTkFrame(self.ecm_tab, fg_color="transparent")
        self.temp_exh_frame.grid(row=1, column=3, padx=5, pady=2)
        self.temp_exh_gauge = ThermometerGauge(self.temp_exh_frame, width=100, height=185, min_val=0, max_val=255, title="T. Escape", unit="raw", color="#33cc33")
        self.temp_exh_gauge.pack()

        # --- BOTTOM ROW: TPS, Battery, MAP ---
        # Col 0: IBR Bar | TPS (Analog) | APS Bar
        self.tps_frame = ctk.CTkFrame(self.ecm_tab, fg_color="transparent")
        self.tps_frame.grid(row=2, column=0, padx=5, pady=2)

        # 1. IBR Lever (Left)
        self.ibr_frame = ctk.CTkFrame(self.tps_frame, fg_color="transparent")
        self.ibr_frame.pack(side="left", padx=0)
        
        # Vertical Bar: Fill = Trigger, Marker = Gate Position
        self.ibr_lever_bar = VerticalBarWithMarker(self.ibr_frame, width=25, height=160, bg_color="#222", fill_color="#ff00aa", marker_color="orange")
        self.ibr_lever_bar.pack(pady=(15, 5))
        self.ibr_lever_label = ctk.CTkLabel(self.ibr_frame, text="IBR\n0%", font=("Arial", 10, "bold"), text_color="#ff00aa")
        self.ibr_lever_label.pack()

        # 2. TPS Gauge (Center)
        self.tps_gauge = AnalogGauge(self.tps_frame, width=170, height=170, min_val=0, max_val=100, title="Acel.(TPS)", unit="%", color="#ff5500")
        self.tps_gauge.pack(side="left")

        # 3. APS Bar (Right)
        self.aps_frame = ctk.CTkFrame(self.tps_frame, fg_color="transparent")
        self.aps_frame.pack(side="left", padx=0)
        
        self.aps_bar = VerticalBarWithMarker(self.aps_frame, width=25, height=160, bg_color="#222", fill_color="#00ffff", marker_color="white")
        self.aps_bar.pack(pady=(15, 5))
        self.aps_label = ctk.CTkLabel(self.aps_frame, text="APS\n0%", font=("Arial", 10, "bold"), text_color="#00ffff")
        self.aps_label.pack()

        # Col 1-2: Battery (Analog - Center)
        self.battery_frame = ctk.CTkFrame(self.ecm_tab, fg_color="transparent")
        self.battery_frame.grid(row=2, column=1, columnspan=2, padx=5, pady=2)
        
        # Battery Zones: Red (8-10), Green (10-15), Red (15-16)
        bat_zones = [(8, 10, "#ff0000"), (10, 15, "#00cc00"), (15, 16, "#ff0000")]
        self.battery_gauge = AnalogGauge(self.battery_frame, width=170, height=170, min_val=8, max_val=16, 
                                         title="Bateria", unit="V", color="#ffffff", zones=bat_zones, decimals=1)
        self.battery_gauge.pack()

        # Col 3: MAP (Analog)
        self.map_frame = ctk.CTkFrame(self.ecm_tab, fg_color="transparent")
        self.map_frame.grid(row=2, column=3, padx=5, pady=2)
        
        self.map_gauge = AnalogGauge(self.map_frame, width=170, height=170, min_val=0, max_val=2500, 
                                     title="MAP", unit="hPa", color="#ffffff", double_scale=True, outer_unit="PSI")
        self.map_gauge.pack()

        # --- TOP INFO BAR (row 0) â€” aproveita espaÃ§o acima dos gauges ---
        self.info_frame = ctk.CTkFrame(self.ecm_tab, fg_color="#1e1e1e", corner_radius=6)
        self.info_frame.grid(row=0, column=0, columnspan=4, sticky="ew", padx=5, pady=(2, 0))
        
        self.status_bar_lbl = ctk.CTkLabel(self.info_frame, text="Status: Aguardando...", font=("Arial", 11))
        self.status_bar_lbl.pack(side="left", padx=10)
        
        self.vin_label = ctk.CTkLabel(self.info_frame, text="VIN/Modelo: Procurando...", font=("Arial", 11), text_color="gray")
        self.vin_label.pack(side="left", padx=10)
        
        self.debug_110_lbl = ctk.CTkLabel(self.info_frame, text="ID 110: --", font=("Consolas", 10), text_color="gray")
        self.debug_110_lbl.pack(side="left", padx=10)
        
        ctk.CTkButton(self.info_frame, text="Ler Info ECU", width=100, height=24, font=("Arial", 11),
                      command=lambda: self.read_module_info(0x7E0)).pack(side="right", padx=10, pady=3)

        # --- ECM Actuators compact bar (row 3) ---
        self.ecm_act_frame = ctk.CTkFrame(self.ecm_tab, fg_color="#1e1e1e", corner_radius=6)
        self.ecm_act_frame.grid(row=3, column=0, columnspan=4, sticky="ew", padx=5, pady=(0, 2))
        
        ctk.CTkLabel(self.ecm_act_frame, text="Atuadores:", font=("Arial", 11, "bold"), text_color="orange").pack(side="left", padx=6)
        ctk.CTkButton(self.ecm_act_frame, text="Bico 1", width=72, height=26, command=lambda: self.send_ecm_actuation(0x50, 0x02)).pack(side="left", padx=2, pady=3)
        ctk.CTkButton(self.ecm_act_frame, text="Bico 2", width=72, height=26, command=lambda: self.send_ecm_actuation(0x50, 0x04)).pack(side="left", padx=2, pady=3)
        ctk.CTkButton(self.ecm_act_frame, text="Bico 3", width=72, height=26, command=lambda: self.send_ecm_actuation(0x50, 0x20)).pack(side="left", padx=2, pady=3)
        ctk.CTkButton(self.ecm_act_frame, text="Bobina 1", width=72, height=26, command=lambda: self.send_ecm_actuation(0x40, 0x02)).pack(side="left", padx=2, pady=3)
        ctk.CTkButton(self.ecm_act_frame, text="Bomba", width=72, height=26, command=lambda: self.send_ecm_actuation(0x50, 0x01)).pack(side="left", padx=2, pady=3)
        ctk.CTkLabel(self.ecm_act_frame, text="Manual:", font=("Arial", 10)).pack(side="left", padx=(10, 2))
        self.entry_act_id = ctk.CTkEntry(self.ecm_act_frame, width=45, height=26, placeholder_text="ID")
        self.entry_act_id.pack(side="left", padx=2, pady=3)
        self.entry_act_mask = ctk.CTkEntry(self.ecm_act_frame, width=45, height=26, placeholder_text="Mask")
        self.entry_act_mask.pack(side="left", padx=2, pady=3)
        ctk.CTkButton(self.ecm_act_frame, text="Enviar", width=65, height=26, fg_color="green",
                      command=lambda: self.send_ecm_actuation(int(self.entry_act_id.get(), 16), int(self.entry_act_mask.get(), 16))).pack(side="left", padx=2, pady=3)

        # --- IBR-MON Tab Setup (Monitor/Controls) ---
        self.ibr_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.ibr_tab, text="Monitoramento IBR (Gate/Alavanca)", font=("Arial", 16, "bold")).pack(pady=10)
        
        # IBR Controls (Moved from old IBR layout to IBR-MON)
        self.ibr_ctrl_frame = ctk.CTkFrame(self.ibr_tab)
        self.ibr_ctrl_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(self.ibr_ctrl_frame, text="Controle Manual Monitor (7BD)").pack(pady=5)
        
        # Monitor Info Reading (Using hypothesized ID 0x7B5)
        # ctk.CTkButton(self.ibr_ctrl_frame, text="Ler Info Monitor (7B5->7BD)", command=lambda: self.read_module_info(0x7B5)).pack(pady=5)
        
        # --- IBR Signals (Visuals) - 4 Analog Gauges (2x2 Grid) ---
        self.ibr_signals_frame = ctk.CTkFrame(self.ibr_tab)
        self.ibr_signals_frame.pack(fill="both", expand=True, padx=10, pady=4)
        # Configure for 2 columns
        self.ibr_signals_frame.grid_columnconfigure(0, weight=1)
        self.ibr_signals_frame.grid_columnconfigure(1, weight=1)
        
        gauge_size = 160 # Compact size for 1366x768

        # 1. Gate Position (Row 0, Col 0)
        self.gate_frame = ctk.CTkFrame(self.ibr_signals_frame, fg_color="transparent")
        self.gate_frame.grid(row=0, column=0, padx=10, pady=1)
        self.gate_gauge = AnalogGauge(self.gate_frame, width=gauge_size, height=gauge_size, min_val=0, max_val=100, title="GATE POS", unit="%", color="#00ffaa")
        self.gate_gauge.pack()
        
        # 2. IBR Current Monitor (Row 0, Col 1)
        self.current_frame = ctk.CTkFrame(self.ibr_signals_frame, fg_color="transparent")
        self.current_frame.grid(row=0, column=1, padx=10, pady=1)
        # Amperage usually goes up to 50A-60A for these motors. User input: Raw/2. Peak ~35A.
        self.ibr_current_gauge = AnalogGauge(self.current_frame, width=gauge_size, height=gauge_size, min_val=0, max_val=50, title="CORRENTE", unit="A", color="#ffff00")
        self.ibr_current_gauge.pack()

        # 3. Trigger Track 1 (Pista 1) (Row 1, Col 0)
        self.track1_frame = ctk.CTkFrame(self.ibr_signals_frame, fg_color="transparent")
        self.track1_frame.grid(row=1, column=0, padx=10, pady=1)
        self.ibr_track1_gauge = AnalogGauge(self.track1_frame, width=gauge_size, height=gauge_size, min_val=0, max_val=100, title="GATILHO PISTA 1", unit="%", color="#ff00aa")
        self.ibr_track1_gauge.pack()

        # 4. Trigger Track 2 (Pista 2) (Row 1, Col 1)
        self.track2_frame = ctk.CTkFrame(self.ibr_signals_frame, fg_color="transparent")
        self.track2_frame.grid(row=1, column=1, padx=10, pady=1)
        self.ibr_track2_gauge = AnalogGauge(self.track2_frame, width=gauge_size, height=gauge_size, min_val=0, max_val=100, title="GATILHO PISTA 2", unit="%", color="#ff00aa")
        self.ibr_track2_gauge.pack()

        # Update controls frame to be below signals
        self.ibr_ctrl_frame.pack(side="bottom", fill="x", padx=20, pady=4)

        # Placeholder for Gate Control
        ctk.CTkButton(self.ibr_ctrl_frame, text="Ler Dados (Gate Pos)", command=lambda: self.send_can_packet(0x7B2, 8, [0x02, 0x21, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00])).pack(pady=2)


        # --- IBR-MODULE Tab Setup (Identification/Specs) ---
        self.ibr_module_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.ibr_module_tab, text="Identificacao do Modulo IBR", font=("Arial", 16, "bold")).pack(pady=10)

        self.ibr_info_frame = ctk.CTkFrame(self.ibr_module_tab)
        self.ibr_info_frame.pack(fill="x", padx=20, pady=10)
        
        # Info Labels
        self.ibr_info_labels = {}
        info_grid = ctk.CTkFrame(self.ibr_info_frame, fg_color="transparent")
        info_grid.pack(side="left", padx=10)
        
        for i, (key, label) in enumerate([("part", "Part #: --"), ("vin", "VIN: --"), ("sw", "SW/Ser: --")]):
            lbl = ctk.CTkLabel(info_grid, text=label, font=("Arial", 14))
            lbl.grid(row=i, column=0, sticky="w", pady=5)
            self.ibr_info_labels[key] = lbl

        ctk.CTkButton(self.ibr_info_frame, text="Ler Tudo (1A)", width=100, command=self.read_ibr_full_info).pack(side="right", padx=10, pady=10)
        
        # Additional IBR Module Actions
        self.ibr_mod_actions = ctk.CTkFrame(self.ibr_module_tab)
        self.ibr_mod_actions.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(self.ibr_mod_actions, text="Acoes do Modulo", font=("Arial", 12, "bold")).pack(pady=5)
        ctk.CTkButton(self.ibr_mod_actions, text="Reset de Modulo (11 01)", command=lambda: self.send_can_packet(0x7B2, 8, [0x02, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])).pack(pady=5)

        # --- Cluster Tab Setup ---
        self.cluster_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.cluster_tab, text="Painel de Instrumentos (Cluster)", font=("Arial", 16, "bold")).pack(pady=10)
        
        self.cluster_act_frame = ctk.CTkFrame(self.cluster_tab)
        self.cluster_act_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(self.cluster_act_frame, text="Teste de Indicadores (2F CF 07)").pack(pady=5)
        
        ctk.CTkButton(self.cluster_act_frame, text="Teste Lampadas/Icones", command=lambda: self.send_cluster_actuation(0xCF, 0x07, 0x03, 0x80)).pack(pady=5)
        ctk.CTkButton(self.cluster_act_frame, text="Ler Info Painel", command=lambda: self.read_module_info(0x7B3)).pack(pady=5)

        self.dtc_tab.grid_columnconfigure(0, weight=1)
        self.dtc_controls_frame = ctk.CTkFrame(self.dtc_tab, fg_color="transparent")
        self.dtc_controls_frame.pack(pady=10, fill="x")

        self.btn_read_dtc = ctk.CTkButton(self.dtc_controls_frame, text="LER CODIGOS DE FALHA (DTC)", 
                                          font=("Arial", 12, "bold"), fg_color="#AA0000",
                                          command=self.read_brp_dtc)
        self.btn_read_dtc.pack(side="left", padx=10)
        
        self.btn_clear_dtc = ctk.CTkButton(self.dtc_controls_frame, text="LIMPAR CODIGOS", 
                                          font=("Arial", 12, "bold"), fg_color="#555555",
                                          command=self.clear_brp_dtc)
        self.btn_clear_dtc.pack(side="left", padx=10)
        
        # Seletor de modelo: "Auto (por ECU)" ou um modelo concreto da base
        self._model_display_to_key = {"Auto (por ECU)": None}
        _model_displays = []
        for _key, _info in (BRP_DTC_BY_MODEL.get("models") or {}).items():
            _disp = _info.get("display") or _key
            self._model_display_to_key.setdefault(_disp, _key)
            _model_displays.append(_disp)
        _model_displays.sort()
        self.model_selector = ctk.CTkOptionMenu(
            self.dtc_controls_frame,
            values=["Auto (por ECU)"] + _model_displays,
            width=280,
            command=self.on_model_selected,
        )
        self.model_selector.set("Auto (por ECU)")
        self.model_selector.pack(side="left", padx=10)

        self.btn_read_vin = ctk.CTkButton(
            self.dtc_controls_frame, text="LER VIN", width=90, fg_color="#225577",
            command=self.request_vin)
        self.btn_read_vin.pack(side="left", padx=10)
        
        self.dtc_status_label = ctk.CTkLabel(self.dtc_controls_frame, text="Status: Pronto", text_color="yellow")
        self.dtc_status_label.pack(side="left", padx=10)

        # DTC Header
        self.dtc_header = ctk.CTkFrame(self.dtc_tab, height=30, fg_color="#333333")
        self.dtc_header.pack(fill="x", padx=10, pady=(10, 0))
        
        self.dtc_header.grid_columnconfigure(2, weight=1)
        self.dtc_header.grid_columnconfigure(3, weight=1) # Solutions gets weight too
        
        ctk.CTkLabel(self.dtc_header, text="Status", font=("Arial", 12, "bold"), width=60).grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkLabel(self.dtc_header, text="Codigo", font=("Arial", 12, "bold"), width=70).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.dtc_header, text="Modulo", font=("Arial", 12, "bold"), width=65).grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkLabel(self.dtc_header, text="Descricao", font=("Arial", 12, "bold"), anchor="w").grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.dtc_header, text="Solucao / Analise", font=("Arial", 12, "bold"), anchor="w").grid(row=0, column=4, padx=5, pady=5, sticky="ew")
        
        # DTC List (Scrollable)
        self.dtc_list_frame = ctk.CTkScrollableFrame(self.dtc_tab, fg_color="#222222") # Darker background
        self.dtc_list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.dtc_list_frame.grid_columnconfigure(2, weight=1)
        self.dtc_list_frame.grid_columnconfigure(3, weight=1)

        # Initialize DTC rows from DB
        self.dtc_rows = {} # Map 'code' -> widget_dict
        self.init_dtc_table()
        
        # --- TAB YAMAHA: Yamaha Diagnostics (Clone of BRP) ---
        self.yamaha_tab = self.tabview.tab("Diagnostico Yamaha")
        self.yamaha_subtabs = ctk.CTkTabview(self.yamaha_tab)
        self.yamaha_subtabs.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.yamaha_ecm_tab = self.yamaha_subtabs.add("ECM")
        self.yamaha_ibr_tab = self.yamaha_subtabs.add("IBR")
        self.yamaha_cluster_tab = self.yamaha_subtabs.add("PAINEL")
        self.yamaha_dtc_tab = self.yamaha_subtabs.add("DTC")

        # Yamaha ECM Content (Cloned from BRP)
        self.yamaha_ecm_tab.grid_columnconfigure(0, weight=1)
        self.yamaha_ecm_tab.grid_columnconfigure(1, weight=1)
        
        self.yamaha_rpm_frame = ctk.CTkFrame(self.yamaha_ecm_tab, fg_color="transparent")
        self.yamaha_rpm_frame.grid(row=0, column=0, pady=5)
        self.yamaha_rpm_gauge = AnalogGauge(self.yamaha_rpm_frame, width=210, height=210, min_val=0, max_val=9000, title="RPM", unit="r/min", color="#00aaff")
        self.yamaha_rpm_gauge.pack()
        
        self.yamaha_tps_frame = ctk.CTkFrame(self.yamaha_ecm_tab, fg_color="transparent")
        self.yamaha_tps_frame.grid(row=0, column=1, pady=5)
        
        self.yamaha_ibr_lever_frame = ctk.CTkFrame(self.yamaha_tps_frame, fg_color="transparent")
        self.yamaha_ibr_lever_frame.pack(side="left", padx=5, fill="y")
        self.yamaha_ibr_lever_bar = VerticalBarWithMarker(self.yamaha_ibr_lever_frame, width=30, height=160, fill_color="#ff00aa", marker_color="orange")
        self.yamaha_ibr_lever_bar.pack(pady=(10, 5))
        self.yamaha_ibr_lever_bar.set_value(0)
        ctk.CTkLabel(self.yamaha_ibr_lever_frame, text="RiDE", font=("Arial", 12, "bold"), text_color="#ff00aa").pack()
        
        self.yamaha_tps_gauge = AnalogGauge(self.yamaha_tps_frame, width=210, height=210, min_val=0, max_val=100, title="ACELERADOR", unit="%", color="#ff5500")
        self.yamaha_tps_gauge.pack(side="left", padx=5)
        
        self.yamaha_aps_frame = ctk.CTkFrame(self.yamaha_tps_frame, fg_color="transparent")
        self.yamaha_aps_frame.pack(side="left", padx=5, fill="y")
        self.yamaha_aps_bar = ctk.CTkProgressBar(self.yamaha_aps_frame, orientation="vertical", width=25, height=160, progress_color="cyan")
        self.yamaha_aps_bar.pack(pady=(10, 5))
        self.yamaha_aps_bar.set(0)
        ctk.CTkLabel(self.yamaha_aps_frame, text="APS", font=("Arial", 12, "bold"), text_color="cyan").pack()
        
        self.yamaha_info_frame = ctk.CTkFrame(self.yamaha_ecm_tab)
        self.yamaha_info_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=5)
        self.yamaha_info_frame.grid_columnconfigure(0, weight=1)
        self.yamaha_info_frame.grid_columnconfigure(1, weight=1)
        self.yamaha_info_frame.grid_columnconfigure(2, weight=1)
        
        self.yamaha_engine_temp_label = ctk.CTkLabel(self.yamaha_info_frame, text="Temp. Motor: -- Â°C", font=("Arial", 12))
        self.yamaha_engine_temp_label.grid(row=0, column=0, pady=4)
        self.yamaha_intake_temp_label = ctk.CTkLabel(self.yamaha_info_frame, text="Temp. Admissao: -- Â°C", font=("Arial", 12))
        self.yamaha_intake_temp_label.grid(row=0, column=1, pady=4)
        self.yamaha_battery_label = ctk.CTkLabel(self.yamaha_info_frame, text="Bateria: -- V", font=("Arial", 12))
        self.yamaha_battery_label.grid(row=0, column=2, pady=4)
        
        self.yamaha_exhaust_temp_label = ctk.CTkLabel(self.yamaha_info_frame, text="Temp. Escape: -- Â°C", font=("Arial", 12))
        self.yamaha_exhaust_temp_label.grid(row=1, column=0, pady=4)
        self.yamaha_intake_pressure_label = ctk.CTkLabel(self.yamaha_info_frame, text="Pressao Admissao (MAP): -- kPa", font=("Arial", 12))
        self.yamaha_intake_pressure_label.grid(row=1, column=1, pady=4)
        self.yamaha_engine_status_label = ctk.CTkLabel(self.yamaha_info_frame, text="Status: PARADO", font=("Arial", 12, "bold"), text_color="red")
        self.yamaha_engine_status_label.grid(row=1, column=2, pady=4)
        
        self.yamaha_debug_103_label = ctk.CTkLabel(self.yamaha_info_frame, text="ID 103: APS(B0)=-- | B6=-- | B7=--", font=("Arial", 12), text_color="cyan")
        self.yamaha_debug_103_label.grid(row=2, column=0, columnspan=3, pady=3)
        self.yamaha_debug_110_label = ctk.CTkLabel(self.yamaha_info_frame, text="ID 110 [Hex]: -- -- -- -- -- -- -- --", font=("Consolas", 12), text_color="orange")
        self.yamaha_debug_110_label.grid(row=3, column=0, columnspan=3, pady=3)
        
        self.yamaha_vin_label = ctk.CTkLabel(self.yamaha_ecm_tab, text="VIN/Modelo: Procurando...", font=("Arial", 12), text_color="gray")
        self.yamaha_vin_label.grid(row=2, column=0, columnspan=2, pady=4)

        # Yamaha DTC Tab Setup
        self.yamaha_dtc_tab.grid_columnconfigure(0, weight=1)
        self.yamaha_dtc_controls_frame = ctk.CTkFrame(self.yamaha_dtc_tab, fg_color="transparent")
        self.yamaha_dtc_controls_frame.pack(pady=10, fill="x")
        
        self.yamaha_btn_read_dtc = ctk.CTkButton(self.yamaha_dtc_controls_frame, text="LER CODIGOS DE FALHA (DTC)", font=("Arial", 12, "bold"), fg_color="#AA0000", command=self.read_yamaha_dtc)
        self.yamaha_btn_read_dtc.pack(side="left", padx=10)
        self.yamaha_btn_clear_dtc = ctk.CTkButton(self.yamaha_dtc_controls_frame, text="LIMPAR CODIGOS", font=("Arial", 12, "bold"), fg_color="#555555", command=self.clear_yamaha_dtc)
        self.yamaha_btn_clear_dtc.pack(side="left", padx=10)
        self.yamaha_dtc_status_label = ctk.CTkLabel(self.yamaha_dtc_controls_frame, text="Status: Pronto", text_color="yellow")
        self.yamaha_dtc_status_label.pack(side="left", padx=10)

        # O ECM Yamaha transmite continuamente na K-Line (capturas: gaps de
        # 2-6 ms, nenhum > 8 ms), logo nao precisa de wakeup/StartCommunication.
        # Estes dois controlos existem para quem queira forcar o comportamento.
        self.yamaha_kwp_init_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.yamaha_dtc_controls_frame, text="Init KWP",
                        variable=self.yamaha_kwp_init_var, width=90,
                        font=("Arial", 11)).pack(side="left", padx=(14, 4))
        self.yamaha_poll_keepalive_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.yamaha_dtc_controls_frame, text="Poll keep-alive",
                        variable=self.yamaha_poll_keepalive_var, width=120,
                        font=("Arial", 11),
                        command=self.toggle_yamaha_poll_keepalive).pack(side="left", padx=4)
        
        self.yamaha_dtc_header = ctk.CTkFrame(self.yamaha_dtc_tab, height=30, fg_color="#333333")
        self.yamaha_dtc_header.pack(fill="x", padx=10, pady=(10, 0))
        self.yamaha_dtc_header.grid_columnconfigure(2, weight=1)
        self.yamaha_dtc_header.grid_columnconfigure(3, weight=1)
        
        ctk.CTkLabel(self.yamaha_dtc_header, text="Status", font=("Arial", 12, "bold"), width=60).grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkLabel(self.yamaha_dtc_header, text="Codigo", font=("Arial", 12, "bold"), width=70).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.yamaha_dtc_header, text="Descricao", font=("Arial", 12, "bold"), anchor="w").grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.yamaha_dtc_header, text="Solucao / Analise", font=("Arial", 12, "bold"), anchor="w").grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        self.yamaha_dtc_list_frame = ctk.CTkScrollableFrame(self.yamaha_dtc_tab, fg_color="#222222")
        self.yamaha_dtc_list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.yamaha_dtc_list_frame.grid_columnconfigure(2, weight=1)
        self.yamaha_dtc_list_frame.grid_columnconfigure(3, weight=1)
        self.yamaha_dtc_rows = {}
        self.init_yamaha_dtc_table()

        # --- Separador MONITOR: dicionario YDS (parametros Yamaha) ---
        self.yamaha_monitor_tab = self.yamaha_subtabs.add("MONITOR")
        self.yamaha_monitor_tab.grid_columnconfigure(0, weight=1)
        _mon_bar = ctk.CTkFrame(self.yamaha_monitor_tab, fg_color="transparent")
        _mon_bar.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(_mon_bar, text="Parametros YDS:", font=("Arial", 12, "bold")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(_mon_bar, text="Carregar", width=80, fg_color="#445544",
                      command=lambda: self.refresh_yamaha_monitor(force=True)).pack(side="left", padx=(0, 8))
        self.yamaha_monitor_search_var = ctk.StringVar()
        _mon_entry = ctk.CTkEntry(_mon_bar, textvariable=self.yamaha_monitor_search_var,
                                  placeholder_text="filtrar (ex.: TPS, temperatura)", width=280)
        _mon_entry.pack(side="left")
        self.yamaha_monitor_search_var.trace_add(
            "write", lambda *_a: self.refresh_yamaha_monitor())
        self.yamaha_monitor_count = ctk.CTkLabel(_mon_bar, text="", text_color="#88ccff")
        self.yamaha_monitor_count.pack(side="left", padx=12)
        self.yamaha_monitor_result = ctk.CTkLabel(_mon_bar, text="", text_color="#aaffaa")
        self.yamaha_monitor_result.pack(side="right", padx=10)
        ctk.CTkButton(_mon_bar, text="Converter", width=90, fg_color="#225577",
                      command=self.yamaha_monitor_convert).pack(side="right", padx=4)
        self.yamaha_monitor_value_var = ctk.StringVar(value="0")
        ctk.CTkEntry(_mon_bar, textvariable=self.yamaha_monitor_value_var,
                     placeholder_text="valor bruto", width=90).pack(side="right", padx=4)
        _convs = [c["text"] for c in (YAMAHA_YDS_DB.get("conversions") or [])] or ["X"]
        self.yamaha_monitor_conv_var = ctk.StringVar(value=_convs[0])
        ctk.CTkOptionMenu(_mon_bar, values=_convs, variable=self.yamaha_monitor_conv_var,
                          width=200).pack(side="right", padx=4)

        self.yamaha_monitor_list = ctk.CTkScrollableFrame(
            self.yamaha_monitor_tab, fg_color="#222222")
        self.yamaha_monitor_list.pack(fill="both", expand=True, padx=10, pady=5)
        self.yamaha_monitor_list.grid_columnconfigure(1, weight=1)
        self.yamaha_monitor_rows = []
        self.refresh_yamaha_monitor()

        self._build_yamaha_actuator_tab()

        # Initialize remaining tabs and console
        self.init_tabs()

    def _build_yamaha_actuator_tab(self):
        """Separador ATUADOR: testes de actuacao Yamaha por KWP2000."""
        self.yamaha_actuator_tab = self.yamaha_subtabs.add("ATUADOR")
        self.yamaha_actuator_tab.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self.yamaha_actuator_tab, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=8)

        items = self._yamaha_actuator_list()
        self._yamaha_actuator_code_by_label = {}
        labels = []
        for item in items:
            label = "%02d - %s" % (item.get("code", 0), item.get("text", ""))
            self._yamaha_actuator_code_by_label[label] = item.get("code", 0)
            labels.append(label)

        ctk.CTkLabel(bar, text="Atuador:", font=("Arial", 12, "bold")).pack(side="left", padx=(0, 8))
        self.yamaha_actuator_var = ctk.StringVar(value=labels[0] if labels else "")
        ctk.CTkOptionMenu(bar, values=labels or ["(sem dados YDS)"],
                          variable=self.yamaha_actuator_var, width=250).pack(side="left", padx=4)

        ctk.CTkLabel(bar, text="valor:").pack(side="left", padx=(8, 2))
        self.yamaha_actuator_value_var = ctk.StringVar(value="")
        ctk.CTkEntry(bar, textvariable=self.yamaha_actuator_value_var,
                     placeholder_text="0x00", width=70).pack(side="left", padx=2)

        ctk.CTkButton(bar, text="ATIVAR", width=90, fg_color="#AA0000",
                      command=self.yamaha_actuator_activate).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="PARAR", width=90, fg_color="#555555",
                      command=self.yamaha_actuator_deactivate).pack(side="left", padx=6)

        bar2 = ctk.CTkFrame(self.yamaha_actuator_tab, fg_color="transparent")
        bar2.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(bar2, text="Servico KWP:", font=("Arial", 11)).pack(side="left", padx=(0, 6))
        self.yamaha_actuator_service_var = ctk.StringVar(value="0x30 (KWP inputOutputControl)")
        self._yamaha_actuator_service_map = {
            "0x30 (KWP inputOutputControl)": 0x30,
            "0x32 (Yamaha - nao verificado)": 0x32,
        }
        ctk.CTkOptionMenu(
            bar2, values=list(self._yamaha_actuator_service_map),
            variable=self.yamaha_actuator_service_var, width=280,
            command=self._yamaha_actuator_set_service).pack(side="left", padx=4)

        ctk.CTkLabel(bar2, text="IOCP:").pack(side="left", padx=(10, 2))
        self.yamaha_actuator_iocp_var = ctk.StringVar(value="0x07")
        ctk.CTkEntry(bar2, textvariable=self.yamaha_actuator_iocp_var, width=60).pack(side="left")

        self.yamaha_actuator_log_box = ctk.CTkTextbox(
            self.yamaha_actuator_tab, height=240, font=("Consolas", 11))
        self.yamaha_actuator_log_box.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.yamaha_actuator_service = 0x30
        self.yamaha_actuator_iocp = 0x07
        self.yamaha_actuator_auto_off_s = 10
        self.yamaha_actuator_log(
            "%d atuadores do YDS carregados.\n"
            "ON  = <svc> <id> <iocp> [valor];  OFF = <svc> <id> 00 (devolve controlo ao ECU).\n"
            "O servico exacto do YDS nao esta documentado; comecar em 0x30 e comparar a resposta.\n"
            % len(items))

    def _yamaha_actuator_set_service(self, label):
        self.yamaha_actuator_service = self._yamaha_actuator_service_map.get(label, 0x30)
        try:
            self.yamaha_actuator_iocp = int(self.yamaha_actuator_iocp_var.get(), 0)
        except ValueError:
            self.yamaha_actuator_iocp = 0x07
        self.yamaha_actuator_log(
            "servico=0x%02X iocp=0x%02X\n"
            % (self.yamaha_actuator_service, self.yamaha_actuator_iocp))

    def init_dtc_table(self):
        """ Populate table with all known DTCs (Hidden or Gray) """
        for code, info in self._dtc_row_source().items():
            row_frame = ctk.CTkFrame(self.dtc_list_frame, fg_color="#2b2b2b", height=35)
            row_frame.pack(fill="x", pady=1)
            row_frame.grid_columnconfigure(3, weight=1)
            row_frame.grid_columnconfigure(4, weight=1)
            
            # Status Icon
            stat_lbl = ctk.CTkLabel(row_frame, text="--", font=("Arial", 12), width=60, text_color="gray")
            stat_lbl.grid(row=0, column=0, padx=5)
            
            # Code
            cod_lbl = ctk.CTkLabel(row_frame, text=code, font=("Arial", 12, "bold"), width=70, text_color="gray")
            cod_lbl.grid(row=0, column=1, padx=5)

            # Module source
            mod_lbl = ctk.CTkLabel(row_frame, text="--", font=("Arial", 11), width=65, text_color="#666")
            mod_lbl.grid(row=0, column=2, padx=5)
            
            # Description
            desc_lbl = ctk.CTkLabel(row_frame, text=info["desc"], font=("Arial", 12), anchor="w", text_color="gray")
            desc_lbl.grid(row=0, column=3, padx=5, sticky="ew")

            # Solution
            sol_lbl = ctk.CTkLabel(row_frame, text=info.get("sol", ""), font=("Arial", 11, "italic"), anchor="w", text_color="#666")
            sol_lbl.grid(row=0, column=4, padx=5, sticky="ew")
            
            self.dtc_rows[code] = {
                "frame": row_frame,
                "stat": stat_lbl,
                "cod": cod_lbl,
                "mod": mod_lbl,
                "desc": desc_lbl,
                "sol": sol_lbl,
                "active": False,
                "state": "inactive" # inactive, active, history
            }
            
            # Hover Events (ToolTip Support)
            # Create a more detailed text for the tooltip
            full_text = f"CÃ³digo: {code}\n\nDescriÃ§Ã£o: {info['desc']}\n\nSoluÃ§Ã£o do Manual: {info.get('sol', 'N/A')}"
            
            # Attach tooltip to all sub-widgets
            for w in [row_frame, stat_lbl, cod_lbl, desc_lbl, sol_lbl]:
                 ToolTip(w, text=full_text, delay=2000)

            # Keep row highlighting effects (Manual events)
            def on_enter(e, c=code):
                self.on_row_hover(c, True)
            def on_leave(e, c=code):
                self.on_row_hover(c, False)

            for w in [row_frame, stat_lbl, cod_lbl, desc_lbl, sol_lbl]:
                w.bind("<Enter>", on_enter, add="+")
                w.bind("<Leave>", on_leave, add="+")

    def on_model_selected(self, display):
        """Selecao manual do modelo (ou regresso ao modo automatico por ECU)."""
        display = display or ""
        if display.startswith("Auto"):
            self._manual_model = False
            self.active_brp_model = None
            self._scan_modules = set()
            self._scan_codes = set()
            self.rebuild_dtc_table()
            self.dtc_status_label.configure(text="Status: Pronto" + self._dtc_status_suffix())
            return
        key = getattr(self, "_model_display_to_key", {}).get(display)
        if not key:
            return
        self._manual_model = True
        self.set_brp_model(key)
        self.dtc_status_label.configure(text="Modelo manual" + self._dtc_status_suffix())

    def request_vin(self):
        """Pede o VIN ao ECM por UDS (ReadDataByIdentifier 22 F1 90)."""
        if not self.is_connected:
            self.dtc_status_label.configure(text="VIN: ligue-se primeiro")
            return
        try:
            self.console_textbox.insert("end", "> VIN 22 F1 90 -> 0x7E0\n")
            self.send_can_packet(0x7E0, 8, [0x03, 0x22, 0xF1, 0x90, 0x00, 0x00, 0x00, 0x00])
            self.dtc_status_label.configure(text="VIN: pedido enviado")
        except Exception as exc:
            self.dtc_status_label.configure(text=f"VIN: erro ({exc})")

    def set_vehicle_vin(self, vin):
        """Regista o VIN lido e resolve o modelo por ele (fonte mais fiável)."""
        vin = (vin or "").strip().upper()
        if not vin or vin == getattr(self, "vehicle_vin", None):
            return
        self.vehicle_vin = vin
        key, prefix = resolve_brp_model_by_vin(BRP_DTC_BY_MODEL, vin)
        if key:
            self._manual_model = False
            self.set_brp_model(key)
            self.dtc_status_label.configure(text=f"VIN {vin}" + self._dtc_status_suffix())
        else:
            self.dtc_status_label.configure(
                text=f"VIN {vin} | modelo nao esta na base (use o seletor)")

    def _begin_scan_if_stale(self):
        """Inicia um novo scan quando houve uma pausa > 5 s entre respostas."""
        now = time.monotonic()
        if now - getattr(self, "_scan_last_ts", 0.0) > 5.0:
            self._scan_modules = set()
            self._scan_codes = set()
        self._scan_last_ts = now

    def _note_module(self, module):
        """Registra um ECU que respondeu, mesmo sem DTCs (usado na identificacao)."""
        if not module:
            return
        self._begin_scan_if_stale()
        self._scan_modules = getattr(self, "_scan_modules", set())
        self._scan_modules.add(module)

    def _active_model(self):
        """Perfil de modelo ativo (dict) ou None."""
        key = getattr(self, "active_brp_model", None)
        if not key:
            return None
        return (BRP_DTC_BY_MODEL.get("models") or {}).get(key)

    def set_brp_model(self, key):
        """Troca o modelo ativo e reconstroi a tabela de DTCs."""
        if key is not None and key not in (BRP_DTC_BY_MODEL.get("models") or {}):
            key = None
        if key == getattr(self, "active_brp_model", None):
            return
        self.active_brp_model = key
        self.rebuild_dtc_table()

    def _dtc_row_source(self):
        """Codigos apresentados na tabela: catalogo do modelo ativo, senao global."""
        model = self._active_model()
        if not model:
            return BRP_DTC_DB
        entries = {}
        for code, entry in (model.get("dtcs") or {}).items():
            global_entry = BRP_DTC_DB.get(code, {})
            desc = entry.get("desc") or global_entry.get("desc", "Unknown Fault")
            entries[code] = {"desc": desc, "sol": global_entry.get("sol", "")}
        return dict(sorted(entries.items()))

    def rebuild_dtc_table(self):
        """Destroi as linhas atuais e repopula a partir do modelo (ou base global)."""
        for widgets in list(self.dtc_rows.values()):
            try:
                widgets["frame"].destroy()
            except Exception:
                pass
        self.dtc_rows.clear()
        self.init_dtc_table()

    def _update_brp_model_context(self):
        """Resolve o modelo com a evidencia acumulada e troca a tabela se mudar.

        Os acumuladores (_scan_modules/_scan_codes) sao geridos por
        update_dtc_table, que tambem deteta o inicio de um novo scan.
        """
        if getattr(self, "_manual_model", False):
            return

        # Um VIN conhecido manda sobre a inferencia por ECUs/DTCs.
        vin = getattr(self, "vehicle_vin", None)
        if vin:
            vin_key, _ = resolve_brp_model_by_vin(BRP_DTC_BY_MODEL, vin)
            if vin_key:
                if vin_key != getattr(self, "active_brp_model", None):
                    self.set_brp_model(vin_key)
                return

        modules = getattr(self, "_scan_modules", set())
        codes = getattr(self, "_scan_codes", set())
        ranked = rank_brp_models(BRP_DTC_BY_MODEL, modules, codes)
        key, score, contenders = resolve_brp_model(BRP_DTC_BY_MODEL, modules, codes)
        self._model_contenders = contenders
        models = BRP_DTC_BY_MODEL.get("models") or {}
        if ranked and contenders > 1:
            best = ranked[0][0]
            self._model_candidates = [models.get(k, {}).get("display", k)
                                      for s, k in ranked
                                      if abs(s - best) <= 0.01][:3]
        else:
            self._model_candidates = []
        current = getattr(self, "active_brp_model", None)
        if key == current:
            return
        # Um empate entre varios modelos (mesmo conjunto de ECUs) nao permite
        # decidir: mantem a tabela generica ate mais evidencia aparecer.
        if contenders != 1:
            return
        if current is not None and score < 0.75:
            return
        if key is None and score < 0.5:
            return
        self.set_brp_model(key)

    def _dtc_status_suffix(self):
        model = self._active_model()
        if model:
            return f" | Modelo: {model.get('display', '?')} ({model.get('dtc_count', 0)} codigos)"
        contenders = getattr(self, "_model_contenders", 0)
        if contenders > 1:
            names = getattr(self, "_model_candidates", [])
            detail = " / ".join(names) if names else ""
            suffix = f" | Modelo ambiguo ({contenders} candidatos)"
            return suffix + (f": {detail}" if detail else "")
        return ""

    def refresh_yamaha_monitor(self, force=False):
        """Repopula a lista de parametros YDS com o filtro atual (lazy)."""
        if not hasattr(self, "yamaha_monitor_list"):
            return
        needle = (self.yamaha_monitor_search_var.get() or "").strip().lower()
        items = YAMAHA_YDS_DB.get("items") or []
        if not needle and not force and not getattr(self, "_yamaha_monitor_loaded", False):
            self.yamaha_monitor_count.configure(
                text=f"{len(items)} parametros (clique Carregar)")
            return
        self._yamaha_monitor_loaded = True

        for widget in self.yamaha_monitor_rows:
            try:
                widget.destroy()
            except Exception:
                pass
        self.yamaha_monitor_rows = []

        row_index = 0
        for item in items:
            text = item.get("text", "")
            if needle and needle not in text.lower():
                continue
            idx_lbl = ctk.CTkLabel(self.yamaha_monitor_list,
                                   text=f"{item.get('index', 0):3d}", width=40,
                                   text_color="#88ccff", font=("Consolas", 11))
            idx_lbl.grid(row=row_index, column=0, padx=(4, 2), pady=0, sticky="w")
            txt_lbl = ctk.CTkLabel(self.yamaha_monitor_list, text=text, anchor="w",
                                   font=("Arial", 11))
            txt_lbl.grid(row=row_index, column=1, padx=(2, 6), sticky="ew")
            self.yamaha_monitor_rows.extend((idx_lbl, txt_lbl))
            row_index += 1

        self.yamaha_monitor_count.configure(text=f"{row_index} de {len(items)} parametros")

    def yamaha_monitor_convert(self):
        """Aplica uma formula de conversao YDS ao valor bruto introduzido."""
        formula = self.yamaha_monitor_conv_var.get()
        try:
            x = float((self.yamaha_monitor_value_var.get() or "0").replace(",", "."))
        except ValueError:
            self.yamaha_monitor_result.configure(text="valor invalido")
            return
        env = {"X": x, "x": x, "__builtins__": {}}
        env.update({"abs": abs, "sqrt": math.sqrt, "log": math.log, "exp": math.exp})
        try:
            value = eval(formula, env)  # formula vem do dicionario YDS, nao do utilizador
        except Exception as exc:
            self.yamaha_monitor_result.configure(text=f"erro: {exc}")
            return
        self.yamaha_monitor_result.configure(text=f"{formula} -> {value:.4g}")

    def on_row_hover(self, code, is_hovering):
        if code not in self.dtc_rows: return
        w = self.dtc_rows[code]
        
        # Don't change look if it's already Active (High Priority)
        if w["state"] == "active": return 
        
        if is_hovering:
             # Highlight visual
             w["frame"].configure(fg_color="#444444")
             w["stat"].configure(text_color="#eee")
             w["cod"].configure(text_color="#fff")
             w["desc"].configure(text_color="#fff")
             w["sol"].configure(text_color="#ddd")
        else:
             # Restore visual based on state
             self.update_row_visuals(code)

    def update_row_visuals(self, code):
        """ Updates a single row's colors based on its stored state """
        if code not in self.dtc_rows: return
        w = self.dtc_rows[code]
        state = w["state"]
        
        if state == "active":
             w["frame"].configure(fg_color="#4a1a1a") # Dark Red BG
             w["stat"].configure(text="ATIVO", text_color="#FF3333")
             w["cod"].configure(text_color="white")
             w["desc"].configure(text_color="white")
             w["sol"].configure(text_color="#FFaaaa")
             
        elif state == "history":
             w["frame"].configure(fg_color="#333300") # Dark Yellow BG
             w["stat"].configure(text="HISTORICO", text_color="orange")
             w["cod"].configure(text_color="#eee")
             # w["desc"].configure(text_color="#ccc") # Keep description readable
             w["desc"].configure(text_color="#ccc")
             w["sol"].configure(text_color="#999")
             
        else: # inactive
             w["frame"].configure(fg_color="#2b2b2b")
             w["stat"].configure(text="--", text_color="gray")
             w["cod"].configure(text_color="gray")
             w["desc"].configure(text_color="gray")
             w["sol"].configure(text_color="#666")

    def init_yamaha_dtc_table(self):
        """ Populate Yamaha table with all known DTCs (Hidden or Gray) """
        for code, info in YAMAHA_DTC_DB.items():
            row_frame = ctk.CTkFrame(self.yamaha_dtc_list_frame, fg_color="#2b2b2b", height=35)
            row_frame.pack(fill="x", pady=1)
            row_frame.grid_columnconfigure(2, weight=1)
            row_frame.grid_columnconfigure(3, weight=1)
            
            # Status Icon
            stat_lbl = ctk.CTkLabel(row_frame, text="--", font=("Arial", 12), width=60, text_color="gray")
            stat_lbl.grid(row=0, column=0, padx=5)
            
            # Code
            cod_lbl = ctk.CTkLabel(row_frame, text=code, font=("Arial", 12, "bold"), width=70, text_color="gray")
            cod_lbl.grid(row=0, column=1, padx=5)
            
            # Description
            desc_lbl = ctk.CTkLabel(row_frame, text=info["desc"], font=("Arial", 12), anchor="w", text_color="gray")
            desc_lbl.grid(row=0, column=2, padx=5, sticky="ew")

            # Solution
            sol_lbl = ctk.CTkLabel(row_frame, text=info.get("sol", ""), font=("Arial", 11, "italic"), anchor="w", text_color="#666")
            sol_lbl.grid(row=0, column=3, padx=5, sticky="ew")
            
            self.yamaha_dtc_rows[code] = {
                "frame": row_frame,
                "stat": stat_lbl,
                "cod": cod_lbl,
                "desc": desc_lbl,
                "sol": sol_lbl,
                "active": False,
                "state": "inactive" # inactive, active, history
            }
            
            # Hover Events (ToolTip Support)
            full_text = f"CÃ³digo: {code}\n\nDescriÃ§Ã£o: {info['desc']}\n\nSoluÃ§Ã£o: {info.get('sol', 'N/A')}"
            
            for w in [row_frame, stat_lbl, cod_lbl, desc_lbl, sol_lbl]:
                 ToolTip(w, text=full_text, delay=2000)

            # Keep row highlighting effects (Manual events)
            def on_enter(e, c=code):
                self.on_yamaha_row_hover(c, True)
            def on_leave(e, c=code):
                self.on_yamaha_row_hover(c, False)

            for w in [row_frame, stat_lbl, cod_lbl, desc_lbl, sol_lbl]:
                w.bind("<Enter>", on_enter, add="+")
                w.bind("<Leave>", on_leave, add="+")

    def on_yamaha_row_hover(self, code, is_hovering):
        if code not in self.yamaha_dtc_rows: return
        w = self.yamaha_dtc_rows[code]
        
        # Don't change look if it's already Active (High Priority)
        if w["state"] == "active": return 
        
        if is_hovering:
             # Highlight visual
             w["frame"].configure(fg_color="#444444")
             w["stat"].configure(text_color="#eee")
             w["cod"].configure(text_color="#fff")
             w["desc"].configure(text_color="#fff")
             w["sol"].configure(text_color="#ddd")
        else:
             # Restore visual based on state
             self.update_yamaha_row_visuals(code)

    def update_yamaha_row_visuals(self, code):
        """ Updates a single row's colors based on its stored state """
        if code not in self.yamaha_dtc_rows: return
        w = self.yamaha_dtc_rows[code]
        state = w["state"]
        
        if state == "active":
             w["frame"].configure(fg_color="#4a1a1a") # Dark Red BG
             w["stat"].configure(text="ATIVO", text_color="#FF3333")
             w["cod"].configure(text_color="white")
             w["desc"].configure(text_color="white")
             w["sol"].configure(text_color="#FFaaaa")
             
        elif state == "history":
             w["frame"].configure(fg_color="#333300") # Dark Yellow BG
             w["stat"].configure(text="HISTORICO", text_color="orange")
             w["cod"].configure(text_color="#eee")
             w["desc"].configure(text_color="#ccc") # Keep description readable
             w["sol"].configure(text_color="#999")
             
        else: # inactive
             w["frame"].configure(fg_color="#2b2b2b")
             w["stat"].configure(text="--", text_color="gray")
             w["cod"].configure(text_color="gray")
             w["desc"].configure(text_color="gray")
             w["sol"].configure(text_color="#666")

    def read_brp_dtc(self):
        """ Try multiple methods for BRP DTC (Siemens & Bosch) """
        if not self.is_connected: return
        
        self.dtc_status_label.configure(text="Solicitando Codigos...")
        
        # Reset visual state of all rows before new scan
        for code, widgets in self.dtc_rows.items():
            widgets["state"] = "inactive"
            widgets["active"] = False
            self.update_row_visuals(code)
        
        # 1. Try Bosch UDS Method (Service 19)
        # 03 19 02 09 (ReadDTCInformation, ByStatusMask, Confirmed+Pending)
        self.console_textbox.insert("end", "> Sending BRP/Bosch UDS Read DTC (19 02 09)...\n")
        self.send_can_packet(0x7E0, 8, [0x03, 0x19, 0x02, 0x09, 0x00, 0x00, 0x00, 0x00])

        # 2. Schedule Siemens KWP Method (Service 18)
        # 2009 models (Siemens) require a Session Start (10 03) before reading DTCs (18)
        def send_kwp():
            self.console_textbox.insert("end", "> Sending Start Session (10 03) for KWP...\n")
            self.send_can_packet(0x7E0, 8, [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])

            def send_kwp_read():
                 self.console_textbox.insert("end", "> Sending BRP/Siemens KWP Read DTC (18 00 FF 00)...\n")
                 self.send_can_packet(0x7E0, 8, [0x04, 0x18, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00])
            
            self.after(200, send_kwp_read)
            
        self.after(500, send_kwp)

    def clear_brp_dtc(self):
        """ Send Clear DTC commands """
        if not self.is_connected: return
        
        self.dtc_status_label.configure(text="Limpando Codigos...")
        self.console_textbox.insert("end", "> Sending BRP Clear DTC Commands...\n")
        
        # 1. UDS Clear Diag Info (Service 14) - Group FF FF FF (All)
        # 04 14 FF FF FF 00 00 00
        self.send_can_packet(0x7E0, 8, [0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00])

        # 2. Schedule KWP Clear immediately after
        # KWP often uses 14 as well, or 14 FF 00
        def send_kwp_clear():
             self.send_can_packet(0x7E0, 8, [0x03, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00])
             self.dtc_status_label.configure(text="Comando de Limpeza Enviado.")
             
        self.after(200, send_kwp_clear)

    def unlock_ecm_security(self):
        """ Try to unlock ECM Security based on Protocol """
        if not self.is_connected: return
        
        # Determine Security Level based on Protocol
        # KWP (2009): Level 1 (Seed 27 01, Key 27 02)
        # UDS (2010+): Level 5 (Seed 27 05, Key 27 06) or Level 7 (Unlimited?)
        
        is_kwp = (self.active_protocol == "KWP")
        level = 0x01 if is_kwp else 0x05 
        
        self.console_textbox.insert("end", f"> Requesting Security Seed (27 {level:02X}) [{self.active_protocol}]...\n")
        self.lbl_sec_status.configure(text=f"Status: Solicitando Seed (Lvl {level:02X})...", text_color="yellow")
        
        # Request Seed
        self.send_can_packet(0x7E0, 8, [0x02, 0x27, level, 0x00, 0x00, 0x00, 0x00, 0x00])

    def run_routine(self, rid):
        """ Start a diagnostic routine (31 01 AA BB) """
        if not self.is_connected: return
        rid_h = (rid >> 8) & 0xFF
        rid_l = rid & 0xFF
        self.console_textbox.insert("end", f"> Starting Routine {rid:04X}...\n")
        # 31 01 H L
        self.send_can_packet(0x7E0, 8, [0x04, 0x31, 0x01, rid_h, rid_l, 0x00, 0x00, 0x00])

    def send_custom_routine(self):
        try:
            txt = self.entry_rid.get().strip()
            val = int(txt, 16)
            self.run_routine(val)
        except:
            self.console_textbox.insert("end", "Error: Invalid Hex ID\n")

    def stop_custom_routine(self):
        try:
            txt = self.entry_rid.get().strip()
            val = int(txt, 16)
            rid_h = (val >> 8) & 0xFF
            rid_l = val & 0xFF
            self.console_textbox.insert("end", f"> Stopping Routine {val:04X}...\n")
            # 31 02 H L (Stop)
            self.send_can_packet(0x7E0, 8, [0x04, 0x31, 0x02, rid_h, rid_l, 0x00, 0x00, 0x00])
        except: pass

    def _yamaha_in_kline_mode(self):
        """True quando o transporte ativo e K-Line (Yamaha KWP2000)."""
        try:
            if self.connection_mode != "AVR":
                return False
            if self.avr_bus_var.get() != "K-Line":
                return False
            proto = (self.avr_kline_proto_var.get() or "").strip().lower()
            return proto.startswith("yamaha")
        except Exception:
            return False

    def _kwp_payload(self, raw):
        """Extrai o corpo KWP de uma resposta crua (tira filler e header)."""
        resp = [b for b in raw]
        while resp and resp[0] in (0xFE, 0xFF):
            resp.pop(0)
        if not resp:
            return []
        fmt = resp[0]
        if fmt & 0x80:                      # com formato no primeiro byte
            length = fmt & 0x3F
            body = resp[1:]
            if fmt & 0x40 and body:         # com byte de comprimento adicional
                length = body[0]
                body = body[1:]
            return body[:length] if length else body
        return resp

    def _yamaha_kline_read_dtc(self):
        """Le os DTC por KWP2000 readDTCByStatus (18 00 FF 00) na K-Line.

        O ECM Yamaha responde com codigos numericos; a resposta e registada no
        console para permitir comparar o formato real antes de o assumir.
        """
        t = self.avr_transport
        if t is None:
            self.yamaha_dtc_status_label.configure(text="AVR indisponivel")
            return
        if not self._yamaha_yds_session_ready("leitura de DTC"):
            return
        if not self._kline_session_lock.acquire(blocking=False):
            self.yamaha_dtc_status_label.configure(text="Sessao K-Line ocupada")
            return
        try:
            body = [0x84, 0x11, 0xF1, 0x18, 0x00, 0xFF, 0x00]
            frame = bytes(body + [sum(body) & 0xFF])
            self._avr_log("K-Line TX: " + " ".join(f"{b:02X}" for b in frame) + "\n")
            self._kline_record("TX", list(frame))
            # Espera o gap de silencio antes de transmitir.
            resp = self._yamaha_tx_request(frame, idle_ms=40, first_ms=250)

            if not resp:
                self.yamaha_dtc_status_label.configure(text="Sem resposta ao pedido de DTC")
                self._avr_log("K-Line DTC: sem resposta\n")
                return

            self._avr_log("K-Line RX: " + " ".join(f"{b:02X}" for b in resp) + "\n")
            self._kline_record("RX", resp)
            if getattr(self, "_yds_link", None) is not None:
                # Link YDS: nao ha trama com comprimento/NRC -- cada byte enviado
                # devolve uma resposta de 1 byte (FUN_00479570). O mapeamento
                # byte-a-byte dos comandos de DTC ainda nao foi decodificado.
                self._avr_log(
                    f"YDS: {len(resp)} resposta(s) de 1 byte "
                    "(sem cabecalho KWP; mapeamento de DTC pendente)\n")
                self.yamaha_dtc_status_label.configure(
                    text="Link YDS: bytes enviados; mapeamento de DTC pendente")
                return
            payload = self._kwp_payload(resp)
            if payload and payload[0] == 0x7F:
                nrc = payload[2] if len(payload) > 2 else 0
                self.yamaha_dtc_status_label.configure(
                    text=f"Pedido de DTC rejeitado pelo ECM (NRC {nrc:02X})")
                return
            self.parse_yamaha_kwp_dtc(payload)
        except Exception as exc:
            self.yamaha_dtc_status_label.configure(text="Erro na leitura de DTC")
            self._avr_log(f"K-Line DTC erro: {exc}\n")
        finally:
            self._kline_session_lock.release()

    def parse_yamaha_kwp_dtc(self, payload):
        """Converte a resposta KWP2000 (0x58) em codigos YDS numericos.

        O YDS mostra o DTC como numero decimal. O ECM devolve 16 bits; quando o
        byte alto e zero o codigo e o byte baixo. O status KWP2000 e guardado
        no texto para diagnostico.
        """
        if len(payload) < 2:
            self.yamaha_dtc_status_label.configure(text="Resposta KWP curta")
            return "KWP Error"

        count = payload[1]
        body = list(payload[2:])
        stride = 0
        if body:
            if len(body) % 3 == 0:
                stride = 3          # DTC_H, DTC_L, status
            elif len(body) % 2 == 0:
                stride = 2          # DTC_L, status

        dtcs = []
        i = 0
        while stride and i + stride <= len(body):
            if stride == 3:
                dtc_h, dtc_l, st = body[i], body[i + 1], body[i + 2]
            else:
                dtc_h, dtc_l, st = 0, body[i], body[i + 1]
            raw_value = (dtc_h << 8) | dtc_l
            info = describe_yamaha_code(raw_value if dtc_h else dtc_l)
            is_active = (st & 0x40) != 0 or (st & 0x20) != 0 or (st & 0x01) != 0
            dtcs.append({
                "code": info["code"],
                "is_active": is_active,
                "desc": info["desc"],
                "sol": info["sol"],
                "status_byte": st,
                "raw": raw_value,
                "count": 1,
            })
            i += stride

        if not dtcs:
            self.yamaha_dtc_status_label.configure(
                text=f"Sem DTC (ECM reportou {count})")
        self.update_yamaha_dtc_table(dtcs)
        return f"Found {len(dtcs)} Yamaha YDS DTCs"

    def read_yamaha_dtc(self):
        """ Pede os DTC ao ECM Yamaha.

            K-Line: KWP2000 readDTCByStatus (18 00 FF 00) para 0x11. O YDS
            apresenta o resultado como numero decimal, logo este caminho usa
            parse_yamaha_kwp_dtc() e nunca converte para P-code.
            CAN: OBD-II Mode 03 + UDS 19 nos modelos com CAN.
        """
        if not self.is_connected: return

        self.yamaha_dtc_status_label.configure(text="Solicitando Codigos Yamaha...")

        if self._yamaha_in_kline_mode():
            self.console_textbox.insert(
                "end", "> K-Line KWP2000 readDTCByStatus (18 00 FF 00) -> 0x11\n")
            threading.Thread(target=self._yamaha_kline_read_dtc, daemon=True).start()
            return

        self.console_textbox.insert("end", "> Sending Yamaha OBD-II Mode 03 & UDS 19...\n")

        # 1. Standard OBD-II Mode 03 (Request Emission-Related DTCs)
        # 02 03 00 ...
        self.send_can_packet(0x7E0, 8, [0x02, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

        # 2. Schedule UDS Read (Service 19) for newer models
        # 03 19 02 0C ... (Read Confirmed + Active)
        def send_uds_yamaha():
            self.send_can_packet(0x7E0, 8, [0x03, 0x19, 0x02, 0x0C, 0x00, 0x00, 0x00, 0x00])
            
        self.after(500, send_uds_yamaha)

    def clear_yamaha_dtc(self):
        """ Send Yamaha Clear DTC Commands """
        if not self.is_connected: return
        
        self.yamaha_dtc_status_label.configure(text="Limpando Codigos Yamaha...")
        self.console_textbox.insert("end", "> Sending Yamaha Clear DTC (Mode 04)...\n")
        
        # Standard OBD-II Mode 04 (Clear Diagnostic Information)
        self.send_can_packet(0x7E0, 8, [0x01, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self.yamaha_dtc_status_label.configure(text="Comando de Limpeza Enviado.")

    def parse_uds_response_deprecated(self, payload):
        if not payload: return "Empty Payload"
        sid = payload[0]
        
        # 0x59: UDS Read DTC Info Response
        if sid == 0x59:
             # Fmt: [59] [Sub] [Mask] [DTC1_H] [DTC1_M] [DTC1_L] [St] [DTC2...]
             num_bytes = len(payload)
             start_idx = 3 # Skip 59 02 Mask
             dtcs = []
             
             i = start_idx
             while i + 3 < num_bytes:
                 dtc_h = payload[i]
                 dtc_m = payload[i+1]
                 dtc_l = payload[i+2]
                 status = payload[i+3]
                 
                 # Convert to P-Code
                 type_code = (dtc_h & 0xC0) >> 6
                 prefix = {0: "P", 1: "C", 2: "B", 3: "U"}[type_code]
                 
                 code_hex = f"{((dtc_h & 0x3F) << 8 | dtc_m):04X}" 
                 code_str = f"{prefix}{code_hex}"
                 
                 # Look up description in BRP_DTC_DB
                 # DB format: "Pxxxx": {"desc": "...", "sol": "..."}
                 db_entry = lookup_dtc_entry(BRP_DTC_DB, code_str)
                 desc_str = db_entry.get("desc", f"Unknown Fault (St:{status:02X})")
                 
                 # Status Decoding (Simple)
                 # Bit 0: testFailed (Active)
                 # Bit 3: confirmedDTC (Stored)
                 is_active = (status & 0x01) != 0
                 
                 dtc_obj = {
                     'code': code_str,
                     'is_active': is_active,
                     'desc': desc_str,
                     'count': 1 # UDS usually doesn't send count in this mode
                 }
                 dtcs.append(dtc_obj)
                 i += 4
             
             self.update_dtc_table(dtcs)
             self.update_yamaha_dtc_table(dtcs)
             return f"Found {len(dtcs)} UDS DTCs"

        # 0x58: KWP Read DTC Response
        elif sid == 0x58:
            # Fmt: [58] [Count] [DTC1_H] [DTC1_L] [St] ... 
            if len(payload) < 2: return "KWP Error"
            count = payload[1]
            dtcs = []
            i = 2
            while i + 2 < len(payload):
                dtc_h = payload[i]
                dtc_l = payload[i+1]
                st = payload[i+2]
                
                # Assume KWP uses standard P-Codes too or just Hex
                code_str = f"P{dtc_h:02X}{dtc_l:02X}" # Usually P-Codes on KWP too
                
                db_entry = lookup_dtc_entry(BRP_DTC_DB, code_str)
                desc_str = db_entry.get("desc", f"Unknown KWP (St:{st:02X})")
                
                # Active logic for KWP can vary. Usually non-zero status or bit masks.
                # Let's assume (st & 0x20) or similar. 
                # For now, treat all as History unless clearly defined.
                # Actually, standard KWP2000 bit 6 is "Present".
                is_active = (st & 0x40) != 0 or (st & 0x20) != 0 
                # Let's use generic True for now to test, or check if status > 0
                
                dtc_obj = {
                    'code': code_str,
                    'is_active': is_active, 
                    'desc': desc_str,
                    'count': 1
                }
                dtcs.append(dtc_obj)
                i += 3
            
            self.update_dtc_table(dtcs)
            self.update_yamaha_dtc_table(dtcs)
            return f"Found {len(dtcs)} KWP DTCs"

        # 0x43: OBD-II Mode 03 Read DTC Response
        elif sid == 0x43:
            # Response to Mode 03 (Request Emission-Related Diagnostic Trouble Codes)
            # Fmt: [43] [DTC1_H] [DTC1_L] [DTC2_H] [DTC2_L] ...
            num_bytes = len(payload)
            dtcs = []
            i = 1 
            while i + 1 < num_bytes:
                dtc_h = payload[i]
                dtc_l = payload[i+1]
                
                # Padding check
                if dtc_h == 0 and dtc_l == 0:
                    i += 2
                    continue
                
                type_code = (dtc_h & 0xC0) >> 6
                prefix = {0: "P", 1: "C", 2: "B", 3: "U"}[type_code]
                
                code_hex = f"{((dtc_h & 0x3F) << 8 | dtc_l):04X}"
                code_str = f"{prefix}{code_hex}"
                
                is_active = True 
                
                dtc_obj = {
                     'code': code_str,
                     'is_active': is_active,
                     'desc': "OBD-II Fault", 
                     'count': 1
                }
                dtcs.append(dtc_obj)
                i += 2
            
            self.update_dtc_table(dtcs)
            self.update_yamaha_dtc_table(dtcs)
            return f"Found {len(dtcs)} OBD DTCs"

        # 0x41: OBD-II Mode 01 Response (Backwards compat)
        elif sid == 0x41:
            pid = payload[1]
            if pid in self.obd_pids:
                 name, calc_func = self.obd_pids[pid]
                 # Extract A, B, C, D if available
                 a = payload[2] if len(payload) > 2 else 0
                 b = payload[3] if len(payload) > 3 else 0
                 c = payload[4] if len(payload) > 4 else 0
                 d = payload[5] if len(payload) > 5 else 0
                 val_str = calc_func(a, b, c, d)
                 return f"OBD: {name} = {val_str}"

        return f"UDS Resp: {sid:X}"

    def update_dtc_table(self, dtc_list):
        # dtc_list is list of {code, is_active, ...}
        
        found_count = len(dtc_list)
        self.dtc_status_label.configure(text=f"Scan Completo: {found_count} Falhas")
        
        # 1. Update found codes
        for dtc in dtc_list:
            c = dtc['code']
            is_act = dtc['is_active']
            
            # If code exists in DB
            if c in self.dtc_rows:
                w = self.dtc_rows[c]
                # Highlighting
                if is_act:
                    w["state"] = "active"
                    w["active"] = True
                else:
                    if w["state"] != "active": # Don't downgrade active to history if multiple packets
                        w["state"] = "history"
                        w["active"] = False
                
                self.update_row_visuals(c)
                    
            else:
                # Unknown code - Create temporary row? 
                # Or just log it. For now let's just log or maybe add to top dynamically?
                # Adding dynamically is better.
                pass 

        # 2. Sort Rows: Active -> History (Modified Rows) -> Inactive (Default)
        # Get all widget items
        # We need to repack them in correct order.
        
        # Helper to determing sort weight
        def get_sort_weight(code):
            if code not in self.dtc_rows: return 100
            w = self.dtc_rows[code]
            state = w["state"]
            
            if state == "active": return 0
            if state == "history": return 1
            return 2
            
        sorted_codes = sorted(self.dtc_rows.keys(), key=get_sort_weight)
        
        # Repack
        for code in sorted_codes:
            self.dtc_rows[code]["frame"].pack_forget()
            self.dtc_rows[code]["frame"].pack(fill="x", pady=1)
            
        # Handle "Unknown" codes not in DB -- (Optional: Add them to top)
        for dtc in dtc_list:
            if dtc['code'] not in self.dtc_rows:
                 # Create a new dynamic row for unknown fault
                 row_frame = ctk.CTkFrame(self.dtc_list_frame, fg_color="#333", height=35)
                 row_frame.pack(fill="x", pady=1, before=self.dtc_list_frame.winfo_children()[0]) # Pack at top
                 
                 row_frame.grid_columnconfigure(2, weight=1)
                 row_frame.grid_columnconfigure(3, weight=1)
                 
                 ctk.CTkLabel(row_frame, text="UNK", text_color="red").grid(row=0, column=0)
                 ctk.CTkLabel(row_frame, text=dtc['code'], font=("Arial",12,"bold")).grid(row=0, column=1)
                 ctk.CTkLabel(row_frame, text="Falha Desconhecida", text_color="white").grid(row=0, column=2, sticky="ew")
                 ctk.CTkLabel(row_frame, text=f"Raw: {dtc.get('desc','')}", text_color="gray").grid(row=0, column=3, sticky="ew")

    def update_yamaha_dtc_table(self, dtc_list):
        """ Update table status based on scan results (List of Dicts) 
            dtc_list = [{'code': '01', 'is_active': bool, 'desc': '...'}, ...]

            Os codigos sao normalizados para o formato YDS (numero decimal de dois
            digitos) antes de tocar na tabela, venham eles do K-Line ou do CAN.
        """
        normalized = []
        for dtc in dtc_list:
            code, fmt = normalize_yamaha_code(dtc.get("code"))
            entry = dict(dtc)
            entry["code"] = code
            entry["format"] = fmt
            if not entry.get("desc"):
                entry["desc"] = describe_yamaha_code(code)["desc"]
            normalized.append(entry)
        dtc_list = normalized

        found_count = len(dtc_list)
        self.yamaha_dtc_status_label.configure(text=f"Scan Completo: {found_count} Falhas")
        
        # 1. Update found codes
        for dtc in dtc_list:
            c = dtc['code']
            is_act = dtc['is_active']
            
            # If code exists in DB
            if c in self.yamaha_dtc_rows:
                w = self.yamaha_dtc_rows[c]
                # Highlighting
                if is_act:
                    w["state"] = "active"
                    w["active"] = True
                else:
                    if w["state"] != "active": 
                        w["state"] = "history"
                        w["active"] = False
                
                self.update_yamaha_row_visuals(c)
                    
            else:
                pass 

        # 2. Sort Rows
        def get_sort_weight(code):
            if code not in self.yamaha_dtc_rows: return 100
            w = self.yamaha_dtc_rows[code]
            state = w["state"]
            
            if state == "active": return 0
            if state == "history": return 1
            return 2
            
        sorted_codes = sorted(self.yamaha_dtc_rows.keys(), key=get_sort_weight)
        
        # Repack
        for code in sorted_codes:
            self.yamaha_dtc_rows[code]["frame"].pack_forget()
            self.yamaha_dtc_rows[code]["frame"].pack(fill="x", pady=1)

        # Handle Unknowns
        for dtc in dtc_list:
            if dtc['code'] not in self.yamaha_dtc_rows:
                 info = describe_yamaha_code(dtc['code'])
                 row_frame = ctk.CTkFrame(self.yamaha_dtc_list_frame, fg_color="#333", height=35)
                 row_frame.pack(fill="x", pady=1, before=self.yamaha_dtc_list_frame.winfo_children()[0]) # Pack at top
                 
                 row_frame.grid_columnconfigure(2, weight=1)
                 row_frame.grid_columnconfigure(3, weight=1)
                 
                 ctk.CTkLabel(row_frame, text="UNK", text_color="red").grid(row=0, column=0)
                 ctk.CTkLabel(row_frame, text=dtc['code'], font=("Arial",12,"bold")).grid(row=0, column=1)
                 ctk.CTkLabel(row_frame, text=info["desc"], text_color="white").grid(row=0, column=2, sticky="ew")
                 raw_txt = f"Raw: 0x{dtc.get('raw', 0):04X}" if dtc.get("raw") is not None else ""
                 ctk.CTkLabel(row_frame, text=raw_txt, text_color="gray").grid(row=0, column=3, sticky="ew")

    def init_tabs(self):
        self.ibr_label = ctk.CTkLabel(self.ibr_tab, text="Status do Sistema IBR: Monitorando...", font=("Arial", 14), text_color="gray")
        self.ibr_label.pack(pady=20)
        
        # Old IBR layout removed to avoid duplicate gauges overwriting references
        # The new layout is defined in the IBR-MON setup section above.
        
        # Detailed IBR Status Labels
        self.ibr_status_frame = ctk.CTkFrame(self.ibr_tab, fg_color="transparent")
        self.ibr_status_frame.pack(fill="x", padx=20, pady=10)
        
        self.lbl_ibr_trigger = ctk.CTkLabel(self.ibr_status_frame, text="Gatilho Freio: 0 % (Raw: 0)", font=("Arial", 14), text_color="#ff00aa")
        self.lbl_ibr_trigger.pack(anchor="center")
        
        self.lbl_ibr_gate = ctk.CTkLabel(self.ibr_status_frame, text="Pos. Comporta: 0 % (Raw: 0)", font=("Arial", 14), text_color="orange")
        self.lbl_ibr_gate.pack(anchor="center")

        # --- Sub-Tab: IS (Intelligent Suspension) ---
        self.is_label = ctk.CTkLabel(self.is_tab, text="Status Suspensao IS: Aguardando Pacote...", font=("Arial", 14), text_color="gray")
        self.is_label.pack(pady=40)

        # --- Sub-Tab: CLUSTER ---
        self.cluster_label = ctk.CTkLabel(self.cluster_tab, text="Controles do Painel / Manopla", font=("Arial", 16, "bold"), text_color="white")
        self.cluster_label.pack(pady=20)
        
        self.cluster_controls_frame = ctk.CTkFrame(self.cluster_tab, fg_color="#333333")
        self.cluster_controls_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # VTS / Trim
        self.lbl_vts = ctk.CTkLabel(self.cluster_controls_frame, text="VTS (Trim): --", font=("Arial", 20, "bold"), text_color="gray")
        self.lbl_vts.pack(pady=10)

        # Right Control Arrows
        self.lbl_arrows = ctk.CTkLabel(self.cluster_controls_frame, text="Setas: --", font=("Arial", 20, "bold"), text_color="gray")
        self.lbl_arrows.pack(pady=10)

        # Mode / Set
        self.lbl_cluster_btn = ctk.CTkLabel(self.cluster_controls_frame, text="Modo/Set: --", font=("Arial", 20, "bold"), text_color="gray")
        self.lbl_cluster_btn.pack(pady=10)

        # --- YAMAHA: Clone Content for IBR/IS/CLUSTER ---
        self.yamaha_ibr_label = ctk.CTkLabel(self.yamaha_ibr_tab, text="Status do Sistema RiDE: Monitorando...", font=("Arial", 14), text_color="gray")
        self.yamaha_ibr_label.pack(pady=20)
        
        self.yamaha_ibr_content = ctk.CTkFrame(self.yamaha_ibr_tab, fg_color="transparent")
        self.yamaha_ibr_content.pack(fill="both", expand=True)

        self.yamaha_trigger_frame = ctk.CTkFrame(self.yamaha_ibr_content)
        self.yamaha_trigger_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.yamaha_trigger_gauge = AnalogGauge(self.yamaha_trigger_frame, width=220, height=220, min_val=0, max_val=100, title="GATILHO RiDE", unit="%", color="#ff00aa")
        self.yamaha_trigger_gauge.pack(pady=10)
        
        self.yamaha_gate_frame = ctk.CTkFrame(self.yamaha_ibr_content)
        self.yamaha_gate_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.yamaha_gate_gauge = AnalogGauge(self.yamaha_gate_frame, width=220, height=220, min_val=0, max_val=100, title="POSICAO COMPORTA", unit="%", color="orange")
        self.yamaha_gate_gauge.pack(pady=10)
        
        self.yamaha_ibr_status_frame = ctk.CTkFrame(self.yamaha_ibr_tab, fg_color="transparent")
        self.yamaha_ibr_status_frame.pack(fill="x", padx=20, pady=10)
        self.yamaha_lbl_ibr_trigger = ctk.CTkLabel(self.yamaha_ibr_status_frame, text="Gatilho RiDE (Esq): 0 % (Raw: 0)", font=("Arial", 14), text_color="#ff00aa")
        self.yamaha_lbl_ibr_trigger.pack(anchor="center")
        self.yamaha_lbl_ibr_gate = ctk.CTkLabel(self.yamaha_ibr_status_frame, text="Pos. Comporta: 0 % (Raw: 0)", font=("Arial", 14), text_color="orange")
        self.yamaha_lbl_ibr_gate.pack(anchor="center")

        self.yamaha_cluster_label = ctk.CTkLabel(self.yamaha_cluster_tab, text="Controles do Painel / Manopla", font=("Arial", 16, "bold"), text_color="white")
        self.yamaha_cluster_label.pack(pady=20)
        self.yamaha_cluster_controls_frame = ctk.CTkFrame(self.yamaha_cluster_tab, fg_color="#333333")
        self.yamaha_cluster_controls_frame.pack(fill="both", expand=True, padx=20, pady=20)
        self.yamaha_lbl_vts = ctk.CTkLabel(self.yamaha_cluster_controls_frame, text="VTS (Trim): --", font=("Arial", 20, "bold"), text_color="gray")
        self.yamaha_lbl_vts.pack(pady=10)
        self.yamaha_lbl_arrows = ctk.CTkLabel(self.yamaha_cluster_controls_frame, text="Setas: --", font=("Arial", 20, "bold"), text_color="gray")
        self.yamaha_lbl_arrows.pack(pady=10)
        self.yamaha_lbl_cluster_btn = ctk.CTkLabel(self.yamaha_cluster_controls_frame, text="Modo/Set: --", font=("Arial", 20, "bold"), text_color="gray")
        self.yamaha_lbl_cluster_btn.pack(pady=10)

        # --- TAB 1: Traffic Monitor (Treeview) ---
        self.monitor_frame = self.tabview.tab("Monitor Trafego")
        self.monitor_frame.grid_columnconfigure(0, weight=1)
        self.monitor_frame.grid_rowconfigure(0, weight=1)

        # Styling Treeview for Dark Mode
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", 
                        background="#2b2b2b", 
                        foreground="white", 
                        fieldbackground="#2b2b2b", 
                        rowheight=25)
        # style.map('Treeview', background=[('selected', '#1f538d')])
        # style.configure("Treeview.Heading", background="#1f538d", foreground="white")

        self.monitor_headers = ["ID", "DLC", "B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "Cont", "Freq", "Descr"]
        self.monitor_scroll = ctk.CTkScrollableFrame(self.monitor_frame, corner_radius=0)
        self.monitor_scroll.grid(row=0, column=0, sticky="nsew")
        self.monitor_scroll.grid_columnconfigure(12, weight=1) # Description column expands

        # Create Headers
        for i, h in enumerate(self.monitor_headers):
            l = ctk.CTkLabel(self.monitor_scroll, text=h, font=("Arial", 12, "bold"))
            l.grid(row=0, column=i, padx=2, sticky="w")
        
        self.monitor_rows = {} # { can_id: { 'widgets': [], 'selected': False } }

        # --- TAB 2: Network Graph (Canvas) ---
        self.graph_frame = self.tabview.tab("Grafo Rede")
        self.graph_frame.grid_columnconfigure(0, weight=1)
        self.graph_frame.grid_rowconfigure(0, weight=1)
        
        self.canvas = tk.Canvas(self.graph_frame, bg="#2b2b2b", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        # --- TAB 3: Signal Graph (Strip Charts) ---
        self.signal_tab = self.tabview.tab("Grafo Sinais")
        self.signal_tab.grid_columnconfigure(0, weight=1)
        self.signal_tab.grid_rowconfigure(1, weight=1)

        self.signal_selector_scroll = ctk.CTkScrollableFrame(self.signal_tab, label_text="Selecao de Sinais Yamaha", height=90)
        self.signal_selector_scroll.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        
        self.signals_scroll = ctk.CTkScrollableFrame(self.signal_tab, label_text="Sinais em Tempo Real (Byte 0)")

        # --- TAB 5: Atuadores (New) ---
        self.actuator_tab = self.tabview.add("Atuadores")
        self.actuator_tab.grid_columnconfigure(0, weight=1)
        self.actuator_tab.grid_rowconfigure(1, weight=1)
        
        # Security Access Section
        self.sec_frame = ctk.CTkFrame(self.actuator_tab)
        self.sec_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(self.sec_frame, text="Acesso de Seguranca (UDS Service 27)", font=("Arial", 14, "bold")).pack(pady=5)
        self.btn_unlock_ecm = ctk.CTkButton(self.sec_frame, text="Desbloquear ECM (Seed/Key)", command=self.unlock_ecm_security, fg_color="#aa0000")
        self.btn_unlock_ecm.pack(pady=5)
        ToolTip(self.btn_unlock_ecm, "Requer algoritmo Seed->Key.\nAlgoritmo atual desconhecido (Logs incompletos).", delay=500)
        self.lbl_sec_status = ctk.CTkLabel(self.sec_frame, text="Status: Bloqueado", text_color="red")
        self.lbl_sec_status.pack(pady=5)

        # Routines Section
        self.routines_frame = ctk.CTkFrame(self.actuator_tab)
        self.routines_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(self.routines_frame, text="Controle de Rotinas (Service 31)", font=("Arial", 14, "bold")).pack(pady=5)
        
        # Standard buttons
        self.act_btn_frame = ctk.CTkFrame(self.routines_frame, fg_color="transparent")
        self.act_btn_frame.pack(fill="x", pady=5)
        
        self.btn_coil = ctk.CTkButton(self.act_btn_frame, text="Teste IgniÃ§Ã£o (Coil 1)", command=lambda: self.run_routine(0x0203))
        self.btn_coil.pack(side="left", padx=5)
        ToolTip(self.btn_coil, "ID: 0x0203\nEncontrado em Log de 2009 (Sea-Doo).", delay=500)

        self.btn_inj = ctk.CTkButton(self.act_btn_frame, text="Teste Injetor 1", command=lambda: self.run_routine(0x0202))
        self.btn_inj.pack(side="left", padx=5)
        ToolTip(self.btn_inj, "ID: 0x0202\nProvÃ¡vel ID sequencial.", delay=500)

        self.btn_fan = ctk.CTkButton(self.act_btn_frame, text="Teste Ventoinha", command=lambda: self.run_routine(0x0204))
        self.btn_fan.pack(side="left", padx=5)
        ToolTip(self.btn_fan, "ID: 0x0204\nComum em Rotax.", delay=500)

        # Custom Routine
        self.custom_routine_frame = ctk.CTkFrame(self.routines_frame)
        self.custom_routine_frame.pack(fill="x", pady=20)
        ctk.CTkLabel(self.custom_routine_frame, text="Rotina Customizada (HEX ID):").pack(side="left", padx=5)
        self.entry_rid = ctk.CTkEntry(self.custom_routine_frame, width=80, placeholder_text="Ex: F001")
        self.entry_rid.pack(side="left", padx=5)
        ctk.CTkButton(self.custom_routine_frame, text="Enviar Start (31 01)", command=self.send_custom_routine).pack(side="left", padx=5)
        ctk.CTkButton(self.custom_routine_frame, text="Parar (31 02)", command=self.stop_custom_routine, fg_color="#555").pack(side="left", padx=5)
        self.signals_scroll.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        self.signal_rows = {} # Map ID -> {frame, canvas, values: deque}
        
        # --- TAB 4: Raw Log ---
        self.log_frame = self.tabview.tab("Log Bruto")
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=1)
        
        self.clear_btn = ctk.CTkButton(self.log_frame, text="Limpar Log", width=100, command=self.clear_log)
        self.clear_btn.grid(row=0, column=0, padx=10, pady=10, sticky="e")

        self.console_textbox = ctk.CTkTextbox(self.log_frame, font=("Consolas", 12))
        self.console_textbox.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        # Start UI Update Loop
        self.after(100, self.update_ui_loop)
        # (debug ticks desativados)

    def change_mode(self, value):
        self.connection_mode = value
        if value in ("Serial", "AVR"):
            self.tcp_frame.grid_forget()
            self.ixxat_frame.grid_forget()
            self.kvaser_frame.grid_forget()
            self.serial_frame.grid(row=3, column=0, sticky="ew")
        elif value == "TCP":
            self.serial_frame.grid_forget()
            self.ixxat_frame.grid_forget()
            self.kvaser_frame.grid_forget()
            self.tcp_frame.grid(row=3, column=0, sticky="ew")
        elif value == "IXXAT":
            self.serial_frame.grid_forget()
            self.tcp_frame.grid_forget()
            self.kvaser_frame.grid_forget()
            self.ixxat_frame.grid(row=3, column=0, sticky="ew")
        else:
            self.serial_frame.grid_forget()
            self.tcp_frame.grid_forget()
            self.ixxat_frame.grid_forget()
            self.kvaser_frame.grid(row=3, column=0, sticky="ew")

        # Show AVR sub-options only in AVR mode; hide main CAN bitrate selector
        if value == "AVR":
            self.avr_sub_frame.pack(fill="x")
            self.baud_label.grid_forget()
            self.kbps_option.grid_forget()
        else:
            self.avr_sub_frame.pack_forget()
            self.baud_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="w")
            self.kbps_option.grid(row=5, column=0, padx=20, pady=(5, 10), sticky="ew")

    def get_serial_ports(self):
        """ List available COM ports with friendly names """
        ports = serial.tools.list_ports.comports()
        port_list = [f"{p.device} - {p.description}" for p in ports]
        return port_list if port_list else ["No Ports"]

    def _parse_port(self, value: str) -> str:
        """ Extract 'COMx' from 'COMx - Description' """
        return value.split(" - ")[0].strip()

    def refresh_ports(self):
        """ Refresh the dropdown list """
        ports = self.get_serial_ports()
        self.port_option.configure(values=ports)
        self.port_option.set(ports[0])

    # ------------------------------------------------------------------
    # AVR sub-panel helpers
    # ------------------------------------------------------------------
    def _avr_log(self, msg: str):
        """Thread-safe log to console."""
        self.after(0, lambda m=msg: (self.console_textbox.insert("end", m), self.console_textbox.see("end")))

    _CMD_DEBUG_TICK = 0xF0

    def _poll_avr_debug(self):
        """Called every 500 ms from the tkinter main loop.
        Reads unsolicited CMD_DEBUG_TICK (0xF0) packets from the AVR and logs them.
        These packets carry g_ms_ticks so we can verify Timer0 is running at 1 kHz.
        """
        if self.avr_transport and self.is_connected and self.connection_mode == "AVR":
            try:
                pkt = self.avr_transport.poll_unsolicited()
                if pkt is not None and pkt.command == self._CMD_DEBUG_TICK and len(pkt.payload) >= 2:
                    ms = pkt.payload[0] | (pkt.payload[1] << 8)
                    ka = bool(pkt.payload[2]) if len(pkt.payload) >= 3 else False
                    self.console_textbox.insert("end", f"[AVR TICK] t={ms}ms ({ms/1000:.3f}s) ka={'ON' if ka else 'OFF'}\n")
                    self.console_textbox.see("end")
            except Exception:
                pass
        self.after(500, self._poll_avr_debug)

    def _python_tick(self):
        """Fires every 1000 ms (Python/OS side) for timing comparison with AVR ticks."""
        import time as _time
        self._py_tick_count += 1
        elapsed = _time.monotonic() - self._py_tick_start
        self.console_textbox.insert("end", f"[PY  TICK] count={self._py_tick_count}  elapsed={elapsed:.3f}s\n")
        self.console_textbox.see("end")
        self.after(1000, self._python_tick)

    def _kline_record(self, direction: str, frame: list):
        """Write a K-Line frame to the CSV log if recording is active.
        direction: 'TX' or 'RX'
        frame: list of integer bytes
        """
        if not self.is_recording or not self.log_writer:
            return
        try:
            ts = datetime.now().strftime("%H:%M:%S.%f")
            hex_data = " ".join(f"{b:02X}" for b in frame)
            self.log_writer.writerow([ts, f"KLINE-{direction}", len(frame), hex_data])
        except Exception:
            pass

    def _format_kline_status(self, status) -> str:
        return (
            f"state={status.state_name} high_ms={status.high_ms} low_ms={status.low_ms} "
            f"edges={status.edge_count} rx_bytes={status.rx_byte_count}"
        )

    def _on_avr_bus_change(self, value):
        """Show K-Line or CAN sub-options depending on selected AVR bus."""
        if value == "K-Line":
            self.avr_can_frame.pack_forget()
            self.avr_kline_frame.pack(fill="x")
        else:
            self.avr_kline_frame.pack_forget()
            self.avr_can_frame.pack(fill="x")

    def _on_avr_can_speed_change(self, choice):
        """Live bitrate change in CAN mode while connected."""
        if not self.is_connected or self.connection_mode != "AVR":
            return
        if choice == "Auto":
            threading.Thread(target=self._avr_can_auto_detect, daemon=True).start()
        else:
            def _do():
                try:
                    self._avr_log(f"  SET_MODE â†’ CAN ... ")
                    self.avr_transport.set_mode(InterfaceMode.CAN)
                    self._avr_log("OK\n")
                    self._avr_log(f"  CAN_SET_BITRATE {choice} kbps ... ")
                    self.avr_transport.can_set_bitrate(int(choice))
                    self._avr_log(f"OK\n")
                    can_status = self.avr_transport.can_get_status()
                    flags = []
                    if can_status.bus_off:
                        flags.append("BUS_OFF")
                    if can_status.error_warning:
                        flags.append("ERROR_WARNING")
                    if can_status.data_overrun:
                        flags.append("DATA_OVERRUN")
                    if can_status.rx_buffer_has_data:
                        flags.append("RX_PENDING")
                    self._avr_log(
                        f"  CAN_GET_STATUS sr=0x{can_status.status:02X} "
                        f"rxerr={can_status.rx_error_counter} txerr={can_status.tx_error_counter} "
                        f"rmc={can_status.rx_message_count} flags={','.join(flags) if flags else 'none'}\n"
                    )
                except Exception as e:
                    self._avr_log(f"ERRO: {e}\n")
            threading.Thread(target=_do, daemon=True).start()

    def _avr_can_auto_detect(self):
        """Try each standard CAN bitrate and pick the first one that receives a frame."""
        self._avr_log("CAN auto-detect: testando 500 â†’ 250 â†’ 125 â†’ 1000 kbpsâ€¦\n")
        for kbps in [500, 250, 125, 1000]:
            if not self.is_connected:
                return
            try:
                self._avr_log(f"  CAN_SET_BITRATE {kbps} kbps ... ")
                self.avr_transport.set_mode(InterfaceMode.CAN)
                self.avr_transport.can_set_bitrate(kbps)
                self._avr_log("OK â€” aguardando frame...\n")
                deadline = time.monotonic() + 0.20
                detected = False
                while time.monotonic() < deadline:
                    pkt = self.avr_transport.poll_unsolicited()
                    if pkt is not None and pkt.command == 0x24:
                        detected = True
                        break
                if detected:
                    self._avr_log(f"  -> trafego detectado em {kbps} kbps OK\n")
                    self.after(0, lambda k=str(kbps): self.avr_can_kbps_var.set(k))
                    return
                self._avr_log(f"  -> silencio\n")
            except Exception as e:
                self._avr_log(f"  ERRO: {e}\n")
        self._avr_log("Auto-detect: sem trÃ¡fego â€” usando 500 kbps\n")
        try:
            self.avr_transport.can_set_bitrate(500)
        except Exception:
            pass
        self.after(0, lambda: self.avr_can_kbps_var.set("500"))

    def clear_log(self):
        self.console_textbox.delete("0.0", "end")

    def toggle_connection(self):
        self.console_textbox.insert("end", f"--- CONNECT pressed (mode={self.connection_mode}, connected={self.is_connected}) ---\n")
        self.console_textbox.see("end")
        if not self.is_connected:
            # Connect
            if self.connection_mode == "Serial":
                self.connect_serial()
            elif self.connection_mode == "TCP":
                self.connect_tcp()
            elif self.connection_mode == "AVR":
                self.connect_avr()
            elif self.connection_mode == "KVASER":
                self.connect_kvaser()
            else:
                self.connect_ixxat()
        else:
            # Disconnect
            self.disconnect()

    def connect_serial(self):
        port = self._parse_port(self.port_option.get())
        if port == "No Ports":
            return

        try:
            # 500000 baud (User requested change from 1M)
            self.ser = serial.Serial(port, 500000, timeout=0.1) 
            
            self.is_connected = True
            self.update_ui_connected(f"Connected: {port}")
            self.console_textbox.insert("end", f"--- Serial Connected to {port} (500k) ---\n")
            
            # Start Thread
            self.stop_thread = False
            self.read_thread = threading.Thread(target=self.read_loop)
            self.read_thread.start()
            
        except Exception as e:
            self.console_textbox.insert("end", f"Serial Connection Error: {e}\n")

    def connect_avr(self):
        port = self._parse_port(self.port_option.get())
        if port == "No Ports":
            return

        if AvrTransport is None:
            self.console_textbox.insert("end", f"AVR backend unavailable: import failed ({AVR_IMPORT_ERROR})\n")
            return

        bus_type = self.avr_bus_var.get()  # "K-Line" or "CAN"

        try:
            self.avr_transport = AvrTransport(port, timeout=0.2)
            self.avr_transport.connect()
            log = self.console_textbox  # shorthand

            # --- Firmware handshake ---
            log.insert("end", f"--- AVR: abrindo {port} @ {self.avr_transport.baudrate} baud ---\n")
            try:
                info = self.avr_transport.get_info()
                log.insert("end", f"  firmware proto=0x{info['proto_version']:02X}  mode=0x{info['mode']:02X}\n")
            except Exception as e:
                log.insert("end", f"  GET_INFO falhou: {e}\n")

            if bus_type == "K-Line":
                baud = int(self.avr_kline_baud_var.get())
                proto = self.avr_kline_proto_var.get().strip()
                kline_status = None
                log.insert("end", f"  SET_MODE â†’ K-Line ... ")
                self.avr_transport.set_mode(InterfaceMode.KLINE)
                log.insert("end", "OK\n")
                log.insert("end", f"  KLINE_SET_BAUD {baud} ... ")
                self.avr_transport.kline_set_baud(baud)
                log.insert("end", "OK\n")
                try:
                    kline_status = self.avr_transport.kline_get_status(120)
                    log.insert("end", f"  KLINE_GET_STATUS {self._format_kline_status(kline_status)}\n")
                except Exception as e:
                    log.insert("end", f"  KLINE_GET_STATUS falhou: {e}\n")
                status_text = f"Connected AVR: {port} (K-Line {baud})"
                log.insert("end", f"--- AVR pronto em modo K-Line @ {baud} baud ---\n")
            else:
                kbps_choice = self.avr_can_kbps_var.get()
                log.insert("end", f"  SET_MODE â†’ CAN ... ")
                self.avr_transport.set_mode(InterfaceMode.CAN)
                log.insert("end", "OK\n")
                if kbps_choice == "Auto":
                    log.insert("end", "  CAN_SET_BITRATE 500 (provisÃ³rio, auto-detect pendente) ... ")
                    self.avr_transport.can_set_bitrate(500)
                    log.insert("end", "OK\n")
                else:
                    log.insert("end", f"  CAN_SET_BITRATE {kbps_choice} kbps ... ")
                    self.avr_transport.can_set_bitrate(int(kbps_choice))
                    log.insert("end", "OK\n")
                try:
                    can_status = self.avr_transport.can_get_status()
                    flags = []
                    if can_status.bus_off:
                        flags.append("BUS_OFF")
                    if can_status.error_warning:
                        flags.append("ERROR_WARNING")
                    if can_status.data_overrun:
                        flags.append("DATA_OVERRUN")
                    if can_status.rx_buffer_has_data:
                        flags.append("RX_PENDING")
                    log.insert(
                        "end",
                        f"  CAN_GET_STATUS sr=0x{can_status.status:02X} rxerr={can_status.rx_error_counter} "
                        f"txerr={can_status.tx_error_counter} rmc={can_status.rx_message_count} "
                        f"flags={','.join(flags) if flags else 'none'}\n",
                    )
                except Exception as e:
                    log.insert("end", f"  CAN_GET_STATUS falhou: {e}\n")
                status_text = f"Connected AVR: {port} ({kbps_choice}k)"
                log.insert("end", f"--- AVR pronto em modo CAN @ {kbps_choice} kbps ---\n")
            log.see("end")

            self.is_connected = True
            self.update_ui_connected(status_text)

            self.stop_thread = False
            self.read_thread = threading.Thread(target=self.read_loop, daemon=True)
            self.read_thread.start()

            # CAN auto-detect runs after thread starts
            if bus_type == "CAN" and self.avr_can_kbps_var.get() == "Auto":
                threading.Thread(target=self._avr_can_auto_detect, daemon=True).start()
            elif bus_type == "K-Line" and proto == "Yamaha" and baud in (9600, 10400, 15625):
                # Modo YDS (padrao): repete exactamente o que o YDS.exe faz ao
                # abrir o equipamento -- 300 baud + 0x1C, 9600, handshake.
                # Modo antigo (YDS link desmarcado): preserva o init KWP.
                _yds_chk = getattr(self, "yamaha_yds_link_var", None)
                _use_yds = bool(_yds_chk is not None and _yds_chk.get()
                                and YdsByteLink is not None)
                _init_chk = getattr(self, "yamaha_kwp_init_var", None)
                if _use_yds:
                    log.insert("end",
                               f"--- Yamaha {baud}: ligacao YDS (wake 0x1C @ {YDS_WAKE_BAUD} baud, "
                               "handshake FD E5 E5 FE FF FE FF) ---\n")
                    if kline_status is not None:
                        log.insert("end", f"    K-Line: {kline_status.state_name} "
                                          f"high={kline_status.high_ms}ms low={kline_status.low_ms}ms "
                                          f"edges={kline_status.edge_count} rx={kline_status.rx_byte_count}\n")
                    threading.Thread(
                        target=self._yamaha_kline_init_thread,
                        kwargs={"initial_status": kline_status},
                        daemon=True,
                    ).start()
                elif not _init_chk or not _init_chk.get():
                    log.insert("end",
                               f"--- Yamaha {baud}: ECM transmite continuamente; sem init KWP "
                               "(marque 'Init KWP' para forcar) ---\n")
                    if kline_status is not None:
                        log.insert("end", f"    K-Line: {kline_status.state_name} "
                                          f"high={kline_status.high_ms}ms low={kline_status.low_ms}ms "
                                          f"edges={kline_status.edge_count} rx={kline_status.rx_byte_count}\n")
                elif kline_status is None:
                    log.insert("end", "--- Yamaha: K-Line nao pode ser classificada; init nao iniciado ---\n")
                else:
                    log.insert("end", f"--- Yamaha {baud}: K-Line {kline_status.state_name}; a iniciar init KWP ---\n")
                    threading.Thread(
                        target=self._yamaha_kline_init_thread,
                        kwargs={"initial_status": kline_status},
                        daemon=True,
                    ).start()
            elif bus_type == "K-Line" and proto == "Yamaha" and baud == 16040:
                log.insert("end", f"--- Yamaha {baud}: baud experimental selecionado; modo passivo ---\n")
                log.insert("end", f"--- Yamaha {baud}: baud experimental selecionado; auto-init desabilitado para permitir sniff/teste passivo ---\n")

        except Exception as e:
            self.console_textbox.insert("end", f"AVR Connection Error: {e}\n")
            if self.avr_transport:
                try:
                    self.avr_transport.close()
                except Exception:
                    pass
            self.avr_transport = None

    def connect_tcp(self):
        ip = self.ip_entry.get()
        port = self.tcp_port_entry.get()
        
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(1.0) # Connection timeout
            self.tcp_socket.connect((ip, int(port)))
            self.tcp_socket.settimeout(0.1) # Read timeout
            
            self.is_connected = True
            self.tcp_buffer = ""
            self.update_ui_connected(f"Connected: {ip}:{port}")
            self.console_textbox.insert("end", f"--- TCP Connected to {ip}:{port} ---\n")
            
            # Start Thread
            self.stop_thread = False
            self.read_thread = threading.Thread(target=self.read_loop)
            self.read_thread.start()
            
        except Exception as e:
             self.console_textbox.insert("end", f"TCP Connection Error: {e}\n")

    def connect_ixxat(self):
        if can is None:
            self.console_textbox.insert("end", f"IXXAT unavailable: python-can import failed ({CAN_IMPORT_ERROR})\n")
            return

        try:
            channel = int(self.ixxat_channel_entry.get().strip())
        except Exception:
            self.console_textbox.insert("end", "IXXAT Connection Error: invalid channel. Use an integer (e.g. 0).\n")
            return

        bitrate = int(self.kbps_var.get()) * 1000
        self.console_textbox.insert("end", f"--- IXXAT connect request (channel={channel}, bitrate={bitrate}) ---\n")
        self.console_textbox.see("end")

        try:
            self.can_bus = self._open_ixxat_bus(channel, bitrate)

            self.is_connected = True
            self.update_ui_connected(f"Connected: IXXAT ch{channel} @ {int(self.kbps_var.get())} kbps")
            self.console_textbox.insert("end", f"--- IXXAT Connected (channel={channel}, bitrate={bitrate}) ---\n")

            self.stop_thread = False
            self.read_thread = threading.Thread(target=self.read_loop)
            self.read_thread.start()

        except Exception as e:
            self.console_textbox.insert("end", f"IXXAT Connection Error: {e}\n")

    def _open_ixxat_bus(self, channel, bitrate):
        try:
            return can.Bus(interface="ixxat", channel=channel, bitrate=bitrate)
        except TypeError:
            # Backward compatibility with older python-can versions
            return can.Bus(bustype="ixxat", channel=channel, bitrate=bitrate)

    def connect_kvaser(self):
        if can is None:
            self.console_textbox.insert("end", f"KVASER unavailable: python-can import failed ({CAN_IMPORT_ERROR})\n")
            return

        try:
            channel = int(self.kvaser_channel_entry.get().strip())
        except Exception:
            self.console_textbox.insert("end", "KVASER Connection Error: invalid channel. Use an integer (e.g. 0).\n")
            return

        bitrate = int(self.kbps_var.get()) * 1000
        self.console_textbox.insert("end", f"--- KVASER connect request (channel={channel}, bitrate={bitrate}) ---\n")
        self.console_textbox.see("end")

        try:
            self.can_bus = self._open_kvaser_bus(channel, bitrate)

            self.is_connected = True
            self.update_ui_connected(f"Connected: KVASER ch{channel} @ {int(self.kbps_var.get())} kbps")
            self.console_textbox.insert("end", f"--- KVASER Connected (channel={channel}, bitrate={bitrate}) ---\n")

            self.stop_thread = False
            self.read_thread = threading.Thread(target=self.read_loop)
            self.read_thread.start()

        except Exception as e:
            self.console_textbox.insert("end", f"KVASER Connection Error: {e}\n")

    def _open_kvaser_bus(self, channel, bitrate):
        try:
            return can.Bus(interface="kvaser", channel=channel, bitrate=bitrate)
        except TypeError:
            # Backward compatibility with older python-can versions
            return can.Bus(bustype="kvaser", channel=channel, bitrate=bitrate)

    def auto_detect_kvaser_speed(self):
        if self.connection_mode != "KVASER":
            self.console_textbox.insert("end", "Auto-speed is available only in KVASER mode.\n")
            return
        if can is None:
            self.console_textbox.insert("end", f"KVASER unavailable: python-can import failed ({CAN_IMPORT_ERROR})\n")
            return
        if self.is_connected:
            self.console_textbox.insert("end", "Disconnect first before auto speed detection.\n")
            return
        if self.is_detecting_speed:
            self.console_textbox.insert("end", "Auto speed detection already running...\n")
            return

        try:
            channel = int(self.kvaser_channel_entry.get().strip())
        except Exception:
            self.console_textbox.insert("end", "Auto speed error: invalid channel. Use an integer (e.g. 0).\n")
            return

        self.is_detecting_speed = True
        self.kvaser_autospeed_btn.configure(state="disabled", text="Detecting...")
        self.console_textbox.insert("end", f"--- KVASER Auto-Speed started (channel={channel}) ---\n")

        t = threading.Thread(target=self._auto_detect_kvaser_speed_worker, args=(channel,), daemon=True)
        t.start()

    def _auto_detect_kvaser_speed_worker(self, channel):
        candidates = [500, 250, 1000, 125, 100, 50, 20, 10]
        sniff_duration = 1.2
        passive_results = []

        # Phase 1: passive sniff for each bitrate
        for kbps in candidates:
            count = 0
            unique_ids = set()
            err_msg = None
            bus = None
            try:
                bus = self._open_kvaser_bus(channel, kbps * 1000)
                end_time = time.time() + sniff_duration
                while time.time() < end_time:
                    msg = bus.recv(timeout=0.05)
                    if msg is not None:
                        count += 1
                        unique_ids.add(msg.arbitration_id)
            except Exception as e:
                err_msg = str(e)
            finally:
                if bus is not None:
                    try:
                        bus.shutdown()
                    except Exception:
                        pass

            passive_results.append({
                "kbps": kbps,
                "count": count,
                "unique": len(unique_ids),
                "error": err_msg,
            })

        best = max(passive_results, key=lambda x: x["count"])

        # Phase 2: active probe fallback when bus is silent
        chosen_kbps = best["kbps"] if best["count"] > 0 else None
        active_reason = ""
        if chosen_kbps is None:
            for kbps in candidates:
                bus = None
                try:
                    bus = self._open_kvaser_bus(channel, kbps * 1000)
                    req_uds = can.Message(arbitration_id=0x7E0, data=[0x03, 0x19, 0x02, 0x09, 0x00, 0x00, 0x00, 0x00], is_extended_id=False)
                    req_kwp = can.Message(arbitration_id=0x7E0, data=[0x04, 0x18, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00], is_extended_id=False)
                    bus.send(req_uds)
                    time.sleep(0.05)
                    bus.send(req_kwp)

                    end_time = time.time() + 0.8
                    while time.time() < end_time:
                        msg = bus.recv(timeout=0.05)
                        if msg is None or len(msg.data) < 2:
                            continue
                        if not (0x7E8 <= msg.arbitration_id <= 0x7EF):
                            continue

                        sid = msg.data[1]
                        if sid in (0x59, 0x58):
                            chosen_kbps = kbps
                            active_reason = f"active probe matched SID {sid:02X} on {msg.arbitration_id:03X}"
                            break
                        if sid == 0x7F and len(msg.data) >= 3 and msg.data[2] in (0x19, 0x18):
                            chosen_kbps = kbps
                            active_reason = f"active probe matched negative response 7F {msg.data[2]:02X} on {msg.arbitration_id:03X}"
                            break

                    if chosen_kbps is not None:
                        break
                except Exception:
                    pass
                finally:
                    if bus is not None:
                        try:
                            bus.shutdown()
                        except Exception:
                            pass

        self.after(0, lambda: self._finish_kvaser_speed_detection(chosen_kbps, passive_results, active_reason))

    def _finish_kvaser_speed_detection(self, chosen_kbps, passive_results, active_reason):
        self.is_detecting_speed = False
        self.kvaser_autospeed_btn.configure(state="normal", text="Auto Detect Speed")

        self.console_textbox.insert("end", "--- KVASER Auto-Speed results ---\n")
        for row in passive_results:
            if row["error"]:
                self.console_textbox.insert("end", f"  {row['kbps']} kbps -> error: {row['error']}\n")
            else:
                self.console_textbox.insert("end", f"  {row['kbps']} kbps -> frames: {row['count']} | ids: {row['unique']}\n")

        if chosen_kbps is not None:
            self.kbps_var.set(str(chosen_kbps))
            self.console_textbox.insert("end", f"> Auto-selected bitrate: {chosen_kbps} kbps\n")
            if active_reason:
                self.console_textbox.insert("end", f"> Detection detail: {active_reason}\n")
            self.console_textbox.insert("end", "> Click CONNECT to use the detected speed.\n")
        else:
            self.console_textbox.insert("end", "> Could not determine bitrate automatically (bus may be silent/asleep).\n")
            self.console_textbox.insert("end", "> Wake the ECU and retry auto detection.\n")

        self.console_textbox.see("end")

    def read_kvaser(self):
        try:
            msg = self.can_bus.recv(timeout=0.05)
            if msg is None:
                return

            dlc = int(msg.dlc) if hasattr(msg, "dlc") else len(msg.data)
            data_commas = ",".join(f"{b:02X}" for b in list(msg.data)[:dlc])
            pkt = f"PKT:{msg.arbitration_id:X},{dlc},{data_commas}"
            self.process_packet(pkt)
        except Exception as e:
            if not self.stop_thread:
                print(f"KVASER Loop Error: {e}")
                self.stop_thread = True

    def auto_detect_ixxat_speed(self):
        if self.connection_mode != "IXXAT":
            self.console_textbox.insert("end", "Auto-speed is available only in IXXAT mode.\n")
            return
        if can is None:
            self.console_textbox.insert("end", f"IXXAT unavailable: python-can import failed ({CAN_IMPORT_ERROR})\n")
            return
        if self.is_connected:
            self.console_textbox.insert("end", "Disconnect first before auto speed detection.\n")
            return
        if self.is_detecting_speed:
            self.console_textbox.insert("end", "Auto speed detection already running...\n")
            return

        try:
            channel = int(self.ixxat_channel_entry.get().strip())
        except Exception:
            self.console_textbox.insert("end", "Auto speed error: invalid channel. Use an integer (e.g. 0).\n")
            return

        self.is_detecting_speed = True
        self.ixxat_autospeed_btn.configure(state="disabled", text="Detecting...")
        self.console_textbox.insert("end", f"--- IXXAT Auto-Speed started (channel={channel}) ---\n")

        t = threading.Thread(target=self._auto_detect_ixxat_speed_worker, args=(channel,), daemon=True)
        t.start()

    def _auto_detect_ixxat_speed_worker(self, channel):
        candidates = [500, 250, 1000, 125, 100, 50, 20, 10]
        sniff_duration = 1.2
        passive_results = []

        # Phase 1: passive sniff for each bitrate
        for kbps in candidates:
            count = 0
            unique_ids = set()
            err_msg = None
            bus = None
            try:
                bus = self._open_ixxat_bus(channel, kbps * 1000)
                end_time = time.time() + sniff_duration
                while time.time() < end_time:
                    msg = bus.recv(timeout=0.05)
                    if msg is not None:
                        count += 1
                        unique_ids.add(msg.arbitration_id)
            except Exception as e:
                err_msg = str(e)
            finally:
                if bus is not None:
                    try:
                        bus.shutdown()
                    except Exception:
                        pass

            passive_results.append({
                "kbps": kbps,
                "count": count,
                "unique": len(unique_ids),
                "error": err_msg,
            })

        best = max(passive_results, key=lambda x: x["count"])

        # Phase 2: active probe fallback when bus is silent
        chosen_kbps = best["kbps"] if best["count"] > 0 else None
        active_reason = ""
        if chosen_kbps is None:
            for kbps in candidates:
                bus = None
                try:
                    bus = self._open_ixxat_bus(channel, kbps * 1000)
                    # Probe with UDS and KWP requests; look for diagnostic-like response.
                    req_uds = can.Message(arbitration_id=0x7E0, data=[0x03, 0x19, 0x02, 0x09, 0x00, 0x00, 0x00, 0x00], is_extended_id=False)
                    req_kwp = can.Message(arbitration_id=0x7E0, data=[0x04, 0x18, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00], is_extended_id=False)
                    bus.send(req_uds)
                    time.sleep(0.05)
                    bus.send(req_kwp)

                    end_time = time.time() + 0.8
                    while time.time() < end_time:
                        msg = bus.recv(timeout=0.05)
                        if msg is None or len(msg.data) < 2:
                            continue
                        if not (0x7E8 <= msg.arbitration_id <= 0x7EF):
                            continue

                        sid = msg.data[1]
                        if sid in (0x59, 0x58):
                            chosen_kbps = kbps
                            active_reason = f"active probe matched SID {sid:02X} on {msg.arbitration_id:03X}"
                            break
                        if sid == 0x7F and len(msg.data) >= 3 and msg.data[2] in (0x19, 0x18):
                            chosen_kbps = kbps
                            active_reason = f"active probe matched negative response 7F {msg.data[2]:02X} on {msg.arbitration_id:03X}"
                            break

                    if chosen_kbps is not None:
                        break
                except Exception:
                    pass
                finally:
                    if bus is not None:
                        try:
                            bus.shutdown()
                        except Exception:
                            pass

        self.after(0, lambda: self._finish_ixxat_speed_detection(chosen_kbps, passive_results, active_reason))

    def _finish_ixxat_speed_detection(self, chosen_kbps, passive_results, active_reason):
        self.is_detecting_speed = False
        self.ixxat_autospeed_btn.configure(state="normal", text="Auto Detect Speed")

        self.console_textbox.insert("end", "--- IXXAT Auto-Speed results ---\n")
        for row in passive_results:
            if row["error"]:
                self.console_textbox.insert("end", f"  {row['kbps']} kbps -> error: {row['error']}\n")
            else:
                self.console_textbox.insert("end", f"  {row['kbps']} kbps -> frames: {row['count']} | ids: {row['unique']}\n")

        if chosen_kbps is not None:
            self.kbps_var.set(str(chosen_kbps))
            self.console_textbox.insert("end", f"> Auto-selected bitrate: {chosen_kbps} kbps\n")
            if active_reason:
                self.console_textbox.insert("end", f"> Detection detail: {active_reason}\n")
            self.console_textbox.insert("end", "> Click CONNECT to use the detected speed.\n")
        else:
            self.console_textbox.insert("end", "> Could not determine bitrate automatically (bus may be silent/asleep).\n")
            self.console_textbox.insert("end", "> Wake the ECU and retry auto detection.\n")

        self.console_textbox.see("end")

    def update_ui_connected(self, status_text):
        self.connect_btn.configure(text="DISCONNECT", fg_color="red")
        self.status_label.configure(text=status_text, text_color="green")
        self.mode_option.configure(state="disabled")
        self.port_option.configure(state="disabled")
        self.ip_entry.configure(state="disabled")
        self.tcp_port_entry.configure(state="disabled")
        self.ixxat_channel_entry.configure(state="disabled")
        self.ixxat_autospeed_btn.configure(state="disabled")
        self.kvaser_channel_entry.configure(state="disabled")
        self.kvaser_autospeed_btn.configure(state="disabled")

        # Auto-detect protocol on connection
        self.after(1000, self.start_protocol_detection)

    def start_protocol_detection(self):
        """ Attempts to identify if the connected vehicle is UDS or KWP2000 """
        if not self.is_connected: return
        # K-Line mode does not use CAN frames â€” skip CAN-based auto-detection
        if self.connection_mode == "AVR" and self.avr_bus_var.get() == "K-Line":
            self.console_textbox.insert("end", "--- K-Line mode: skipping CAN protocol auto-detection ---\n")
            return
        
        self.console_textbox.insert("end", f"--- Starting Protocol Auto-Detection ---\n")
        self.active_protocol = "AUTO"
        self.detecting_protocol = True
        self.dtc_status_label.configure(text="Detecting Protocol...")
        
        # 1. Send UDS Read DTC (19 02 09)
        # Newer (post-2010) models should respond 59 ...
        # Older (2009) models will respond 7F 19 11 (Not Supported)
        self.send_can_packet(0x7E0, 8, [0x03, 0x19, 0x02, 0x09, 0x00, 0x00, 0x00, 0x00])

        # Timeout/Fallback check after 1 second if no response decided
        def check_detection_timeout():
            if self.detecting_protocol and self.active_protocol == "AUTO":
                 self.console_textbox.insert("end", f"> No valid UDS response. Trying KWP...\n")
                 # Try KWP Read (18 00 FF 00)
                 # KWP might need 'Fast Init' or 'Start Session' first, but 2009 log showed 
                 # it responded to 18 directly (after wake-up traffic, maybe?)
                 # Let's try 18 directly.
                 self.send_can_packet(0x7E0, 8, [0x04, 0x18, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00])
                 
        self.after(1000, check_detection_timeout)


    def disconnect(self):
        self.stop_thread = True
        self.is_connected = False

        # Snapshot resources and null them out BEFORE updating UI so subsequent
        # calls (e.g. rapid re-connect) don't race with background cleanup.
        ser        = self.ser;         self.ser         = None
        tcp        = self.tcp_socket;  self.tcp_socket  = None
        can_bus    = self.can_bus;     self.can_bus     = None
        self._kline_active = False       # stop K-Line keepalive before releasing transport
        self._yds_link = None            # drop the YDS byte link with the transport
        self._yamaha_session = None
        self._kline_sniff_stop.set()      # stop passive sniff thread
        self._kline_sniff_active = False  # stop passive sniff thread
        avr        = self.avr_transport; self.avr_transport = None

        # Update UI immediately â€” do NOT block the main thread waiting for
        # port close (on Windows, pyserial's overlapped-IO close can take ~1 s).
        self.connect_btn.configure(text="CONNECT", fg_color="green")
        self.status_label.configure(text="Status: Disconnected", text_color="gray")

        self.console_textbox.insert("end", "--- Disconnected ---\n")
        self.mode_option.configure(state="normal")
        self.port_option.configure(state="normal")
        self.ip_entry.configure(state="normal")
        self.tcp_port_entry.configure(state="normal")
        self.ixxat_channel_entry.configure(state="normal")
        self.ixxat_autospeed_btn.configure(state="normal")

        # Close hardware resources in background so the UI stays responsive.
        def _close_resources():
            try:
                if ser:
                    ser.close()
            except Exception:
                pass
            try:
                if tcp:
                    tcp.close()
            except Exception:
                pass
            try:
                if can_bus:
                    can_bus.shutdown()
            except Exception:
                pass
            try:
                if avr:
                    avr.close()
            except Exception:
                pass

        threading.Thread(target=_close_resources, daemon=True).start()

    def set_can_speed(self, choice):
        """ Send command to change CAN Bitrate """
        if self.connection_mode == "AVR":
            # AVR CAN speed is managed by _on_avr_can_speed_change via avr_can_kbps_opt
            return

        if self.connection_mode in ("IXXAT", "KVASER"):
            self.console_textbox.insert("end", f"> Selected CAN bitrate: {choice} kbps ({self.connection_mode})\n")
            self.console_textbox.see("end")

            if self.is_connected:
                self.console_textbox.insert("end", f"> Reconnecting {self.connection_mode} with {choice} kbps...\n")
                self.console_textbox.see("end")

                # Preserve selected mode and reconnect using the new bitrate.
                current_mode = self.connection_mode
                self.disconnect()
                self.connection_mode = current_mode
                if current_mode == "IXXAT":
                    self.connect_ixxat()
                else:
                    self.connect_kvaser()
            return

        if self.is_connected:
            cmd = f"CAN_SPEED:{choice}"
            self.send_command(cmd)
            self.console_textbox.insert("end", f"> Sent: {cmd}\n")
            self.console_textbox.see("end")

    def send_can_packet(self, can_id, dlc, data_bytes):
        """ Sends a CAN packet via bridge (Serial/TCP) or IXXAT. """
        if self.is_replaying:
            return

        data_str_list = [f"{b:02X}" for b in data_bytes]
        # Pad with 00 if length is less than DLC, though usually the caller matches them
        while len(data_str_list) < dlc:
            data_str_list.append("00")

        if self.connection_mode == "AVR":
            if not self.avr_transport:
                self.console_textbox.insert("end", "Error sending CAN: AVR transport not connected.\n")
                return
            try:
                can_id_int = int(can_id)
                if can_id_int > 0x7FF:
                    self.console_textbox.insert("end", f"Error sending CAN: AVR supports only standard ID (got 0x{can_id_int:X}).\n")
                    return
                payload = bytes(int(x, 16) for x in data_str_list[:dlc])
                self.avr_transport.set_mode(InterfaceMode.CAN)
                self.avr_transport.can_tx_std(can_id_int, payload)
                self.console_textbox.insert("end", f"> TX(AVR): ID={can_id_int:X} Data={' '.join(data_str_list[:dlc])}\n")
            except Exception as e:
                self.console_textbox.insert("end", f"Error sending AVR frame: {e}\n")
                return

        elif self.connection_mode == "IXXAT":
            if not self.can_bus:
                self.console_textbox.insert("end", "Error sending CAN: IXXAT bus not connected.\n")
                return
            try:
                payload = [int(x, 16) for x in data_str_list[:dlc]]
                msg = can.Message(
                    arbitration_id=int(can_id),
                    data=payload,
                    is_extended_id=(int(can_id) > 0x7FF),
                )
                self.can_bus.send(msg)
                self.console_textbox.insert("end", f"> TX(IXXAT): ID={can_id:X} Data={' '.join(data_str_list[:dlc])}\n")
            except Exception as e:
                self.console_textbox.insert("end", f"Error sending IXXAT frame: {e}\n")
                return
        else:
            data_str = ",".join(data_str_list)
            cmd = f"TX:{can_id:X},{dlc},{data_str}"
            self.send_command(cmd)
            self.console_textbox.insert("end", f"> TX: ID={can_id:X} Data={data_str}\n")
        
        # Log TX Packet to CSV
        if self.is_recording and self.log_writer:
             try:
                 # Format same as RX for replay compatibility
                 # Note: Replay will just 'process' and show it, which is fine.
                 self.log_writer.writerow([datetime.now().strftime("%H:%M:%S.%f"), f"{can_id:X}", dlc, " ".join(data_str_list)])
             except: pass

    def send_brp_init(self, method):
        if not self.is_connected:
             self.console_textbox.insert("end", "Error: Not connected.\n")
             return

        if method == "Siemens":
             # Siemens KWP2000 Start Communication (Typical for Rotax 4-TEC)
             self.console_textbox.insert("end", "Sending BRP Siemens Init...\n")
             # KWP Start Comm: 81 (Format) 11 (Tgt) F1 (Src) 81 (StartComm) ... 
             # OR ISO-TP style on CAN: ID 7E0 Data 02 81 01 ...
             self.send_can_packet(0x7E0, 8, [0x02, 0x81, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
             
        elif method == "Bosch":
             # Bosch UDS Diagnostic Session Control
             self.console_textbox.insert("end", "Sending BRP Bosch Init...\n")
             self.send_can_packet(0x7E0, 8, [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])

    def read_ibr_full_info(self):
        """ Read IBR specific info using KWP 1A commands found in log """
        if not self.is_connected: return
        self.console_textbox.insert("end", "> Reading IBR Info (1A 90/91/B0)...\n")
        
        # 1. Request VIN (1A 90)
        self.send_can_packet(0x7B2, 8, [0x02, 0x1A, 0x90, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        # 2. Request Part Number (1A 91)
        self.after(200, lambda: self.send_can_packet(0x7B2, 8, [0x02, 0x1A, 0x91, 0x00, 0x00, 0x00, 0x00, 0x00]))
        
        # 3. Request Serial/SW (1A B0 - seen in log)
        self.after(400, lambda: self.send_can_packet(0x7B2, 8, [0x02, 0x1A, 0xB0, 0x00, 0x00, 0x00, 0x00, 0x00]))

    def send_yamaha_init(self):
        if not self.is_connected:
             self.console_textbox.insert("end", "Error: Not connected.\n")
             return

        if self.connection_mode == "AVR" and self.avr_bus_var.get() == "K-Line":
            threading.Thread(target=self._yamaha_kline_init_thread, daemon=True).start()
        else:
            # CAN path: Yamaha YDS uses UDS Extended Diagnostic Session on 0x7E0
            self.console_textbox.insert("end", "Sending Yamaha YDS (UDS) Init...\n")
            self.send_can_packet(0x7E0, 8, [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])

    def send_kawasaki_init(self):
        if not self.is_connected:
             self.console_textbox.insert("end", "Error: Not connected.\n")
             return

        if self.connection_mode == "AVR" and self.avr_bus_var.get() == "K-Line":
            threading.Thread(target=self._kawasaki_kline_init_thread, daemon=True).start()
        else:
            # Kawasaki KDS on CAN: KWP Start Comm + Diag Session
            self.console_textbox.insert("end", "Sending Kawasaki KDS Init Loop...\n")
            self.send_can_packet(0x7E0, 8, [0x02, 0x81, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
            self.console_textbox.insert("end", "> Sent KWP Start Comm (81 01)\n")
            self.after(500, lambda: self.send_can_packet(0x7E0, 8, [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00]))
            self.console_textbox.insert("end", "> Sent UDS/KWP Session Start (10 03) (Scheduled +500ms)\n")

    # ------------------------------------------------------------------
    # K-Line init sequences (run in daemon threads)
    # ------------------------------------------------------------------

    def _yamaha_tester_present_frame(self, ecu_addr: int, source: int = 0xF1) -> bytes:
        """TesterPresent KWP2000 com suppressPosRsp: 82 <ecu> <src> 3E 80 <cksum>."""
        body = [0x82, ecu_addr & 0xFF, source & 0xFF, 0x3E, 0x80]
        checksum = sum(body) & 0xFF
        return bytes(body + [checksum])

    def _kwp_frame(self, payload, ecu_addr=0x11, source=0xF1):
        """Monta um frame KWP2000 endereçado: <fmt> <tgt> <src> <payload...> <cksum>.

        O byte de formato usa o bit 7 e codifica o comprimento do payload
        (SID + dados), como no readDTCByStatus ja usado (0x84 ...).
        """
        payload = list(payload)
        frame = [0x80 | (len(payload) & 0x3F), ecu_addr & 0xFF, source & 0xFF] + payload
        return bytes(frame + [sum(frame) & 0xFF])

    def _yamaha_actuator_frame(self, code, control, value=None):
        """Frame de controlo de actuador (inputOutputControlByLocalIdentifier).

        :param code:    identificador do actuador (1..62, bloco 0x90 do SEItem)
        :param control: "on" (assumir controlo) ou "off" (devolver controlo ao ECU)
        :param value:   valor opcional (ex. posicao do ISC)

        O servico e configuravel porque o YDS nao o expoe em claro: o candidato
        padrao e o KWP2000 0x30; o SEByte sugere ainda um 0x32 proprietario.
        """
        service = int(getattr(self, "yamaha_actuator_service", 0x30)) & 0xFF
        if control == "off":
            payload = [service, code & 0xFF, 0x00]          # returnControlToECU
        else:
            iocp = int(getattr(self, "yamaha_actuator_iocp", 0x07)) & 0xFF
            payload = [service, code & 0xFF, iocp]
            if value is not None:
                payload.append(int(value) & 0xFF)
        return self._kwp_frame(payload)

    def _yamaha_kline_actuator(self, code, control, value=None):
        """Envia um comando de actuador por K-Line e registra a resposta."""
        t = self.avr_transport
        if t is None:
            self.yamaha_actuator_log("AVR indisponivel\n")
            return
        if not self._yamaha_yds_session_ready("actuador"):
            return
        if not self._kline_session_lock.acquire(blocking=False):
            self.yamaha_actuator_log("Sessao K-Line ocupada; tente de novo.\n")
            return
        try:
            frame = self._yamaha_actuator_frame(code, control, value)
            name = self._yamaha_actuator_name(code)
            self.yamaha_actuator_log(
                f"> {name} [{control}] TX: " + " ".join(f"{b:02X}" for b in frame) + "\n")
            # Sempre no gap de silencio: o ECM ocupa a linha continuamente.
            resp = self._yamaha_tx_request(frame, idle_ms=40, first_ms=300)

            if not resp:
                self.yamaha_actuator_log("  < sem resposta (confirme o servico/ID)\n")
            else:
                self.yamaha_actuator_log(
                    "< RX: " + " ".join(f"{b:02X}" for b in resp) + "\n")
                if getattr(self, "_yds_link", None) is not None:
                    self.yamaha_actuator_log(
                        f"  link YDS: {len(resp)} resposta(s) de 1 byte por byte enviado\n")
                    return
                payload = self._kwp_payload(resp)
                if payload and payload[0] == 0x7F:
                    nrc = payload[2] if len(payload) > 2 else 0
                    self.yamaha_actuator_log(f"  negativo (NRC {nrc:02X})\n")
                elif payload:
                    self.yamaha_actuator_log("  positivo\n")
        except Exception as exc:
            self.yamaha_actuator_log(f"erro: {exc}\n")
        finally:
            self._kline_session_lock.release()

    def _yamaha_actuator_list(self):
        return YAMAHA_YDS_DB.get("actuation_items") or []

    def _yamaha_actuator_name(self, code):
        for item in self._yamaha_actuator_list():
            if item.get("code") == code:
                return item.get("text", f"Atuador {code}")
        return f"Atuador {code}"

    def yamaha_actuator_log(self, text):
        widget = getattr(self, "yamaha_actuator_log_box", None)
        if widget is None:
            return
        try:
            widget.insert("end", text)
            widget.see("end")
        except Exception:
            pass

    def yamaha_actuator_activate(self):
        self._yamaha_actuator_run("on")

    def yamaha_actuator_deactivate(self):
        self._yamaha_actuator_run("off")

    def _yamaha_actuator_run(self, control):
        if not getattr(self, "is_connected", False):
            self.yamaha_actuator_log("Ligue-se primeiro.\n")
            return
        if not self._yamaha_in_kline_mode():
            self.yamaha_actuator_log(
                "Actuadores Yamaha requerem K-Line + protocolo Yamaha.\n")
            return
        try:
            code = int(self._yamaha_actuator_code_by_label.get(
                self.yamaha_actuator_var.get(), 0))
        except Exception:
            code = 0
        if not code:
            self.yamaha_actuator_log("Selecione um actuador.\n")
            return
        value = None
        raw_value = (self.yamaha_actuator_value_var.get() or "").strip()
        if raw_value:
            try:
                value = int(raw_value, 0)
            except ValueError:
                self.yamaha_actuator_log(f"valor invalido: {raw_value}\n")
                return
        threading.Thread(target=self._yamaha_kline_actuator,
                         args=(code, control, value), daemon=True).start()
        if control == "on":
            # O YDS devolve o controlo ao ECU automaticamente; replicamos isso
            # para nao deixar um injector/coil sob controlo do tester.
            timeout_ms = int(getattr(self, "yamaha_actuator_auto_off_s", 10) * 1000)
            self.yamaha_actuator_log(
                f"  (devolucao automatica do controlo em {timeout_ms // 1000}s)\n")
            self._yamaha_actuator_auto_off_id = self.after(
                timeout_ms,
                lambda c=code: self._yamaha_kline_actuator(c, "off"))

    # --- Poll keep-alive Yamaha -------------------------------------------
    # O ECM Yamaha ocupa a K-Line de forma praticamente continua (todas as
    # capturas tem gaps de 2-6 ms, nenhum acima de 8 ms). Nao ha "wakeup" a
    # fazer: o modulo esta activo enquanto a ignicao estiver ligada. O que o
    # YDS faz durante o Engine Monitor e pedir dados de forma continua, e e
    # essa actividade que mantem a sessao de diagnostico viva. Em vez de
    # TesterPresent (3E), replicamos isso com readDataByLocalIdentifier (21).

    def _yamaha_poll_frame(self, item=0x01):
        """readDataByLocalIdentifier 21 <item> -> Engine speed por omissao."""
        return self._kwp_frame([0x21, item & 0xFF])

    def _yamaha_tx_request(self, frame, idle_ms=40, first_ms=250,
                           inter_ms=6, max_bytes=28):
        """Envia no primeiro gap de silencio e le a resposta em bloco.

        Transmitir sem esperar por idle (idle_timeout_ms=0) colide com a
        transmissao continua do ECM e produz lixo no barramento.
        """
        link = getattr(self, "_yds_link", None)
        if link is not None:
            # Sessao YDS: o unico primitivo provado no YDS.exe e a troca de um
            # byte por vez (WriteFile so aparece em FUN_0046eeb0, 1 byte), por
            # isso um "frame" e enviado como sequencia de trocas com eco.
            try:
                return link.send_sequence(frame)
            except Exception as exc:
                self._avr_log(f"  YDS exchange falhou: {exc}\n")
                return []
        t = self.avr_transport
        if t is None:
            return []
        try:
            t.kline_tx_frame(frame, idle_timeout_ms=idle_ms)
        except Exception:
            for b in frame:
                t.kline_tx_byte(b)
        try:
            return list(t.kline_rx_bulk(first_timeout_ms=first_ms,
                                        inter_timeout_ms=inter_ms,
                                        max_bytes=max_bytes))
        except Exception:
            return []

    def _yamaha_poll_once(self, item=0x01):
        """Um ciclo de poll; devolve o payload KWP ou None se a sessao esta ocupada."""
        if not self._kline_session_lock.acquire(blocking=False):
            return None
        try:
            return self._kwp_payload(self._yamaha_tx_request(
                self._yamaha_poll_frame(item)))
        finally:
            self._kline_session_lock.release()

    def _yamaha_poll_loop(self):
        nrc_logged = False
        while getattr(self, "_yamaha_poll_active", False) and self.is_connected:
            link = getattr(self, "_yds_link", None)
            if link is not None:
                # Sessao YDS: manter vivo = continuar a trocar bytes de
                # identidade (0xFE), como o YDS faz no seu ciclo de poll.
                if link.ping(0xFE):
                    self._yamaha_poll_ok = getattr(self, "_yamaha_poll_ok", 0) + 1
                else:
                    self._yamaha_poll_fail = getattr(self, "_yamaha_poll_fail", 0) + 1
                time.sleep(max(0.05, getattr(self, "_yamaha_poll_interval", 0.5)))
                continue
            payload = self._yamaha_poll_once()
            if payload and payload[0] == 0x61:
                self._yamaha_poll_ok = getattr(self, "_yamaha_poll_ok", 0) + 1
            elif payload and payload[0] == 0x7F:
                self._yamaha_poll_fail = getattr(self, "_yamaha_poll_fail", 0) + 1
                if not nrc_logged:
                    nrc = payload[2] if len(payload) > 2 else 0
                    self._avr_log(
                        f"Yamaha poll: negativo (NRC {nrc:02X}) a 21 01\n")
                    nrc_logged = True
            else:
                self._yamaha_poll_fail = getattr(self, "_yamaha_poll_fail", 0) + 1
            time.sleep(max(0.05, getattr(self, "_yamaha_poll_interval", 0.5)))

    def toggle_yamaha_poll_keepalive(self):
        enabled = self.yamaha_poll_keepalive_var.get()
        if enabled:
            if not self._yamaha_in_kline_mode():
                self.yamaha_dtc_status_label.configure(
                    text="Poll keep-alive: so em K-Line + protocolo Yamaha")
                self.yamaha_poll_keepalive_var.set(False)
                return
            self._yamaha_poll_active = True
            self._yamaha_poll_ok = 0
            self._yamaha_poll_fail = 0
            threading.Thread(target=self._yamaha_poll_loop, daemon=True).start()
            mode = "0xFE (YDS)" if getattr(self, "_yds_link", None) else "21 01 (KWP)"
            self.yamaha_dtc_status_label.configure(
                text=f"Poll {mode} activo (mantem a sessao por actividade)")
        else:
            self._yamaha_poll_active = False
            self.yamaha_dtc_status_label.configure(
                text="Poll keep-alive parado | ok=%d falhas=%d"
                     % (getattr(self, "_yamaha_poll_ok", 0),
                        getattr(self, "_yamaha_poll_fail", 0)))

    def _yamaha_kline_init_thread(self, initial_status=None):
        """
        Yamaha YDS K-Line auto-init:
        wait for the ECM to release the K-Line high after ignition,
        then perform the physical-layer wakeup + ISO-14230 StartCommunication.

        Wakeup pattern (validated on oscilloscope):
          AVR firmware kline_yamaha_wakeup():
            H 47 ms â†’ L 95 ms â†’ H 95 ms â†’ L 95 ms â†’ H 8 ms

        StartCommunication frame (KWP fast-init style, ISO 14230-2):
          81 11 F1 81 04
          â””â”€ len=1 (service only)  tgt=0x11  src=0xF1  svc=0x81  chk

        Expected ECU response:
          C1 57 8F 86 E9 8A  (or similar preamble depending on ECU variant)
        """
        if not self._kline_session_lock.acquire(blocking=False):
            self._avr_log("Yamaha K-Line Init skipped: another K-Line session is already running\n")
            return
        try:
            # O sniff passivo le o mesmo transporte; tem de parar antes do
            # handshake, senao rouba o eco/resposta que o link YDS espera.
            if self._kline_sniff_active:
                self._avr_log("  sniff passivo parado para abrir o link YDS\n")
                self._kline_sniff_active = False
                self._kline_sniff_stop.set()
                time.sleep(0.15)
            self._yamaha_kline_init_inner(initial_status=initial_status)
        finally:
            self._kline_session_lock.release()

    def _yamaha_yds_session_ready(self, what):
        """No modo YDS, exige uma sessao aberta antes de enviar comandos.

        Sem isto, uma sessao falhada voltava ao caminho KWP e enviava tramas
        com comprimento/checksum num barramento que nao as usa.
        """
        check = getattr(self, "yamaha_yds_link_var", None)
        if check is None or not check.get():
            return True
        if getattr(self, "_yds_link", None) is not None:
            return True
        self.yamaha_dtc_status_label.configure(
            text=f"{what}: abra primeiro o link YDS")
        self.yamaha_actuator_log(
            f"{what}: link YDS nao esta aberto (ver o diagnostico no console)\n")
        return False

    def _yamaha_yds_open_session(self, transport):
        """Abertura no estilo YDS: 300 baud + 0x1C, 9600, handshake, escada.

        Reconstruido de FUN_004798f0 (ver docs/YDS_Protocol_Decompiled.md).
        """
        self._avr_log("=== Yamaha YDS link (9600 8N1) ===\n")
        if YdsByteLink is None:
            self._avr_log(f"  yds_protocol indisponivel: {YDS_IMPORT_ERROR}\n")
            return
        link = YdsByteLink(transport, log=self._avr_log)
        self._yds_link = link
        self._yamaha_session = None
        try:
            if transport.ser and transport.ser.is_open:
                transport.ser.reset_input_buffer()
            self._avr_log("  SET_MODE -> K-Line ... ")
            transport.set_mode(InterfaceMode.KLINE)
            self._avr_log("OK\n")
            silent_before = self._yamaha_bus_silent(transport, "antes do wake-up")
            session = link.open_session(probe=True)
        except Exception as exc:
            self._avr_log(f"  falha: {exc}\n")
            self._yds_link = None
            self._kline_active = False
            return

        if session.echo_required is None:
            self._avr_log("  eco: nao determinado\n")
        else:
            self._avr_log("  eco: " + (
                "presente (cada byte e devolvido antes da resposta)"
                if session.echo_required
                else "ausente (o primeiro byte recebido ja e a resposta)") + "\n")

        if not session.ok:
            self._avr_log(f"< YDS link sem sessao: {session.detail}\n")
            self._yamaha_yds_explain_failure(transport, link, silent_before)
            self._yds_link = None
            self._kline_active = False
            return

        variant_name = "A" if session.variant == 0 else "B"
        self._avr_log(
            f"  variante {variant_name} (0xE5 -> 0x{'EF' if session.variant == 0 else 'ED'})\n")
        self._avr_log(
            f"  identidade: FE=0x{session.ident_fe:02X} FF=0x{session.ident_ff:02X}\n")
        self._avr_log(
            f"  endereco do modulo 0x{session.module_address:02X} "
            f"-> resposta 0x{session.module_ident:02X}\n")
        self._avr_log("Yamaha YDS link OK - modulo a responder\n")
        self._yamaha_session = session
        self._kline_active = True
        self._kline_proto = "yamaha-yds"

    def _yamaha_bus_silent(self, transport, when):
        """Amostra a K-Line e diz se nao ha trafego nenhum."""
        try:
            status = transport.kline_get_status(150)
        except Exception as exc:
            self._avr_log(f"  K-Line {when}: nao foi possivel amostrar ({exc})\n")
            return None
        self._avr_log(
            f"  K-Line {when}: {status.state_name} high={status.high_ms}ms "
            f"low={status.low_ms}ms edges={status.edge_count} rx={status.rx_byte_count}\n")
        if status.edge_count == 0 and status.rx_byte_count == 0:
            return True
        return False

    def _yamaha_yds_explain_failure(self, transport, link, silent_before):
        """Traduz a falha do handshake num diagnostico accionavel."""
        silent_after = self._yamaha_bus_silent(transport, "depois do wake-up")
        echo = link.echo_mode

        # O eco e a evidencia mais forte: prova que o byte saiu para o barramento
        # e voltou. Vale mais do que a amostragem de edges, que so ve a linha
        # enquanto o AVR nao esta a transmitir.
        if echo is True:
            self._avr_log(
                "  DIAGNOSTICO: cada byte enviado voltou em eco — o AVR, o nivel\n"
                "  electrico e o caminho de regresso funcionam. O modulo e que nao\n"
                "  respondeu. Causas, por ordem de probabilidade:\n"
                "   1. modulo sem alimentacao ou ignicao desligada;\n"
                "   2. pino de diagnostico errado na ficha (K-Line vs +12V vs massa);\n"
                "   3. este modelo nao usa esta sequencia de abertura.\n"
                "  O elo fisico esta bom: o problema e do lado do veiculo.\n")
            return

        if echo is False:
            self._avr_log(
                "  DIAGNOSTICO: o primeiro byte recebido nao era o eco do enviado.\n"
                "  Ha actividade no barramento mas nao a esperada — provavelmente\n"
                "  baud diferente de 9600 neste modelo. Tentar 10400 ou 15625.\n")
            return

        if silent_before and silent_after:
            self._avr_log(
                "  DIAGNOSTICO: o barramento K-Line esta em repouso (0 transicoes,\n"
                "  0 bytes) antes e depois do wake-up, e nem o proprio byte enviado\n"
                "  voltou. Isso aponta para o caminho fisico, nao para o protocolo.\n"
                "  Verificar, por esta ordem:\n"
                "   1. fio RX do AVR no pino correcto da ficha de diagnostico;\n"
                "   2. massa comum entre o AVR e o veiculo;\n"
                "   3. ignicao ligada e painel/ECU alimentados;\n"
                "   4. nivel electrico: a K-Line em repouso fica a ~12 V, nao a 5 V.\n"
                "  Confirmacao rapida: 'K-Line Sniff (passivo)' com a ignicao ligada.\n"
                "  Se nao aparecer um unico byte, o problema e fisico.\n")
            return

        if silent_after:
            self._avr_log(
                "  DIAGNOSTICO: sem eco e sem transicoes durante o wake-up.\n"
                "  O AVR nao esta a ver a linha. Verificar o fio RX e a massa.\n")
            return

        self._avr_log(
            "  DIAGNOSTICO: houve transicoes na linha mas o handshake nao fechou.\n"
            "  Guardar o log do 'K-Line Sniff (passivo)' para analise.\n")

    def _yamaha_kline_init_inner(self, initial_status=None):
        t = self.avr_transport
        if t is None:
            return
        _yds_chk = getattr(self, "yamaha_yds_link_var", None)
        if _yds_chk is not None and _yds_chk.get():
            self._yamaha_yds_open_session(t)
            return
        baud = int(self.avr_kline_baud_var.get())
        self._avr_log("=== Yamaha K-Line Init ===\n")
        try:
            # 1. Ensure K-Line mode + baud rate
            self._avr_log(f"  SET_MODE â†’ K-Line ... ")
            # Flush stale bytes left by any previous failed/timed-out transaction
            if t.ser and t.ser.is_open:
                t.ser.reset_input_buffer()
            t.set_mode(InterfaceMode.KLINE)
            self._avr_log("OK\n")
            self._avr_log(f"  KLINE_SET_BAUD {baud} ... ")
            t.kline_set_baud(baud)
            self._avr_log("OK\n")

            if initial_status is None:
                try:
                    initial_status = t.kline_get_status(120)
                    self._avr_log(f"  KLINE_GET_STATUS {self._format_kline_status(initial_status)}\n")
                except Exception as e:
                    self._avr_log(f"  KLINE_GET_STATUS falhou: {e}\n")

            if initial_status is not None and initial_status.is_communicating:
                self._avr_log("  K-Line ja esta comunicando; pulando wakeup/init para nao interferir no barramento.\n")
                return

            if initial_status is not None and initial_status.is_high:
                self._avr_log("  K-Line alta estavel detectada; enviando StartCommunication.\n")
            else:
                # 2. Arm while the line is low, then wait for the real ignition rise.
                self._avr_log("  Aguardando borda de subida da K-Line (baixa->alta, timeout=30s, alta estavel=20ms) ... ")
                if not t.kline_wait_high(timeout_ms=30000, stable_ms=20):
                    self._avr_log("TIMEOUT\n")
                    self._avr_log("< A K-Line nao fez a transicao baixa->alta. Arme antes de ligar a ignicao e tente novamente.\n")
                    return
                self._avr_log("OK\n")
                time.sleep(0.010)

            # 3. StartCommunication: 81 11 F1 81 04
            # ISO 14230 fast-init exige o pedido enviado como UM frame continuo:
            # byte-a-byte via USB cria gaps de varios ms e o ECU aborta o frame.
            init_seq = [0x81, 0x11, 0xF1, 0x81, 0x04]
            try:
                t.kline_tx_frame(bytes(init_seq), idle_timeout_ms=0)
            except Exception as _tx_e:
                self._avr_log(f"  tx_frame indisponivel ({_tx_e}); fallback byte-a-byte\n")
                for b in init_seq:
                    t.kline_tx_byte(b)
            self._avr_log(f"> TX: {' '.join(f'{b:02X}' for b in init_seq)}\n")
            self._kline_record("TX", init_seq)

            # 4. Ler a resposta de uma vez. Byte-a-byte estoura o buffer de 1 byte
            # do AVR e perde bytes -> era a origem do "ruido".
            try:
                raw_response = list(t.kline_rx_bulk(
                    first_timeout_ms=300, inter_timeout_ms=10, max_bytes=12))
            except Exception as _rx_e:
                self._avr_log(f"  rx_bulk indisponivel ({_rx_e}); fallback byte-a-byte\n")
                raw_response = []
                for _ in range(12):
                    rx = t.kline_rx_byte(200)
                    if rx is None:
                        break
                    raw_response.append(rx)

            if raw_response:
                self._avr_log(f"< RX: {' '.join(f'{b:02X}' for b in raw_response)}\n")
                self._kline_record("RX", raw_response)
                # Strip leading 0xFE/0xFF preamble bytes to isolate ECU payload
                response = list(raw_response)
                while response and response[0] in (0xFE, 0xFF):
                    response.pop(0)
                if response:
                    self._avr_log(f"  ECU payload: {' '.join(f'{b:02X}' for b in response)}\n")
                self._avr_log("Yamaha K-Line Init OK â€” ECU responded\n")
                self._kline_active = True
                self._kline_proto = "yamaha"
                # Sessao KWP2000 cai se o tester nao enviar TesterPresent dentro
                # de P3. Sem keepalive a ligacao morre ao fim do idle do ECU
                # (~30 s) -- era o sintoma observado.
                if self.kwp_keep_alive_var.get():
                    try:
                        _ka_frame = self._yamaha_tester_present_frame(0x11)
                        t.kline_keepalive_start(_ka_frame, interval_ms=1500)
                        self._avr_log(
                            "  Keepalive no firmware: "
                            f"{' '.join(f'{b:02X}' for b in _ka_frame)} a cada 1.5s\n")
                    except Exception as _ka_e:
                        self._avr_log(f"  Keepalive firmware nao suportado ({_ka_e}); sem keepalive\n")
                else:
                    self._avr_log("  Keepalive DESATIVADO: a sessao cai no idle do ECU.\n")
            else:
                self._avr_log("< No ECU response (check wiring / baud rate)\n")

        except Exception as e:
            self._avr_log(f"Yamaha K-Line Init Error: {e}\n")

    def _kawasaki_kline_init_thread(self):
        """
        Kawasaki KDS K-Line wakeup + KWP2000 StartCommunication.

        Uses the same physical wakeup pattern as Yamaha (same AVR command),
        then sends the KWP StartCommunication header targeting ECU address 0x13.

        StartCommunication frame:
          C1 13 F1 81 46
          â””â”€ FMT=C1 (len=1, functional)  tgt=0x13  src=0xF1  svc=0x81  chk
        """
        if not self._kline_session_lock.acquire(blocking=False):
            self._avr_log("Kawasaki K-Line Init skipped: another K-Line session is already running\n")
            return
        try:
            self._kawasaki_kline_init_inner()
        finally:
            self._kline_session_lock.release()

    def _kawasaki_kline_init_inner(self):
        t = self.avr_transport
        if t is None:
            return
        baud = int(self.avr_kline_baud_var.get())
        self._avr_log("=== Kawasaki K-Line Init ===\n")
        try:
            self._avr_log(f"  SET_MODE â†’ K-Line ... ")
            # Flush stale bytes from any previous failed/timed-out transaction
            if t.ser and t.ser.is_open:
                t.ser.reset_input_buffer()
            t.set_mode(InterfaceMode.KLINE)
            self._avr_log("OK\n")
            self._avr_log(f"  KLINE_SET_BAUD {baud} ... ")
            t.kline_set_baud(baud)
            self._avr_log("OK\n")

            # StartCommunication: C1 13 F1 81 46
            init_seq = [0xC1, 0x13, 0xF1, 0x81, 0x46]
            for b in init_seq:
                t.kline_tx_byte(b)
            self._avr_log(f"> TX: {' '.join(f'{b:02X}' for b in init_seq)}\n")
            self._kline_record("TX", init_seq)

            raw_response = []
            for _ in range(12):
                rx = t.kline_rx_byte(200)
                if rx is None:
                    break
                raw_response.append(rx)

            if raw_response:
                self._avr_log(f"< RX: {' '.join(f'{b:02X}' for b in raw_response)}\n")
                self._kline_record("RX", raw_response)
                response = list(raw_response)
                while response and response[0] in (0xFE, 0xFF):
                    response.pop(0)
                if response:
                    self._avr_log(f"  ECU payload: {' '.join(f'{b:02X}' for b in response)}\n")
                self._avr_log("Kawasaki K-Line Init OK â€” ECU responded\n")
                self._kline_active = True
                self._kline_proto = "kawasaki"
                if self.kwp_keep_alive_var.get():
                    try:
                        _ka_frame = bytes([0x82, 0x13, 0xF1, 0x3E, 0x80, 0x44])
                        t.kline_keepalive_start(_ka_frame, interval_ms=1500)
                        self._avr_log("  Keepalive iniciado no firmware (TesterPresent a cada 1.5s)\n")
                    except Exception as _ka_e:
                        self._avr_log(f"  Keepalive firmware nao suportado ({_ka_e}); sem keepalive\n")
                else:
                    self._avr_log("  Keepalive desativado (marque Keep-Alive para manter sessao)\n")
            else:
                self._avr_log("< No ECU response\n")

        except Exception as e:
            self._avr_log(f"Kawasaki K-Line Init Error: {e}\n")

    def send_ecm_actuation(self, loc_id, mask):
        """ Send KWP/UDS Actuator Test Command to ECM (0x7E0) """
        if not self.is_connected: return
        self.console_textbox.insert("end", f"> Actuator Test: ID {loc_id:02X} Mask {mask:02X}\n")
        # Command: 30 [LocID] 07 [Mask]
        # Payload: 04 30 LocID 07 Mask 00 00 00
        self.send_can_packet(0x7E0, 8, [0x04, 0x30, loc_id, 0x07, mask, 0x00, 0x00, 0x00])
        self.console_textbox.see("end")

    def send_cluster_actuation(self, did_h, did_l, param1, param2):
        """ Send Actuator Test to Cluster (0x7B3) - Service 2F """
        if not self.is_connected: return
        self.console_textbox.insert("end", f"> Cluster Test: DID {did_h:02X}{did_l:02X}\n")
        # Payload: 05 2F DID_H DID_L P1 P2 00 00
        self.send_can_packet(0x7B3, 8, [0x05, 0x2F, did_h, did_l, param1, param2, 0x00, 0x00])
        self.console_textbox.see("end")

    def read_module_info(self, req_id):
        """ General Info Read (VIN/Part) using KWP 1A """
        # Only use this for default devices if not specific
        if not self.is_connected: return
        self.console_textbox.insert("end", f"> Reading Info from {req_id:X} (1A 90/80)\n")
        # Request VIN (1A 90)
        self.send_can_packet(req_id, 8, [0x02, 0x1A, 0x90, 0x00, 0x00, 0x00, 0x00, 0x00])
        # Request Part Num (1A 80) - Schedule slightly later
        self.after(200, lambda: self.send_can_packet(req_id, 8, [0x02, 0x1A, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00]))

    def read_gps_info(self):
        """ Specific Routine for GPS (0x7A6 -> 0x7AE) UDS Reading - Hardware IDs """
        if not self.is_connected: return
        self.console_textbox.insert("end", "> Reading GPS Info (0x7A6)...\n")
        
        # 1. Part Number (F18E) -> 278003899
        self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xF1, 0x8E, 0x00, 0x00, 0x00, 0x00])

        # 2. Calibration (F1F0) -> 1001131822...
        self.after(200, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xF1, 0xF0, 0x00, 0x00, 0x00, 0x00]))
        
        # 3. HW Num (F192) -> 1001133301
        self.after(400, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xF1, 0x92, 0x00, 0x00, 0x00, 0x00]))
        
        # 4. Serial / Other (F18C or F102) -> 899...
        self.after(600, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xF1, 0x8C, 0x00, 0x00, 0x00, 0x00]))

    def read_gps_position(self):
        """ Read GPS Position Data (Latitude, Longitude, Altitude) from 0x7A6 """
        if not self.is_connected: return
        self.console_textbox.insert("end", "> Reading GPS Position (0x7A6)...\n")
        
        # DIDs extracted from diagnostic logs - based on reverse-eng from EDB
        # 0xCF05 = Altitude (meters, signed int16)
        # 0xCF06 = Latitude (degrees)
        # 0xCF07 = Longitude (degrees)
        
        self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x05, 0x00, 0x00, 0x00, 0x00])
        self.after(200, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x06, 0x00, 0x00, 0x00, 0x00]))
        self.after(400, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x07, 0x00, 0x00, 0x00, 0x00]))

    def read_gps_motion(self):
        """ Read GPS Motion Data (Speed, Course, Satellites, Fix Status) """
        if not self.is_connected: return
        self.console_textbox.insert("end", "> Reading GPS Motion (0x7A6)...\n")
        
        # 0xCF00 = GPS Fix Status (enum: 0=NoFix, 1=2D, 2=3D, etc.)
        # 0xCF01 = GPS Satellites in view/used
        # 0xCF03 = HDOP (Horizontal Dilution of Precision)
        # 0xCF08 = Speed over ground
        # 0xCF0B = Course/Heading
        
        self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x00, 0x00, 0x00, 0x00, 0x00])
        self.after(200, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x01, 0x00, 0x00, 0x00, 0x00]))
        self.after(400, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x03, 0x00, 0x00, 0x00, 0x00]))
        self.after(600, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x08, 0x00, 0x00, 0x00, 0x00]))
        self.after(800, lambda: self.send_can_packet(0x7A6, 8, [0x03, 0x22, 0xCF, 0x0B, 0x00, 0x00, 0x00, 0x00]))

    def read_gps_all(self):
        """ Read all GPS data: Hardware IDs + Position + Motion """
        if not self.is_connected: return
        self.console_textbox.insert("end", "> Reading ALL GPS Data...\n")
        
        # Chain all three read operations with delays
        delay = 0
        
        # Hardware IDs
        for did_pair, offset in [(0xF18E, 0), (0xF1F0, 200), (0xF192, 400), (0xF18C, 600)]:
            did_h = (did_pair >> 8) & 0xFF
            did_l = did_pair & 0xFF
            self.after(delay + offset, lambda dh=did_h, dl=did_l: self.send_can_packet(0x7A6, 8, [0x03, 0x22, dh, dl, 0x00, 0x00, 0x00, 0x00]))
        
        # Position Data
        for did_pair, offset in [(0xCF05, 1200), (0xCF06, 1400), (0xCF07, 1600)]:
            did_h = (did_pair >> 8) & 0xFF
            did_l = did_pair & 0xFF
            self.after(delay + offset, lambda dh=did_h, dl=did_l: self.send_can_packet(0x7A6, 8, [0x03, 0x22, dh, dl, 0x00, 0x00, 0x00, 0x00]))
        
        # Motion Data
        for did_pair, offset in [(0xCF00, 2000), (0xCF01, 2200), (0xCF03, 2400), (0xCF08, 2600), (0xCF0B, 2800)]:
            did_h = (did_pair >> 8) & 0xFF
            did_l = did_pair & 0xFF
            self.after(delay + offset, lambda dh=did_h, dl=did_l: self.send_can_packet(0x7A6, 8, [0x03, 0x22, dh, dl, 0x00, 0x00, 0x00, 0x00]))

    def read_brp_dtc(self):
        """ Poll all known modules for DTCs (UDS 19 02 FF / KWP 18 00 FF) """
        if not self.is_connected: return
        
        self.dtc_status_label.configure(text="Requesting Codes...")
        
        # Reset visual state of all rows before new scan
        for code, widgets in self.dtc_rows.items():
            widgets["frame"].configure(fg_color="#2b2b2b")
            widgets["stat"].configure(text="--", text_color="gray")
            widgets["cod"].configure(text_color="gray")
            if "mod" in widgets:
                widgets["mod"].configure(text="--", text_color="#666")
            widgets["desc"].configure(text_color="gray")
            widgets["sol"].configure(text_color="#666")
            widgets["active"] = False
        
        is_kwp = (self.active_protocol == "KWP")
        
        if is_kwp:
            # KWP: Start session then read DTCs â€” only ECM responds
            self.console_textbox.insert("end", "> KWP - Start Session (10 03) â†’ Read DTC (18 00 FF)\n")
            self.send_can_packet(0x7E0, 8, [0x02, 0x10, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
            self.after(200, lambda: self.send_can_packet(0x7E0, 8, [0x04, 0x18, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00]))
        else:
            # UDS: poll every module from EDB with 19 02 FF, spaced 150 ms
            poll = MODULE_DTC_POLL_LIST if MODULE_DTC_POLL_LIST else [(0x7E0, "ECM")]
            self.console_textbox.insert("end", f"> UDS - Polling {len(poll)} module(s) for DTCs...\n")
            for idx, (req_id, mod_name) in enumerate(poll):
                delay = idx * 150
                self.after(delay, lambda rid=req_id, mn=mod_name: (
                    self.console_textbox.insert("end", f">   [{mn}] â†’ 0x{rid:03X}  19 02 FF\n"),
                    self.send_can_packet(rid, 8, [0x03, 0x19, 0x02, 0xFF, 0x00, 0x00, 0x00, 0x00])
                ))

    def clear_brp_dtc(self):
        """ Send Clear DTC commands based on active protocol """
        if not self.is_connected: return
        
        self.dtc_status_label.configure(text="Clearing Codes...")
        
        is_kwp = (self.active_protocol == "KWP")
        
        if is_kwp:
             self.console_textbox.insert("end", "> Protocol: KWP - Sending Clear DTC (14 FF 00)...\n")
             self.send_can_packet(0x7E0, 8, [0x03, 0x14, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00])
        else:
             # UDS Clear Diag Info (Service 14) - Group FF FF FF (All)
             self.console_textbox.insert("end", "> Protocol: UDS - Sending Clear DTC (14 FF FF FF)...\n")
             self.send_can_packet(0x7E0, 8, [0x04, 0x14, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00])

        self.dtc_status_label.configure(text="Clear Command Sent.")

    def parse_uds_response(self, payload, can_id=0):
        if not payload: return "Empty Payload"
        sid = payload[0]

        # 0x62 ReadDataByIdentifier positiva — VIN no DID F190
        if sid == 0x62 and len(payload) >= 4 and payload[1] == 0xF1 and payload[2] == 0x90:
            vin = "".join(chr(b) for b in payload[3:] if 32 <= b < 127).strip()
            if len(vin) >= 6:
                self.set_vehicle_vin(vin)
            return f"VIN: {vin}"

        # --- Protocol Auto-Detection Handler ---
        if self.detecting_protocol:
            # Check for Positive UDS Response (59)
            if sid == 0x59:
                self.active_protocol = "UDS"
                self.detecting_protocol = False
                self.console_textbox.insert("end", f"> Protocol Auto-Detected: UDS (Resp {sid:02X})\n")

                return "Protocol Detected: UDS"
            
            # Check for Negative Response to Service 19 -> Likely KWP
            # 7F 19 11 (Service Rejected) or 7F 19 12 (Subfunc not supported)
            elif sid == 0x7F and len(payload) >= 2 and payload[1] == 0x19:
                self.active_protocol = "KWP"
                self.detecting_protocol = False
                self.console_textbox.insert("end", f"> Protocol Auto-Detected: KWP (Resp 7F 19, Service Rejected)\n")
                return "Protocol Detected: KWP (via 7F 19)"
            
            # Check for Positive KWP Reponse (58)
            elif sid == 0x58:
                self.active_protocol = "KWP"
                self.detecting_protocol = False
                self.console_textbox.insert("end", f"> Protocol Auto-Detected: KWP (Resp {sid:02X})\n")
                return "Protocol Detected: KWP"

        # 0x62: UDS ReadDataByIdentifier Response
        if sid == 0x62:
            if len(payload) < 3: return "UDS Read Short"
            did = (payload[1] << 8) | payload[2]
            data = payload[3:]
            
            # Try ASCII Decode
            ascii_val = "".join([chr(b) for b in data if 31 < b < 127])
            
            # --- GPS (0x7AE) Routing ---
            if can_id == 0x7AE:
                # Hardware IDs (ASCII)
                if did == 0xF18E: self.gps_labels["part"].configure(text=f"Part #: {ascii_val}")
                elif did == 0xF1F0 or did == 0xF188: self.gps_labels["cal"].configure(text=f"Calib #: {ascii_val}")
                elif did == 0xF192: self.gps_labels["hw"].configure(text=f"HW #: {ascii_val}")
                elif did == 0xF18C or did == 0xF102: self.gps_labels["ser"].configure(text=f"Serial #: {ascii_val}")
                
                # Position DIDs (numerical)
                elif did == 0xCF05:
                    # Altitude (signed int16)
                    if len(data) >= 2:
                        alt_raw = (data[0] << 8) | data[1]
                        alt = alt_raw if alt_raw < 32768 else alt_raw - 65536  # Sign extend
                        self.gps_labels["alt"].configure(text=f"Altitude: {alt} m")
                        return f"GPS Altitude: {alt} m"
                    
                elif did == 0xCF06:
                    # Latitude (degrees, may be fractional)
                    if len(data) >= 1:
                        lat_deg = data[0]
                        lat_frac = data[1] if len(data) > 1 else 0
                        lat_str = f"{lat_deg}.{lat_frac:02d}Â°"
                        self.gps_labels["lat"].configure(text=f"Latitude: {lat_str}")
                        return f"GPS Latitude: {lat_str}"
                    
                elif did == 0xCF07:
                    # Longitude (degrees, may be fractional)
                    if len(data) >= 1:
                        lon_deg = data[0]
                        lon_frac = data[1] if len(data) > 1 else 0
                        lon_str = f"{lon_deg}.{lon_frac:02d}Â°"
                        self.gps_labels["lon"].configure(text=f"Longitude: {lon_str}")
                        return f"GPS Longitude: {lon_str}"
                
                # Motion DIDs (numerical)
                elif did == 0xCF00:
                    # GPS Fix Status
                    if len(data) >= 1:
                        fix_status = data[0]
                        fix_names = {0: "No Fix", 1: "2D", 2: "3D", 3: "DGPS", 4: "RTK"}
                        fix_str = fix_names.get(fix_status, f"Unknown ({fix_status})")
                        self.gps_labels["fix"].configure(text=f"Fix Status: {fix_str}")
                        return f"GPS Fix: {fix_str}"
                
                elif did == 0xCF01:
                    # Satellites
                    if len(data) >= 1:
                        sats = data[0]
                        self.gps_labels["sats"].configure(text=f"Satelites: {sats}")
                        return f"GPS Satellites: {sats}"
                
                elif did == 0xCF03:
                    # HDOP
                    if len(data) >= 2:
                        hdop_raw = (data[0] << 8) | data[1]
                        hdop = hdop_raw / 100.0  # 0.01 resolution
                        self.gps_labels["hdop"].configure(text=f"H.DOP: {hdop:.2f}")
                        return f"GPS HDOP: {hdop:.2f}"
                
                elif did == 0xCF08:
                    # Speed
                    if len(data) >= 2:
                        speed_raw = (data[0] << 8) | data[1]
                        speed_ms = speed_raw / 100.0  # 0.01 m/s resolution
                        speed_kmh = speed_ms * 3.6
                        self.gps_labels["speed"].configure(text=f"Velocidade: {speed_kmh:.1f} km/h")
                        return f"GPS Speed: {speed_ms:.2f} m/s ({speed_kmh:.1f} km/h)"
                
                elif did == 0xCF0B:
                    # Course/Heading
                    if len(data) >= 2:
                        course_raw = (data[0] << 8) | data[1]
                        course = course_raw / 100.0  # 0.01 degree resolution
                        self.gps_labels["course"].configure(text=f"Direcao: {course:.1f}Â°")
                        return f"GPS Course: {course:.1f}Â°"
                
                return f"GPS DID {did:04X}: {ascii_val}"
            
            # --- Cluster / Others ---
            return f"UDS Read DID {did:04X}: {ascii_val}"
        
        # 0x59: UDS Read DTC Info Response
        if sid == 0x59:
             # Fmt: [59] [Sub] [Mask] [DTC1_H] [DTC1_M] [DTC1_L] [St] [DTC2...]
             num_bytes = len(payload)
             start_idx = 3 # Skip 59 02 Mask
             dtcs = []
             
             i = start_idx
             while i + 3 < num_bytes:
                 dtc_h = payload[i]
                 dtc_m = payload[i+1]
                 dtc_l = payload[i+2]
                 status = payload[i+3]
                 
                 # Convert to P-Code
                 type_code = (dtc_h & 0xC0) >> 6
                 prefix = {0: "P", 1: "C", 2: "B", 3: "U"}[type_code]
                 
                 # Create Hex String (stripping type bits from High Byte)
                 code_hex = f"{(dtc_h & 0x3F):02X}{dtc_m:02X}{dtc_l:02X}"
                 
                 code_str = f"{prefix}{code_hex}"
                 
                 # Look up description in BRP_DTC_DB
                 desc_str = lookup_dtc_desc(BRP_DTC_DB, code_str, f"Unknown Fault (St:{status:02X})")
                 
                 # Status Decoding (Simple)
                 # Bit 0: testFailed (Active)
                 # Bit 3: confirmedDTC (Stored)
                 is_active = (status & 0x01) != 0

                 # Identify source module by response CAN ID
                 mod_name = MODULE_RESP_NAME_MAP.get(can_id, f"0x{can_id:03X}" if can_id else "?")
                 # Conta o ECU mesmo quando responde "sem falhas": o conjunto de
                 # modulos presentes e o que identifica o modelo.
                 self._note_module(mod_name)
                 
                 dtc_obj = {
                     'code': code_str,
                     'is_active': is_active,
                     'desc': desc_str,
                     'module': mod_name,
                     'count': 1 # UDS usually doesn't send count in this mode
                 }
                 dtcs.append(dtc_obj)
                 i += 4
             
             self.update_dtc_table(dtcs)
             return f"Found {len(dtcs)} UDS DTCs"

        # 0x58: KWP Read DTC Response (or Standard KWP)
        # 0xC4: BRP Proprietary Response (observed in logs)
        elif sid == 0x58 or sid == 0xC4:
            # Yamaha K-Line: os codigos sao numericos, nunca P-code.
            if sid == 0x58 and self._yamaha_in_kline_mode():
                return self.parse_yamaha_kwp_dtc(list(payload))

            # Fmt 58: [58] [Count] [DTC1_H] [DTC1_L] [St] ...
            # Fmt C4: [C4] [CD] [?] [?] [Count] [DTC1_H] [DTC1_L] [St] ... (Observed)
            # LOG: c4 cd 00 0b 03 04 2d 00 ...
            
            dtcs = []
            i = 0
            
            if sid == 0xC4:
                # BRP Wrapper: C4 CD 00 0B 03 ...
                # Skip C4 CD and length bytes until Count?
                # Based on log: C4 CD 00 0B 03. 03 is count.
                if len(payload) < 5: return "BRP DTC Short"
                count = payload[4]
                i = 5
            else:
                # Standard KWP: 58 Count ...
                if len(payload) < 2: return "KWP Error"
                count = payload[1]
                i = 2
            
            processed_count = 0
            while i + 2 < len(payload) and processed_count < count:
                dtc_h = payload[i]
                dtc_l = payload[i+1] # Low byte or rest of code
                st = payload[i+2]
                
                # Decoding High Byte for P/C/B/U
                # KWP/BRP logic: Use same masking as UDS or simple?
                # P042D -> 04 2D. 04 = 0000 0100. P.
                # C0043 -> 40 43 (likely). 40 = 0100 0000. C.
                
                type_code = (dtc_h & 0xC0) >> 6
                prefix = {0: "P", 1: "C", 2: "B", 3: "U"}[type_code]
                
                # Check for standard 2-byte KWP structure
                # Hex string of remaining parts
                val = ((dtc_h & 0x3F) << 8) | dtc_l
                code_str = f"{prefix}{val:04X}"
                
                # Look up description
                desc_str = lookup_dtc_desc(BRP_DTC_DB, code_str, "Unknown Fault")
                
                # BRP/KWP Status:
                # 0x2x, 0x6x often seen.
                # 0x60 = Active? 
                # Let's mark as active if non-zero for now/logging
                is_active = (st & 0x20) != 0 or (st & 0x40) != 0 or st == 0x60
                
                dtc_obj = {
                    'code': code_str,
                    'is_active': is_active, 
                    'desc': desc_str,
                    'count': 1
                }
                dtcs.append(dtc_obj)
                i += 3
                processed_count += 1
            
            self.update_dtc_table(dtcs)
            return f"Found {len(dtcs)} DTCs (BRP/KWP)"
            
        # 0x67: Security Access Response
        elif sid == 0x67:
            # 67 [Level] [Seed...]
            if len(payload) < 2: return "Sec Access Response Error"
            level = payload[1]
            seed_bytes = payload[2:]
            
            if not seed_bytes:
                # Access Granted usually just 67 02 or 67 08
                self.lbl_sec_status.configure(text=f"Acesso NÃ­vel {level:02X} Concedido!", text_color="green")
                return f"Security Access Granted (Level {level:02X})"
            else:
                # Seed Provided
                seed_hex = seed_bytes.hex().upper()
                self.lbl_sec_status.configure(text=f"Seed Recebido: {seed_hex}", text_color="orange")
                
                # Implement Simple Sum Algorithm (Observed in Log: +0x33D5)
                # Seed: 85 42 -> 34114
                # Key:  B9 17 -> 47383 (Diff: 13269 = 0x33D5)
                if len(seed_bytes) >= 2:
                    seed_val = (seed_bytes[0] << 8) | seed_bytes[1]
                    
                    # Logic: Key = Seed + 0x33D5 (with 16-bit wrap)
                    key_val = (seed_val + 0x33D5) & 0xFFFF
                    
                    key_h = (key_val >> 8) & 0xFF
                    key_l = key_val & 0xFF
                    
                    # Send Key (Level + 1)
                    # 27 [Level+1] [KeyH] [KeyL]
                    next_level = level + 1
                    self.send_can_packet(0x7E0, 8, [0x04, 0x27, next_level, key_h, key_l, 0x00, 0x00, 0x00])
                    
                    self.lbl_sec_status.configure(text=f"Enviando Chave: {key_val:04X}...", text_color="yellow")
                    return f"Security Seed RX: {seed_hex}. Sending Key: {key_val:04X}"

                return f"Security Seed RX: {seed_hex} (Lev {level:02X})"

        # 0x41: OBD-II Mode 01 Response (Backwards compat)
        elif sid == 0x41:
            pid = payload[1]
            if pid in self.obd_pids:
                 name, calc_func = self.obd_pids[pid]
                 # Extract A, B, C, D if available
                 a = payload[2] if len(payload) > 2 else 0
                 b = payload[3] if len(payload) > 3 else 0
                 c = payload[4] if len(payload) > 4 else 0
                 d = payload[5] if len(payload) > 5 else 0
                 val_str = calc_func(a, b, c, d)
                 return f"OBD: {name} = {val_str}"

        # 0x5A: KWP ReadEcuIdentification Response (Used by IBR mainly)
        elif sid == 0x5A:
             # Fmt: [5A] [LocalID] [AsciiBytes...]
             if len(payload) > 2:
                 local_id = payload[1]
                 ascii_val = "".join([chr(b) for b in payload[2:] if 31 < b < 127])
                 
                 # IBR Updates
                 if local_id == 0x90: self.update_ibr_info("vin", ascii_val)
                 elif local_id == 0x91: self.update_ibr_info("part", ascii_val)
                 elif local_id == 0xB0: self.update_ibr_info("sw", ascii_val)
                 
                 return f"ECU Info [{local_id:02X}]: {ascii_val}"

        return f"UDS Resp: {sid:X}"

    def update_dtc_table(self, dtc_list):
        # dtc_list is list of {code, is_active, module?, ...}
        
        # Separação por modelo: acumula módulos/códigos do scan e, quando o modelo
        # é identificado, reconstrói a tabela com o catálogo desse modelo.
        self._begin_scan_if_stale()
        self._scan_modules = getattr(self, "_scan_modules", set())
        self._scan_codes = getattr(self, "_scan_codes", set())
        for dtc in dtc_list:
            if dtc.get("module"):
                self._scan_modules.add(dtc["module"])
            if dtc.get("code"):
                self._scan_codes.add(dtc["code"])
        self._update_brp_model_context()

        # Descrição específica do modelo tem prioridade sobre a base genérica
        model = self._active_model()
        if model:
            model_dtcs = model.get("dtcs") or {}
            for dtc in dtc_list:
                entry = model_dtcs.get(dtc.get("code"))
                if entry and entry.get("desc"):
                    dtc["desc"] = entry["desc"]

        found_count = len(dtc_list)
        self.dtc_status_label.configure(text=f"Scan Complete: {found_count} Faults" + self._dtc_status_suffix())
        
        # 1. Update found codes
        for dtc in dtc_list:
            c = dtc['code']
            is_act = dtc['is_active']
            mod_name = dtc.get('module', '')
            
            # If code exists in DB
            if c in self.dtc_rows:
                w = self.dtc_rows[c]
                # Descrição específica do modelo (se houver) substitui a genérica
                if dtc.get("desc") and w["desc"].cget("text") != dtc["desc"]:
                    w["desc"].configure(text=dtc["desc"])
                # Module label
                if "mod" in w and mod_name:
                    w["mod"].configure(text=mod_name, text_color="#88ccff")
                # Highlighting
                if is_act:
                    w["frame"].configure(fg_color="#4a1a1a") # Dark Red BG
                    w["stat"].configure(text="ACTIVE", text_color="#FF3333")
                    w["cod"].configure(text_color="white")
                    w["desc"].configure(text_color="white")
                    w["sol"].configure(text_color="#FFaaaa")
                    w["active"] = True
                else:
                    w["frame"].configure(fg_color="#333300") # Dark Yellow BG
                    w["stat"].configure(text="HISTORY", text_color="orange")
                    w["cod"].configure(text_color="#eee")
                    w["desc"].configure(text_color="#ccc")
                    w["sol"].configure(text_color="#999")
                    w["active"] = False
            else:
                pass  # Dynamic row added below

        # 2. Sort Rows: Active -> History -> Inactive
        def get_sort_weight(code):
            if code not in self.dtc_rows: return 100
            w = self.dtc_rows[code]
            stat_text = w["stat"].cget("text")
            if stat_text == "ACTIVE": return 0
            if stat_text == "HISTORY": return 1
            return 2
            
        sorted_codes = sorted(self.dtc_rows.keys(), key=get_sort_weight)
        for code in sorted_codes:
            self.dtc_rows[code]["frame"].pack_forget()
            self.dtc_rows[code]["frame"].pack(fill="x", pady=1)
            
        # 3. Handle unknown DTC codes â€” create dynamic rows at top
        for dtc in dtc_list:
            if dtc['code'] not in self.dtc_rows:
                mod_name = dtc.get('module', '?')
                row_frame = ctk.CTkFrame(self.dtc_list_frame, fg_color="#333", height=35)
                row_frame.pack(fill="x", pady=1, before=self.dtc_list_frame.winfo_children()[0])
                row_frame.grid_columnconfigure(3, weight=1)
                row_frame.grid_columnconfigure(4, weight=1)
                
                status_lbl = "ACTIVE" if dtc['is_active'] else "HIST"
                status_color = "#FF3333" if dtc['is_active'] else "orange"
                ctk.CTkLabel(row_frame, text=status_lbl, text_color=status_color, width=60).grid(row=0, column=0, padx=5)
                ctk.CTkLabel(row_frame, text=dtc['code'], font=("Arial",12,"bold"), width=70).grid(row=0, column=1, padx=5)
                ctk.CTkLabel(row_frame, text=mod_name, font=("Arial",11), width=65, text_color="#88ccff").grid(row=0, column=2, padx=5)
                ctk.CTkLabel(row_frame, text=dtc.get('desc', 'Unknown Fault Code'), text_color="white", anchor="w").grid(row=0, column=3, padx=5, sticky="ew")
                ctk.CTkLabel(row_frame, text="--", text_color="gray", anchor="w").grid(row=0, column=4, padx=5, sticky="ew")

    def update_ibr_info(self, type_key, value):
        """ Update the IBR Info labels in the UI """
        if type_key in self.ibr_info_labels:
            if type_key == "part": label_text = f"Part #: {value}"
            elif type_key == "vin": label_text = f"VIN: {value}"
            elif type_key == "sw": label_text = f"SW/Ser: {value}"
            else: label_text = f"{type_key}: {value}"
            
            self.ibr_info_labels[type_key].configure(text=label_text)

    def display_dtcs(self, text):
        # Legacy method kept for compatibility if called elsewhere
        # Or redirect to console
        self.console_textbox.insert("end", f"DTC RAW: {text}\n")


    def toggle_keep_alive(self):
        enabled = self.kwp_keep_alive_var.get()
        if (self.connection_mode == "AVR"
                and self.avr_bus_var.get() == "K-Line"
                and self._kline_active):
            # AVR K-Line: delega keepalive ao firmware
            t = self.avr_transport
            if t is not None:
                if enabled and getattr(self, "_yds_link", None) is not None:
                    # O link YDS nao tem TesterPresent: manter vivo = repetir a
                    # troca de bytes de identidade (opcao "Poll keep-alive").
                    self._avr_log(
                        "Keepalive KWP nao se aplica ao link YDS; "
                        "use 'Poll keep-alive'.\n")
                    self.kwp_keep_alive_var.set(False)
                    return
                if enabled:
                    try:
                        _yam = str(self._kline_proto or "").startswith("yamaha")
                        ecu_addr = 0x11 if _yam else 0x13
                        _ka_frame = self._yamaha_tester_present_frame(ecu_addr)
                        t.kline_keepalive_start(_ka_frame, interval_ms=1500)
                        self._avr_log(
                            "Keepalive K-Line no firmware: "
                            f"{' '.join(f'{b:02X}' for b in _ka_frame)} a cada 1.5s\n")
                    except Exception as _e:
                        self._avr_log(f"Keepalive firmware erro: {_e}\n")
                else:
                    t.kline_keepalive_stop()
                    self._avr_log("Keepalive K-Line parado no firmware.\n")
            return
        # CAN / serial modes: use the generic keep_alive_loop
        if enabled:
            self.keep_alive_thread = threading.Thread(target=self.keep_alive_loop, daemon=True)
            self.keep_alive_thread.start()
            self.console_textbox.insert("end", "Keep-Alive Started.\n")
        else:
            self._avr_log("Keep-Alive desativado.\n")

    def keep_alive_loop(self):
        """ Sends periodical Tester Present messages to keep diagnostic session active """
        while self.kwp_keep_alive_var.get() and self.is_connected:
             is_kwp = (self.active_protocol == "KWP")

             if is_kwp:
                # KWP (2009): Uses 0x55 padding traditionally (bit alternating for sync)
                # Formato: 02 3E 01 [55 55 55 55 55] - Matching logs
                self.send_can_packet(0x7E0, 8, [0x02, 0x3E, 0x01, 0x55, 0x55, 0x55, 0x55, 0x55])
             else:
                # UDS (2010+):
                # Log analysis (2022 GTX) shows BRP tool uses 55 padding everywhere.
                # We use 02 3E 80 (to suppress response) but filled with 55s to match 'style'.
                self.send_can_packet(0x7E0, 8, [0x02, 0x3E, 0x80, 0x55, 0x55, 0x55, 0x55, 0x55])

             time.sleep(2)

    def send_command(self, cmd_str):
        data = (cmd_str + "\n").encode()
        try:
            if self.connection_mode == "Serial" and self.ser:
                self.ser.write(data)
            elif self.connection_mode == "TCP" and self.tcp_socket:
                self.tcp_socket.sendall(data)
        except Exception as e:
            self.console_textbox.insert("end", f"Error sending command: {e}\n")
            self.console_textbox.see("end")

    def read_loop(self):
        """ Background thread to read from Serial, TCP, IXXAT, KVASER, or AVR """
        while not self.stop_thread:
            if self.connection_mode == "Serial" and self.ser and self.ser.is_open:
                self.read_serial()
            elif self.connection_mode == "TCP" and self.tcp_socket:
                self.read_tcp()
            elif self.connection_mode == "IXXAT" and self.can_bus:
                self.read_ixxat()
            elif self.connection_mode == "KVASER" and self.can_bus:
                self.read_kvaser()
            elif self.connection_mode == "AVR" and self.avr_transport:
                self.read_avr()
            else:
                time.sleep(0.1)

    def read_serial(self):
        try:
            # Read all available data
            while self.ser.in_waiting > 0:
                raw_line = self.ser.readline()
                try:
                    line_str = raw_line.decode('utf-8', errors='ignore').strip()
                    if line_str:
                        self.process_packet(line_str)
                except Exception:
                    pass
            
            # Small sleep to prevent 100% CPU usage
            time.sleep(0.005)

        except Exception as e:
            print(f"Serial Loop Error: {e}")
            self.stop_thread = True

    def read_tcp(self):
        try:
            data = self.tcp_socket.recv(1024)
            if data:
                text_chunk = data.decode('utf-8', errors='ignore')
                self.tcp_buffer += text_chunk
                
                while '\n' in self.tcp_buffer:
                    line, self.tcp_buffer = self.tcp_buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self.process_packet(line)
        except socket.timeout:
            pass # No data
        except Exception as e:
             if not self.stop_thread:
                print(f"TCP Loop Error: {e}")
                self.stop_thread = True

    def read_ixxat(self):
        try:
            msg = self.can_bus.recv(timeout=0.05)
            if msg is None:
                return

            # Reuse existing parsing path by normalizing to bridge packet format.
            dlc = int(msg.dlc) if hasattr(msg, "dlc") else len(msg.data)
            data_commas = ",".join(f"{b:02X}" for b in list(msg.data)[:dlc])
            pkt = f"PKT:{msg.arbitration_id:X},{dlc},{data_commas}"
            self.process_packet(pkt)
        except Exception as e:
            if not self.stop_thread:
                print(f"IXXAT Loop Error: {e}")
                self.stop_thread = True

    def read_avr(self):
        bus_type = self.avr_bus_var.get()
        if bus_type == "K-Line":
            self.read_avr_kline()
        else:
            self.read_avr_can()

    def read_avr_can(self):
        """Consome frames CAN enviados autonomamente pelo firmware (CMD_CAN_RX_AUTO=0x24)."""
        if self.stop_thread or not self.avr_transport:
            return
        try:
            pkt = self.avr_transport.poll_unsolicited()
            if pkt is None or pkt.command != 0x24:
                time.sleep(0.005)
            else:
                # payload: [RSP_OK, id_lo, id_hi, dlc, d0..d7]
                if len(pkt.payload) >= 4 and pkt.payload[0] == 0xA5:
                    can_id = pkt.payload[1] | (pkt.payload[2] << 8)
                    dlc = pkt.payload[3]
                    data = list(pkt.payload[4:4 + dlc])
                    data_commas = ",".join(f"{b:02X}" for b in data)
                    packet_str = f"PKT:{can_id:X},{dlc},{data_commas}"
                    self.process_packet(packet_str)

            # Log CAN status a cada 1 s
            now = time.monotonic()
            if now - self._last_can_status_time >= 1.0:
                self._last_can_status_time = now
                try:
                    st = self.avr_transport.can_get_status()
                    flags = []
                    if st.bus_off:       flags.append("BUS_OFF")
                    if st.error_warning: flags.append("ERR_WARN")
                    if st.data_overrun:  flags.append("OVERRUN")
                    flags_str = ",".join(flags) if flags else "none"
                    self._avr_log(
                        f"CAN_GET_STATUS sr=0x{st.status:02X} rxerr={st.rx_error_counter}"
                        f" txerr={st.tx_error_counter} rmc={st.rx_message_count} flags={flags_str}\n"
                    )
                    color = "red" if (st.bus_off or st.error_warning) else "lime green"
                    lbl = f"sr=0x{st.status:02X} rx={st.rx_error_counter} tx={st.tx_error_counter} [{flags_str}]"

                except Exception:
                    pass
        except Exception as e:
            if not self.stop_thread:
                print(f"AVR CAN Loop Error: {e}")
                self.stop_thread = True

    def _get_yamaha_signal_desc(self, signal_id):
        known = {
            0x88: "RPM/rotacao?",
            0x02: "TPS/carga?",
            0x18: "temperatura/estado?",
            0xCD: "carga/pressao?",
            0x9D: "estado ECM?",
            0xD6: "estado motor?",
            0x8C: "heartbeat idle",
            0x9C: "heartbeat idle",
        }
        return known.get(signal_id, "")

    def _reset_yamaha_graph_state(self, clear_selection=False):
        self.yamaha_graph_points.clear()
        self.yamaha_seen_signals.clear()
        self.yamaha_signal_buttons.clear()
        self._yamaha_selector_signature = None
        self.current_signal_source = None
        self.current_signal_id = None

        if hasattr(self, "signal_selector_scroll"):
            for widget in self.signal_selector_scroll.winfo_children():
                widget.destroy()

        if hasattr(self, "signals_scroll") and self.selected_graph_source == "yamaha":
            self.signal_rows.clear()
            for widget in self.signals_scroll.winfo_children():
                widget.destroy()

        if clear_selection and self.selected_graph_source == "yamaha":
            self.selected_graph_id = None
            self.selected_graph_source = "can"

    def _extract_yamaha_signal_pairs(self, frame_bytes):
        pairs = []
        raw = list(frame_bytes)
        idx = 0
        while idx < len(raw) - 1:
            if raw[idx] != 0xFC:
                idx += 1
                continue

            if idx + 3 < len(raw) and raw[idx + 1] != 0xFC and raw[idx + 2] == 0xFC and raw[idx + 3] != 0xFC:
                pairs.append((raw[idx + 1], raw[idx + 3]))
                idx += 4
                continue

            if idx + 2 < len(raw) and raw[idx + 1] != 0xFC and raw[idx + 2] != 0xFC:
                pairs.append((raw[idx + 1], raw[idx + 2]))
                idx += 3
                continue

            idx += 1
        return pairs

    def _push_yamaha_signal_sample(self, signal_id, value, timestamp=None):
        now = timestamp if timestamp is not None else time.time()
        history = self.yamaha_graph_points.setdefault(signal_id, deque(maxlen=2000))
        history.append((now, [value]))
        if signal_id not in self.yamaha_seen_signals:
            self.yamaha_seen_signals[signal_id] = {
                "desc": self._get_yamaha_signal_desc(signal_id)
            }
            self._yamaha_selector_signature = None

    def _replay_kline_row(self, direction: str, frame_bytes: list[int], timestamp: float):
        if direction == "BUS":
            for signal_id, value in self._extract_yamaha_signal_pairs(frame_bytes):
                self._push_yamaha_signal_sample(signal_id, value, timestamp=timestamp)

        hex_str = " ".join(f"{b:02X}" for b in frame_bytes)
        prefix = {
            "BUS": "[REPLAY SNIFF]",
            "RX": "[REPLAY KLINE RX]",
            "TX": "[REPLAY KLINE TX]",
        }.get(direction, f"[REPLAY KLINE {direction}]")
        self.raw_log_buffer.append(f"{prefix} {hex_str}\n")

    def _select_yamaha_graph(self, signal_id):
        self.selected_graph_source = "yamaha"
        self.selected_graph_id = signal_id
        self.current_signal_source = None
        self.current_signal_id = None

    def _refresh_yamaha_signal_selector(self):
        if not hasattr(self, "signal_selector_scroll"):
            return

        signal_ids = list(self.yamaha_seen_signals.keys())

        if self.selected_graph_id is None and signal_ids:
            for preferred_id in (0x88, 0x02, 0x18, 0xCD, 0x9D, 0xD6):
                if preferred_id in self.yamaha_seen_signals:
                    self._select_yamaha_graph(preferred_id)
                    break
            else:
                first_id = signal_ids[0]
                self._select_yamaha_graph(first_id)

        signature = (
            tuple(signal_ids),
            self.selected_graph_source,
            self.selected_graph_id,
        )
        if signature == self._yamaha_selector_signature:
            return

        self._yamaha_selector_signature = signature
        for widget in self.signal_selector_scroll.winfo_children():
            widget.destroy()
        self.yamaha_signal_buttons.clear()

        if not signal_ids:
            ctk.CTkLabel(
                self.signal_selector_scroll,
                text="Nenhum sinal Yamaha visto ainda. Inicie o sniff K-Line passivo para popular os IDs.",
                text_color="gray"
            ).grid(row=0, column=0, padx=6, pady=6, sticky="w")
            return

        for idx, signal_id in enumerate(signal_ids):
            row = idx // 4
            col = idx % 4
            desc = self.yamaha_seen_signals[signal_id].get("desc", "")
            text = f"{signal_id:02X}"
            if desc:
                text = f"{signal_id:02X} {desc}"
            is_selected = self.selected_graph_source == "yamaha" and self.selected_graph_id == signal_id
            button = ctk.CTkButton(
                self.signal_selector_scroll,
                text=text,
                width=150,
                height=28,
                fg_color="#1f6aa5" if is_selected else "#333333",
                command=lambda sid=signal_id: self._select_yamaha_graph(sid),
            )
            button.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            self.yamaha_signal_buttons[signal_id] = button

    def _kline_sniff_start(self):
        """Toggle passive K-Line bus sniffing.

        In sniff mode the AVR is put into K-Line mode (no wakeup, no TX) and
        we read every byte that appears on the wire â€” from BOTH the panel and
        the ECM.  Bytes are grouped into frames using the ISO-14230 inter-frame
        gap (> 25 ms = new frame) and logged to the CSV with ID 'KLINE-BUS'.
        """
        if self._kline_sniff_active:
            # --- STOP ---
            self._kline_sniff_active = False
            self._kline_sniff_stop.set()
            self.kline_sniff_btn.configure(text="K-Line Sniff (passivo)", fg_color="#1a4a6e")
            self._avr_log("[SNIFF] Parado.\n")
            return

        t = self.avr_transport
        if t is None:
            self._avr_log("[SNIFF] AVR nao conectado.\n")
            return

        # Stop any active keepalive and wait for it to fully exit (max 2s)
        # so its last TX doesn't corrupt the sniff capture window.
        self._kline_active = False
        if not self._kline_keepalive_dead.wait(timeout=2.0):
            self._avr_log("[SNIFF] Aviso: keepalive nao parou a tempo; continuando...\n")

        # --- START ---
        self._kline_sniff_stop.clear()   # reset stop event from any previous disconnect/sniff
        self._kline_sniff_active = True
        if self.avr_kline_proto_var.get().strip().lower() == "yamaha":
            self._reset_yamaha_graph_state(clear_selection=False)
        self.kline_sniff_btn.configure(text="PARAR Sniff", fg_color="#8B0000")
        baud = int(self.avr_kline_baud_var.get())
        if self.avr_kline_proto_var.get() == "Yamaha" and baud in (15625, 16040):
            self._avr_log(f"[SNIFF] Yamaha baud experimental selecionado: {baud}.\n")
        self._avr_log(f"[SNIFF] Iniciando em {baud} baud â€” escutando tudo no barramento...\n")
        threading.Thread(target=self._kline_sniff_loop, args=(baud,), daemon=True).start()

    def _kline_sniff_loop(self, baud: int):
        """Passive K-Line bus monitor thread.

        Reads K-Line in continuous bulk bursts through the AVR framed protocol.
        This avoids a USB round-trip per byte, which is too slow for passive
        sniffing after the move to the hardware UART path.

        Frame boundary: 25 ms of silence (ISO 14230 P1_max = 20 ms inside a
        frame; P3_min = 55 ms between frames).

        All frames are logged to CSV as KLINE-BUS.
        """
        t = self.avr_transport
        if t is None:
            self._avr_log("[SNIFF] AVR serial nao disponivel.\n")
            self._kline_sniff_active = False
            return

        # Flush any leftover bytes in AVR RX buffer (keepalive echo, etc.)
        # by doing one short bulk read that we discard.
        try:
            t.kline_rx_bulk(first_timeout_ms=80, inter_timeout_ms=4, max_bytes=64)
        except (TimeoutError, Exception):
            pass

        frame_buf = []
        frame_count = 0
        last_bulk_t = time.monotonic()
        # ISO 14230 P3_min = 55ms between frames. Yamaha proprietary uses ~48ms
        # minimum frame gap. Use 40ms so we don't split single frames while still
        # separating distinct request/response pairs.
        frame_gap_ms = 40.0

        self._avr_log(f"[SNIFF] Lendo barramento via KLINE_RX_BULK...\n")
        silence_reported = 0
        try:
            while not self._kline_sniff_stop.is_set():
                # O init/handshake YDS usa o mesmo transporte. Sem este lock os
                # dois threads leem a serial em paralelo e o pyserial rebenta com
                # ClearCommError/PermissionError, alem de roubarem bytes um ao outro.
                if not self._kline_session_lock.acquire(blocking=False):
                    time.sleep(0.02)
                    continue
                try:
                    # first_timeout_ms=45: wait up to 45ms for the first byte of a
                    # new burst. This keeps the loop responsive but avoids returning
                    # too early between bytes of the same Yamaha frame (bytes arrive
                    # every ~960Âµs at 10400 baud, well within inter_timeout_ms=5ms).
                    chunk = t.kline_rx_bulk(first_timeout_ms=45, inter_timeout_ms=5, max_bytes=32)
                except TimeoutError:
                    chunk = b''  # no bytes in this window; keep polling
                finally:
                    self._kline_session_lock.release()

                # Stop was requested while waiting on bulk read; exit without
                # emitting any extra [SNIFF #..] frame after user pressed stop.
                if self._kline_sniff_stop.is_set():
                    frame_buf = []
                    break

                now = time.monotonic()
                gap_ms = (now - last_bulk_t) * 1000.0

                if not chunk and not frame_buf:
                    # Sem bytes e sem frame em construcao: o barramento esta calado.
                    # Sem este aviso o utilizador ve o sniff "a correr" e conclui
                    # que ha trafego quando nao ha nada.
                    elapsed = now - last_bulk_t
                    if elapsed >= 2.0:
                        silence_reported += 1
                        last_bulk_t = now
                        self._avr_log(
                            f"[SNIFF] {int(elapsed)}s sem um unico byte — barramento "
                            f"em repouso (aviso {silence_reported}). Confirme ignicao, "
                            "fio RX na K-Line e massa comum.\n")
                    continue

                if chunk:
                    if frame_buf and gap_ms > frame_gap_ms:
                        frame_count += 1
                        for signal_id, value in self._extract_yamaha_signal_pairs(frame_buf):
                            self._push_yamaha_signal_sample(signal_id, value)
                        self._kline_record("BUS", frame_buf)
                        hex_str = " ".join(f"{b:02X}" for b in frame_buf)
                        direction = ""
                        if len(frame_buf) >= 2:
                            tgt = frame_buf[1]
                            if tgt == 0xF1:
                                direction = " â†ECM"
                            elif tgt in (0x11, 0x13):
                                direction = " â†’ECM"
                        self._avr_log(f"[SNIFF #{frame_count}]{direction} {hex_str}\n")
                        frame_buf = []

                    frame_buf.extend(chunk)
                    last_bulk_t = now
                else:
                    if frame_buf and (now - last_bulk_t) * 1000.0 > frame_gap_ms * 3:
                        frame_count += 1
                        for signal_id, value in self._extract_yamaha_signal_pairs(frame_buf):
                            self._push_yamaha_signal_sample(signal_id, value)
                        self._kline_record("BUS", frame_buf)
                        hex_str = " ".join(f"{b:02X}" for b in frame_buf)
                        direction = ""
                        if len(frame_buf) >= 2:
                            tgt = frame_buf[1]
                            if tgt == 0xF1:
                                direction = " â†ECM"
                            elif tgt in (0x11, 0x13):
                                direction = " â†’ECM"
                        self._avr_log(f"[SNIFF #{frame_count}]{direction} {hex_str}\n")
                        frame_buf = []
        except Exception as e:
            self._avr_log(f"[SNIFF] Erro: {e}\n")
        finally:
            self._kline_sniff_active = False
            self._avr_log("[SNIFF] Thread encerrada.\n")

    def read_avr_kline(self):
        """
        Background K-Line receive: poll one byte at a time and accumulate into
        _avr_kline_buf.  When a complete KWP frame is detected it is logged to
        the console as a hex string.

        Yields to init/keepalive when they hold the session lock, and fully
        yields to the sniff thread when passive sniff mode is active.
        """
        if self.stop_thread or not self.avr_transport:
            return
        # Passive sniff thread owns the serial directly â€” AVR packet layer must not touch it
        if self._kline_sniff_active:
            time.sleep(0.100)
            return
        # Yamaha traffic currently uses a proprietary protocol, not ISO-14230.
        # If we try to parse it as KWP here, the CSV gets polluted with fake
        # "KLINE-RX" frames that do not match the passive sniffer output.
        # In Yamaha mode, leave bus capture to the dedicated sniffer path.
        if self.avr_kline_proto_var.get().strip().lower() == "yamaha":
            time.sleep(0.050)
            return
        # Back off if an init or keepalive cycle is actively using the bus.
        # This prevents both threads from consuming bytes that belong to the
        # other, which would cause missed log entries and corrupt frame parsing.
        if self._kline_session_lock.locked():
            time.sleep(0.010)
            return
        try:
            chunk = self.avr_transport.kline_rx_bulk(first_timeout_ms=30, inter_timeout_ms=4, max_bytes=28)
            if self.stop_thread:
                return
            if not chunk:
                time.sleep(0.005)
                return
            self._avr_kline_buf.extend(chunk)
            while self._try_parse_kwp_frame():
                pass
        except Exception as e:
            if not self.stop_thread:
                print(f"AVR K-Line Loop Error: {e}")
                self.stop_thread = True

    def _try_parse_kwp_frame(self):
        """
        Minimal ISO-14230 / KWP2000 frame parser.
        Frame format: [FMT, TGT, SRC, (LEN), DATA..., CHK]
          FMT bits [7:6] = address type, bits [5:0] = length (0 â†’ extra LEN byte follows)
        """
        buf = self._avr_kline_buf
        if len(buf) < 4:
            return False
        # Accept only the address triplets used by our K-Line KWP sessions.
        # This prevents proprietary Yamaha bus traffic (for example FC 8C ...)
        # from being misparsed and logged as fake KWP frames.
        tgt = buf[1]
        src = buf[2]
        valid_addrs = {0x11, 0x13, 0xF1}
        if tgt not in valid_addrs or src not in valid_addrs or tgt == src:
            self._avr_kline_buf = buf[1:]
            return len(self._avr_kline_buf) >= 4
        fmt = buf[0]
        data_len = fmt & 0x3F
        if data_len == 0:
            # Additional length byte at position 3
            if len(buf) < 5:
                return False
            data_len = buf[3]
            frame_len = 1 + 1 + 1 + 1 + data_len + 1  # FMT TGT SRC LEN DATA CHK
        else:
            frame_len = 1 + 1 + 1 + data_len + 1  # FMT TGT SRC DATA CHK

        if len(buf) < frame_len:
            return False

        frame = buf[:frame_len]
        self._avr_kline_buf = buf[frame_len:]
        hex_str = " ".join(f"{b:02X}" for b in frame)
        self._avr_log(f"< KWP: {hex_str}\n")
        self._kline_record("RX", frame)
        return True
    
    def process_packet(self, line):
        """ Parse packet and update data structures """
        # Print to Raw Log (if not too spammy? limit it?)
        # self.console_textbox.insert("end", f"{line}\n") 
        # Using a queue or flag for UI update is safer, but insert is thread-safe in Tkinter mostly.
        # However, for high speed CAN, we should direct to Log less often.
        # But user wants Raw Log. Let's keep it but process logic first.
        
        # Parse Format: PKT:ID,DLC,D0,D1...
        if line.startswith("PKT:"):
            try:
                parts = line.split(',')
                # parts[0] is "PKT:1AB"
                id_hex = parts[0].split(':')[1]
                can_id = int(id_hex, 16)
                dlc = int(parts[1])
                data_bytes = parts[2:]
                
                now = time.time()
                
                if can_id in self.can_data:
                    node = self.can_data[can_id]
                    dt = now - node["ts"]
                    
                    # Store previous data for color delta visualization
                    node["prev_data"] = node["data"]
                    
                    node["cnt"] += 1
                    node["data"] = data_bytes
                    node["ts"] = now
                    node["dt"] = dt # Period
                else:
                    self.can_data[can_id] = {
                        "cnt": 1,
                        "dlc": dlc,
                        "data": data_bytes,
                        "prev_data": data_bytes,
                        "ts": now,
                        "dt": 0,
                        "desc": self.analyze_packet(can_id, data_bytes)
                    }
                
                # Update description on every packet? Maybe expensive.
                # Let's do it if it's new or if it's OBD response (value changes)
                if can_id in self.can_data:
                    self.can_data[can_id]["desc"] = self.analyze_packet(can_id, data_bytes)
                
                # --- Graph Data Collection ---
                if self.selected_graph_id is not None and can_id == self.selected_graph_id:
                     int_vals = [int(x, 16) for x in data_bytes]
                     self.graph_data_points.append((now, int_vals))
                
                # --- CSV Logging ---
                if self.is_recording and self.log_writer:
                    try:
                        self.log_writer.writerow([datetime.fromtimestamp(now).strftime("%H:%M:%S.%f"), f"{can_id:X}", dlc, " ".join(data_bytes)])
                    except: pass

                # Buffer for Raw Log (Don't write to UI directly in thread!)
                self.raw_log_buffer.append(f"[{id_hex}] {','.join(data_bytes)}\n")

            except Exception as e:
                print(f"Parse Error: {e} - Line: {line}")
        
        # Also handle Log messages from ESP
        elif line.startswith("I (") or "Request" in line or "Speed" in line:
             self.raw_log_buffer.append(f"{line}\n")

    def analyze_packet(self, can_id, data_bytes):
        """ Try to identify the packet meaning """
        
        # 1. OBD-II Response (ISO 15765-4) & BRP Diagnostics
        # Response IDs loaded from BRP module mapping extracted from EDB/ODX.
        KNOWN_RESP_IDS = KNOWN_MODULE_RESP_IDS
        
        if can_id in KNOWN_RESP_IDS or (0x7E8 <= can_id <= 0x7EF):
            # ISO-TP & UDS Handler
            try:
                vals = [int(x, 16) for x in data_bytes]
                if not vals: return "Empty"
                
                pci = vals[0] # Protocol Control Information
                pci_type = (pci & 0xF0) >> 4
                
                # Single Frame (SF)
                if pci_type == 0:
                    length = pci & 0x0F
                    payload = vals[1:1+length]
                    return self.parse_uds_response(payload, can_id) # Pass can_id for context
                
                # First Frame (FF)
                elif pci_type == 1:
                    full_len = ((pci & 0x0F) << 8) | vals[1]
                    self.isotp_rx_len = full_len
                    self.isotp_rx_buffer = vals[2:]
                    self.isotp_active = True
                    self.isotp_rx_id = can_id # Track who is sending
                    # Send Flow Control (BS=0, STmin=0)
                    # Note: We should ideally send FC for the specific ID, but simple FC 30 00 00 
                    # works if device accepts it blindly or if we send it on correct ID.
                    # GPS (7AE) listens on 7A6. IBR (7BA) on 7B2.
                    # We can automate Flow Control response here if needed.
                    if can_id == 0x7AE:
                        # GPS Flow Control
                        self.send_can_packet(0x7A6, 8, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    elif can_id == 0x7BA:
                         self.send_can_packet(0x7B2, 8, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    elif can_id == 0x7BD:
                         self.send_can_packet(0x7B5, 8, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    else: # Default 7E0 Request -> 7E8 Response
                         self.send_can_packet(0x7E0, 8, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                         
                    return f"ISO-TP FF (Len: {full_len})"
                
                # Consecutive Frame (CF)
                elif pci_type == 2:
                    if self.isotp_active: # Basic check
                        # Check ID match if possible, but simplicity first
                        self.isotp_rx_buffer.extend(vals[1:])
                        
                        if len(self.isotp_rx_buffer) >= self.isotp_rx_len:
                            # Complete!
                            complete_payload = self.isotp_rx_buffer[:self.isotp_rx_len]
                            self.isotp_active = False
                            return self.parse_uds_response(complete_payload, can_id) # Pass ID
                        return f"ISO-TP CF ({len(self.isotp_rx_buffer)}/{self.isotp_rx_len})"
                    return "ISO-TP CF (Orphan)"
                
            except Exception as e:
                return f"Err: {e}"
        
        return ""

        # 2. OBD-II Request (Function)
        if can_id == 0x7DF:
            return "OBD-II Broadcast Request"

        # 3. Common OEM IDs (Very Generic examples)
        # This is where you would build a database for specific cars (GMLAN, CANopen, etc.)
        if can_id == 0x100 and len(data_bytes) == 8:
            # Hypothetical Engine data
            return "Engine Data (Maybe)"
        
        # --- BRP Specific Decoders ---
        if can_id == 0x102:
            return "BRP Engine: B0+1=RPM, B2=TPS, B3=Exhaust?, B4=EngTemp?"
        
        if can_id == 0x103:
            return "BRP Engine 2: APS(B0), Seq(B6-B7)"

        if can_id == 0x110:
            return "BRP Control? [Displaying Full Packet]"

        if can_id == 0x230:
            return "BRP IBR Ctrl: B5=Trigger?"
            
        if can_id == 0x204:
            return "BRP Gate: B1=Position?"
            
        if can_id == 0x408:
            return "BRP VTS/Trim: B0={8=Up, 4=Down}"
            
        if can_id == 0x410:
            return "BRP Cluster Btn: B1={1=Mode, 2=Set}"

        if can_id == 0x514:
            return "BRP: VIN [B2-B6]"
            
        if can_id == 0x10:
            return "BRP: Wakeup + IBR: Trigger(B4), Gate(B2)"
            
        return ""

    def update_ui_loop(self):
        """ Periodically refresh the Traffic Monitor and Graph """
        # Allow UI update if connected OR replaying
        if not self.is_connected and not self.is_replaying:
            self.after(200, self.update_ui_loop)
            return

        now = time.time()
        
        # Only update every 200ms (5 FPS)
        if now - self.last_ui_update > 0.18:
            self.last_ui_update = now
            
            # --- Update BRP Diagnostics Tab (Realtime Gauges) ---
            if 0x102 in self.can_data:
                # Payload: [RPM_H] [RPM_L] [TPS] [ENG_TEMP] [INTAKE_TEMP] ...
                data = self.can_data[0x102]["data"]
                # Convert strings "00", "01" to ints
                try:
                    bytes_val = [int(x, 16) for x in data]
                    
                    # 1. RPM (First 2 bytes)
                    # Formula: ((Byte0 << 8) | Byte1) / 4 ??
                    # User observed ~7000 value for 1760 Real RPM.
                    # 7000 / 1760 ~= 3.97. So Factor is 0.25
                    raw_rpm = (bytes_val[0] << 8) | bytes_val[1]
                    rpm_val = int(raw_rpm / 4)
                    try:
                        self.rpm_gauge.set_value(rpm_val)
                    except: pass
                    
                    # 2. TPS (Byte 2)
                    tps_raw = bytes_val[2]
                    
                    # Simple linear mapping as requested: 0=0%, 255=100%
                    tps_pct_cal = (tps_raw / 255.0) * 100
                    
                    try:
                        self.tps_gauge.set_value(tps_pct_cal)
                    except: pass
                    
                    # 3. Engine Temp (Byte 3 / Index 3) -> Value / 3
                    eng_temp_raw = bytes_val[3]
                    eng_temp_c = eng_temp_raw / 3.0
                    try:
                        self.temp_eng_gauge.set_value(eng_temp_c)
                    except: pass
                    
                    # 4. Intake Temp (Byte 4 / Index 4) -> Value / 3
                    intake_temp_raw = bytes_val[4]
                    intake_temp_c = intake_temp_raw / 3.0
                    try:
                        self.temp_intake_gauge.set_value(intake_temp_c)
                    except: pass

                    # 5. Engine Status (Derived from RPM)
                    if rpm_val > 500:
                        self.status_bar_lbl.configure(text="Status: MOTOR FUNCIONANDO", text_color="green")
                    else:
                        self.status_bar_lbl.configure(text="Status: MOTOR PARADO", text_color="red")
                except: pass

            # --- ID 0x300: Exhaust Temp Candidate (Byte 5) ---
            if 0x300 in self.can_data:
                data = self.can_data[0x300]["data"]
                try:
                     # Byte 5 seems to correlate with Engine Temp (Diff 40)
                     if len(data) > 5:
                        exh_raw = int(data[5], 16)
                        # Heuristic: Raw value for now. 
                        
                        self.temp_exh_gauge.set_value(exh_raw)
                        # self.exhaust_temp_label.configure(text=f"Temp. Escape: {exh_raw}") 
                except: pass

            # --- ID 0x342: Battery Voltage Candidate ---
            if 0x342 in self.can_data:
                data = self.can_data[0x342]["data"]
                try:
                    bytes_val = [int(x, 16) for x in data]
                    if len(bytes_val) > 4:
                        # Byte 4 (Index 4) -> Volts / 10
                        volts = bytes_val[4] / 10.0
                        
                        # Update Gauge
                        if hasattr(self, 'battery_gauge'):
                           self.battery_gauge.set_value(volts)
                        
                        # Try updating Yamaha label if exists (legacy)
                        if hasattr(self, 'yamaha_battery_label'):
                             self.yamaha_battery_label.configure(text=f"Bateria: {volts:.1f} V")
                except: pass


            # --- Update VIN from ID 514 ---
            if 0x514 in self.can_data:
                 data = self.can_data[0x514]["data"]
                 try:
                     # Bytes 2 to 6 are ASCII
                     bytes_val = [int(x, 16) for x in data]
                     ascii_str = ""
                     for b in bytes_val[2:7]: # indices 2,3,4,5,6
                         if 32 <= b <= 126:
                             ascii_str += chr(b)
                     self.vin_label.configure(text=f"Partial VIN/Cal: {ascii_str}")
                 except: pass

            # --- Update ID 103 (User Request: B6, B7) ---
            if 0x103 in self.can_data:
                try:
                    data = self.can_data[0x103]["data"]
                    # Check length
                    if len(data) >= 8:
                        val_aps = int(data[0], 16) # Byte 0 APS (Accelerator Position Sensor)
                        val_b6 = int(data[6], 16)
                        val_b7 = int(data[7], 16)
                        
                        # Update APS Visual
                        aps_pct = (val_aps / 255.0) * 100
                        if hasattr(self, 'aps_bar'):
                            # Check if it's VerticalBarWithMarker (set_value(0-100)) or ProgressBar (set(0-1))
                            if isinstance(self.aps_bar, VerticalBarWithMarker):
                                self.aps_bar.set_value(aps_pct)
                            else:
                                self.aps_bar.set(val_aps / 255.0)
                                
                        if hasattr(self, 'aps_label'):
                            self.aps_label.configure(text=f"APS\n{aps_pct:.0f}%")
                        
                        if hasattr(self, 'debug_103_label'):
                            self.debug_103_label.configure(text=f"ID 103: APS(B0)={val_aps} (Raw) | B6={val_b6} | B7={val_b7}")
                except: pass

            # --- Update ID 110 (User Request) ---
            if 0x110 in self.can_data:
                try:
                    data = self.can_data[0x110]["data"]
                    # Show all bytes
                    data_str = " ".join(data)
                    self.debug_110_label.configure(text=f"ID 110: {data_str}")
                except: pass

            # --- Update Buttons (408 & 410) ---
            # ID 408 Byte 0: VTS and Arrows
            if 0x408 in self.can_data:
                try:
                    data = self.can_data[0x408]["data"]
                    val = int(data[0], 16)
                    
                    # 1. VTS Logic (16=Up, 32=Down)
                    if val == 16:
                        self.lbl_vts.configure(text="VTS (Trim): UP â–²", text_color="#00ff00")
                    elif val == 32:
                        self.lbl_vts.configure(text="VTS (Trim): DOWN â–¼", text_color="#00ff00")
                    else:
                        self.lbl_vts.configure(text="VTS (Trim): --", text_color="gray")

                    # 2. Arrow Logic (8=Up, 4=Down) - Independent check if possible?
                    # Assuming they are exclusive states in byte 0 for now.
                    if val == 8:
                        self.lbl_arrows.configure(text="Arrow Keys: UP â–²", text_color="cyan")
                    elif val == 4:
                        self.lbl_arrows.configure(text="Arrow Keys: DOWN â–¼", text_color="cyan")
                    else:
                        self.lbl_arrows.configure(text="Arrow Keys: --", text_color="gray")
                except: pass
            
            # Cluster Buttons (0x410 Byte 1)
            if 0x410 in self.can_data:
                try:
                    data = self.can_data[0x410]["data"]
                    val = int(data[1], 16)
                    if val == 1:
                        self.lbl_cluster_btn.configure(text="Cluster: MODE", text_color="cyan")
                    elif val == 2:
                        self.lbl_cluster_btn.configure(text="Cluster: SET", text_color="cyan")
                    else:
                        self.lbl_cluster_btn.configure(text="Cluster: --", text_color="gray")
                except: pass

            # --- Update IBR Tab (0x10 Trigger & Gate) ---
            ibr_id = 0x10
            
            if ibr_id in self.can_data:
                try:
                    data = self.can_data[ibr_id]["data"]
                    if len(data) >= 5:
                        # --- Trigger / Lever Logic ---
                        # Standard: Byte 4 is Track 1 (Rising)
                        trigger_raw = int(data[4], 16)
                        if trigger_raw < 35: trigger_raw = 0 
                        trig_val = (trigger_raw / 255.0) * 100
                             
                        # Update UI - Trigger/Track 1
                        if hasattr(self, 'trigger_gauge'): self.trigger_gauge.set_value(trig_val)
                        if hasattr(self, 'ibr_track1_gauge'): self.ibr_track1_gauge.set_value(trig_val)
                        
                        # Update UI - Track 2 (Simulated Inverse 100 -> 0)
                        t2_pct = 100 - trig_val
                        if hasattr(self, 'ibr_track2_gauge'): self.ibr_track2_gauge.set_value(t2_pct)

                        # Update ECM Bar
                        if hasattr(self, 'ibr_lever_bar'): self.ibr_lever_bar.set_value(trig_val)
                        if hasattr(self, 'ibr_lever_label'): self.ibr_lever_label.configure(text=f"IBR\n{trig_val:.0f}%")
                        if hasattr(self, 'lbl_ibr_trigger'): self.lbl_ibr_trigger.configure(text=f"Brake Trigger: {trig_val:.1f} %")

                        # --- Gate Logic ---
                        gate_raw = int(data[2], 16)
                        gate_val = (gate_raw / 255.0) * 100
                        
                        # FORCE UPDATE without hasattr check if possible, or debug
                        try:
                            # print(f"Invoking Gate Gauge SetValue with {gate_val}")
                            self.gate_gauge.set_value(gate_val)
                        except Exception as e:
                            print(f"FAILED Gate Gauge SetValue: {e}")
                            
                        if hasattr(self, 'lbl_ibr_gate'): self.lbl_ibr_gate.configure(text=f"Gate Pos: {gate_val:.1f} %")
                        if hasattr(self, 'ibr_lever_bar'): self.ibr_lever_bar.set_marker(gate_val)

                        # --- Current Logic ---
                        # Assuming Byte 5 is current
                        if len(data) > 5:
                            cur_raw = int(data[5], 16)
                            cur_val = cur_raw / 2.0
                            try:
                                self.ibr_current_gauge.set_value(cur_val)
                            except: pass

                        # DEBUG output to verify values
                        if now - getattr(self, "last_debug_print", 0) > 2.0:
                             self.last_debug_print = now
                             print(f"DEBUG: Trig={trig_val:.1f} Gate={gate_val:.1f} Cur={cur_val if 'cur_val' in locals() else 'N/A'}")

                except Exception as e:
                     print(f"Error updating IBR UI: {e}")

                
            # Gate Position Backup (ID 0x204?)
            # if 0x204 in self.can_data: 
            #    ... (Disabled in favor of ID 10)

            # --- Update Monitor ---
        
        # Optimize: Only update every 200ms
        # FIX: Separate timer for monitor to avoid conflict with BRP timer above
        if now - getattr(self, "last_monitor_update", 0) > 0.48:
            self.last_monitor_update = now
            
            # Use list() to avoid RuntimeError: dictionary changed size during iteration
            for cid, info in list(self.can_data.items()):
                hex_id = f"{cid:X}"
                data_bytes_hex = info["data"] 
                prev_bytes_hex = info.get("prev_data", data_bytes_hex)
                
                # Check for row existence
                if cid not in self.monitor_rows:
                    self.create_monitor_row(cid)
                    
                widgets = self.monitor_rows[cid]["widgets"]
                # 0: ID, 1: DLC, 2-9: Bytes, 10: Count, 11: Freq, 12: Desc
                
                # Update ID (Color if selected)
                widgets[0].configure(text=hex_id)
                if self.selected_graph_id == cid:
                    widgets[0].configure(text_color="cyan")
                else:
                    widgets[0].configure(text_color="white")
                    
                widgets[1].configure(text=str(info["dlc"]))
                
                # Update Bytes with Individual Colors
                c_v = [int(x, 16) for x in data_bytes_hex]
                p_v = [int(x, 16) for x in prev_bytes_hex]
                
                for i in range(8):
                    lbl = widgets[2+i]
                    if i < len(c_v):
                        val = c_v[i]
                        prev = p_v[i] if i < len(p_v) else val
                        
                        lbl.configure(text=f"{val}")
                        if val > prev:
                            lbl.configure(text_color="#00ff00") # Green
                        elif val < prev:
                            lbl.configure(text_color="#ff0000") # Red
                        else:
                            lbl.configure(text_color="#aaaaaa") # Gray/White
                    else:
                        lbl.configure(text="")

                freq = f"{1.0/info['dt']:.1f}" if info["dt"] > 0 else "0.0"
                widgets[10].configure(text=str(info["cnt"]))
                widgets[11].configure(text=freq)
                widgets[12].configure(text=info.get("desc", ""))

            # --- Update Graph ---
            self.draw_graph()


            # --- Update Yamaha Signal Selector ---
            self._refresh_yamaha_signal_selector()


            
            # --- Update Signal Strips ---
            self.draw_signal_strips()
            
            # --- Update Replay Progress ---
            if self.is_replaying:
                # Only update slider if user is NOT dragging it?
                # ctk slider doesn't have explicit is_dragging property easily accessible.
                # But we can verify if the difference is small, or assume update is fine.
                # If we update continuously, it might be hard to grab. 
                # Let's check if there's a seek request pending, if so, skip update
                if self.seek_request is None:
                    self.replay_slider.set(self.current_replay_progress)
                
                self.replay_label.configure(text=f"{self.current_replay_time_str}")
            
            # --- Update Raw Log (Batch) ---
            # Only if Tab is visible? For now, just check buffer
            if self.raw_log_buffer:
                # If buffer is huge, just take latest
                if len(self.raw_log_buffer) > 50:
                    text_blob = "".join(list(self.raw_log_buffer)[-50:])
                    self.raw_log_buffer.clear()
                else:
                    text_blob = "".join(self.raw_log_buffer)
                    self.raw_log_buffer.clear()
                    
                # Only insert if "Raw Log" is selected (Optimization)
                if self.tabview.get() == "Raw Log":
                    self.console_textbox.insert("end", text_blob)
                    self.console_textbox.see("end")

        self.after(200, self.update_ui_loop)

    def draw_signal_strips(self):
        """ Draw 8-byte graphs for the SELECTED ID only """
        # If no ID selected, check logic (maybe show empty state)
        if self.selected_graph_id is None:
             # Logic to possibly clear if we had something before
             return

        selected_source = getattr(self, "selected_graph_source", "can")

        # Check for ID change
        current_id = getattr(self, "current_signal_id", None)
        current_source = getattr(self, "current_signal_source", None)
        
        if current_id != self.selected_graph_id or current_source != selected_source:
            # Reset UI
            self.current_signal_id = self.selected_graph_id
            self.current_signal_source = selected_source
            self.signal_rows.clear()
            for w in self.signals_scroll.winfo_children():
                w.destroy()
            if selected_source == "yamaha":
                desc_txt = self._get_yamaha_signal_desc(self.selected_graph_id)
                title_txt = f"Yamaha K-Line: ID {self.selected_graph_id:02X}"
                if desc_txt:
                    title_txt += f" ({desc_txt})"

                try:
                    self.signals_scroll.configure(label_text=title_txt)
                except:
                    pass

                row_frame = ctk.CTkFrame(self.signals_scroll, fg_color="#222")
                row_frame.pack(fill="x", pady=2, padx=2)
                ctk.CTkLabel(row_frame, text="VAL", width=40, font=("Arial", 12, "bold"), text_color="#00d4ff").pack(side="left", padx=5)
                if desc_txt:
                    ctk.CTkLabel(row_frame, text=desc_txt, width=160, anchor="w", font=("Arial", 11), text_color="#aaa").pack(side="left", padx=2)
                cv = tk.Canvas(row_frame, height=120, bg="#1a1a1a", highlightthickness=0)
                cv.pack(side="left", fill="both", expand=True, padx=2)
                self.signal_rows[0] = {"canvas": cv, "color": "#00d4ff"}
            else:
                # Known ID Descriptions (ID Map)
                known_ids = {
                    0x10: " (IBR Monitor)",
                    0x102: " (ECM - Motor)",
                    0x103: " (ECM - Motor)",
                    0x408: " (CLUSTER - Painel)",
                    0x410: " (CLUSTER - Painel)"
                }
                
                # Map ID -> { ByteIndex: Description }
                known_bytes = {
                    0x10:  { 4: "Gatilho Freio", 2: "Pos. Comporta" },
                    0x102: { 0: "RPM High", 1: "RPM Low", 2: "TPS %", 3: "Exhaust (EGT)?", 4: "Eng Temp?" },
                    0x103: { 0: "APS Raw", 6: "Seq Counter", 7: "Seq Checksum" },
                    0x408: { 0: "VTS/Setas (8=UP, 4=DN)" },
                    0x410: { 1: "Mode/Set (1=Mod, 2=Set)" }
                }

                desc_txt = known_ids.get(self.selected_graph_id, "")
                title_txt = f"Analise Detalhada: ID {self.selected_graph_id:X}{desc_txt}"

                try:
                    self.signals_scroll.configure(label_text=title_txt)
                except:
                    pass
                
                # Create 8 Byte Rows
                colors = ["#FF5555", "#55FF55", "#5555FF", "#FFFF55", "#FF55FF", "#55FFFF", "#FFAA00", "#FFFFFF"]
                
                # Get byte descriptions for current ID
                byte_descs = known_bytes.get(self.selected_graph_id, {})
                
                for i in range(8):
                    row_frame = ctk.CTkFrame(self.signals_scroll, fg_color="#222")
                    row_frame.pack(fill="x", pady=2, padx=2)
                    
                    # Label Byte X
                    ctk.CTkLabel(row_frame, text=f"B{i}", width=30, font=("Arial", 12, "bold"), text_color=colors[i]).pack(side="left", padx=5)
                    
                    # Byte Description (if known)
                    b_desc = byte_descs.get(i, "")
                    if b_desc:
                        ctk.CTkLabel(row_frame, text=b_desc, width=120, anchor="w", font=("Arial", 11), text_color="#aaa").pack(side="left", padx=2)
                    
                    # Canvas
                    cv = tk.Canvas(row_frame, height=60, bg="#1a1a1a", highlightthickness=0)
                    cv.pack(side="left", fill="both", expand=True, padx=2)
                    
                    self.signal_rows[i] = { "canvas": cv, "color": colors[i] }
        
        if selected_source == "yamaha":
            full_list = list(self.yamaha_graph_points.get(self.selected_graph_id, []))
            points = full_list[-500:]
            if len(points) < 2:
                return

            row = self.signal_rows.get(0)
            if not row:
                return

            cv = row["canvas"]
            col = row["color"]
            cv.delete("all")

            w = cv.winfo_width()
            h = cv.winfo_height()
            series = [pt[1][0] for pt in points]
            if not series:
                return

            min_val = min(series)
            max_val = max(series)
            val_range = max_val - min_val
            margin = 8
            draw_h = h - (2 * margin)
            x_step = w / (len(points) - 1)
            scale_factor = draw_h / val_range if val_range else 0
            coords = []

            for idx, val in enumerate(series):
                x = idx * x_step
                if val_range == 0:
                    y = h / 2
                else:
                    y = (h - margin) - ((val - min_val) * scale_factor)
                coords.extend((x, y))

            if len(coords) >= 4:
                cv.create_line(coords, fill=col, width=2)

            latest = series[-1]
            cv.create_text(w - 5, 5, text=f"Now: {latest} (0x{latest:02X})", fill=col, anchor="ne", font=("Consolas", 10, "bold"))
            cv.create_text(5, 5, text=f"Max: {max_val}", fill="#aaa", anchor="nw", font=("Arial", 8))
            cv.create_text(5, h - 5, text=f"Min: {min_val}", fill="#aaa", anchor="sw", font=("Arial", 8))
            cv.create_line(0, h, w, h, fill="#333", dash=(2,2))
            cv.create_line(0, 0, w, 0, fill="#333", dash=(2,2))
            return

        # Draw Data
        if not self.graph_data_points: return
        
        # Performance Optimization: Limit to last N points for rendering
        MAX_RENDER_POINTS = 500
        
        # Convert deque to list to support slicing (and freeze state)
        full_list = list(self.graph_data_points)
        points = full_list[-MAX_RENDER_POINTS:]
        
        count = len(points)
        if count < 2: return
        
        for i in range(8):
            row = self.signal_rows.get(i)
            if not row: continue
            
            cv = row["canvas"]
            col = row["color"]
            cv.delete("all")
            
            w = cv.winfo_width()
            h = cv.winfo_height()
            
            coords = []
            x_step = w / (count - 1)
            
            # Extract series for Byte i
            # Point format: (timestamp, [b0, b1, ..., bn])
            # Optimization: Use list comprehension directly on the sliced subset
            series = [pt[1][i] if i < len(pt[1]) else 0 for pt in points]
            
            if not series: continue

            # Auto-Scale Logic
            min_val = min(series)
            max_val = max(series)
            val_range = max_val - min_val
            
            # Add small padding/handling for flat lines
            margin = 5
            draw_h = h - (2 * margin)
            
            # Draw Line
            # Optimization: Pre-calculate scaling factor
            scale_factor = 0
            if val_range != 0:
                scale_factor = draw_h / val_range

            for idx, val in enumerate(series):
                x = idx * x_step
                
                if val_range == 0:
                     # Flat line in center
                     y = h / 2
                else:
                     # Normalize 0..1 then scale to draw_h
                     # y = (h - margin) - ( (val - min_val) / val_range * draw_h )
                     y = (h - margin) - ((val - min_val) * scale_factor)
                     
                coords.append(x)
                coords.append(y)
                
            if len(coords) >= 4:
                cv.create_line(coords, fill=col, width=2)
            
            # Info Text overlay
            latest = series[-1]
            cv.create_text(w-5, 5, text=f"Now: {latest} (0x{latest:02X})", fill=col, anchor="ne", font=("Consolas", 10, "bold"))
            cv.create_text(5, 5, text=f"Max: {max_val}", fill="#aaa", anchor="nw", font=("Arial", 8))
            cv.create_text(5, h-5, text=f"Min: {min_val}", fill="#aaa", anchor="sw", font=("Arial", 8))
            
            cv.create_line(0, h, w, h, fill="#333", dash=(2,2)) # Bottom Line
            cv.create_line(0, 0, w, 0, fill="#333", dash=(2,2)) # Top Line



    def toggle_recording(self):
        if not self.is_recording:
            # Start
            try:
                filename = f"can_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                self.current_log_filename = filename
                self.log_file = open(filename, 'w', newline='')
                self.log_writer = csv.writer(self.log_file)
                self.log_writer.writerow(["Timestamp", "ID", "DLC", "Data"])
                self.is_recording = True
                self.record_btn.configure(text="STOP REC", fg_color="red")
                self.console_textbox.insert("end", f"Recording started: {filename}\n")
            except Exception as e:
                self.console_textbox.insert("end", f"Error starting record: {e}\n")
        else:
            # Stop
            self.is_recording = False
            if self.log_file:
                self.log_file.close()
                self.log_file = None
                self.log_writer = None
            self.record_btn.configure(text="START REC", fg_color="#444444")
            self.console_textbox.insert("end", "Recording stopped.\n")
            
            # Ask to Rename
            if self.current_log_filename and os.path.exists(self.current_log_filename):
                try:
                    new_path = filedialog.asksaveasfilename(
                        defaultextension=".csv",
                        initialfile=self.current_log_filename,
                        title="Save Log File As",
                        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
                    )
                    
                    if new_path:
                        # Normalize paths
                        old_abs = os.path.abspath(self.current_log_filename)
                        new_abs = os.path.abspath(new_path)
                        
                        if old_abs != new_abs:
                            if os.path.exists(new_abs):
                                os.remove(new_abs) # Ensure overwrite
                            os.rename(old_abs, new_abs)
                            self.console_textbox.insert("end", f"Log saved to: {new_path}\n")
                        else:
                            self.console_textbox.insert("end", f"Log saved to: {self.current_log_filename}\n")
                    else:
                         self.console_textbox.insert("end", f"Save cancelled. File left at: {self.current_log_filename}\n")
                except Exception as e:
                    self.console_textbox.insert("end", f"Error renaming file: {e}\n")
            
            self.current_log_filename = None

    def on_replay_seek(self, value):
        # Value is 0.0 to 1.0 from slider
        if self.is_replaying:
            self.seek_request = value
            
    def toggle_pause(self):
        if not self.is_replaying: return
        
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.configure(text="RESUME", fg_color="green")
            self.console_textbox.insert("end", "Replay Paused.\n")
        else:
            self.pause_btn.configure(text="PAUSE", fg_color="#444444")
            self.console_textbox.insert("end", "Replay Resumed.\n")

    def toggle_replay(self):
        if self.is_replaying:
            self.is_replaying = False
            self.is_paused = False
            self.replay_btn.configure(text="REPLAY LOG", fg_color="#222222")
            self.pause_btn.configure(state="disabled", text="PAUSE", fg_color="#444444")
            self.console_textbox.insert("end", "Replay stopped.\n")
            return

        # Open File Dialog
        filename = filedialog.askopenfilename(title="Select Log File (CSV)", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if not filename:
             return

        self.is_replaying = True
        self.is_paused = False
        self.replay_btn.configure(text="STOP REPLAY", fg_color="red")
        self.pause_btn.configure(state="normal", text="PAUSE", fg_color="#444444")
        self.console_textbox.insert("end", f"Replaying: {filename}\n")
        
        # Disable Connection if active?  
        if self.is_connected:
             self.console_textbox.insert("end", "WARN: Serial is connected! Mixed data may occur.\n")
        
        # Clear existing data for clean replay view
        self.can_data.clear()
        
        # Reset Gauge Stats (Max/Min)
        if hasattr(self, 'gauge_rpm') and self.gauge_rpm: self.gauge_rpm.reset_stats()
        if hasattr(self, 'gauge_temp') and self.gauge_temp: self.gauge_temp.reset_stats()
        if hasattr(self, 'batt_gauge') and self.batt_gauge: self.batt_gauge.reset_stats()
        if hasattr(self, 'gauge_exhaust') and self.gauge_exhaust: self.gauge_exhaust.reset_stats()
        
        # Clear Monitor Rows
        for cid, row_data in self.monitor_rows.items():
            for widget in row_data["widgets"]:
                widget.destroy()
        self.monitor_rows.clear()
        
        self.graph_data_points.clear()
        self._reset_yamaha_graph_state(clear_selection=False)
        self.signal_rows.clear()
        # signal_rows UI cleanup needs to be manual if we want to remove widgets, 
        # but for now let's just clear the logical dict and let them recreate or flicker.
        # Actually better to destroy widgets:
        for widget in self.signals_scroll.winfo_children():
            widget.destroy()

        # Start Thread
        t = threading.Thread(target=self.replay_loop, args=(filename,), daemon=True)
        t.start()

    def replay_loop(self, filename):
        try:
            # Use same encoding assumptions as writer (system default)
            with open(filename, 'r') as f:
                # Quick sniff to check structure if possible, or just standard read
                reader = csv.reader(f)
                rows = list(reader)
                
                if not rows:
                     self.console_textbox.insert("end", "Log is empty.\n")
                     self.is_replaying = False
                     self.replay_btn.configure(text="REPLAY LOG", fg_color="#222222")
                     self.pause_btn.configure(state="disabled")
                     return
                
                # Check Header
                start_row_idx = 0
                if len(rows) > 0 and "timestamp" in rows[0][0].lower():
                    start_row_idx = 1
                
                if len(rows) <= start_row_idx:
                     self.console_textbox.insert("end", "Log contains no data rows.\n")
                     self.is_replaying = False
                     self.replay_btn.configure(text="REPLAY LOG", fg_color="#222222")
                     self.pause_btn.configure(state="disabled")
                     return

                # Find First Valid Timestamp
                t0 = None
                first_row_idx = -1
                
                self.console_textbox.insert("end", f"Log rows: {len(rows)}. Finding start time...\n")
                
                for i in range(start_row_idx, len(rows)):
                    row = rows[i]
                    if len(row) < 1: continue
                    ts_str = row[0].strip()
                    try:
                        # Try common formats
                        if "." in ts_str:
                            t0 = datetime.strptime(ts_str, "%H:%M:%S.%f")
                        else:
                            t0 = datetime.strptime(ts_str, "%H:%M:%S")
                        first_row_idx = i
                        break
                    except ValueError:
                        continue

                if not t0:
                    self.console_textbox.insert("end", "Replay Err: No valid timestamps found.\n")
                    self.is_replaying = False
                    self.replay_btn.configure(text="REPLAY LOG", fg_color="#222222")
                    self.pause_btn.configure(state="disabled")
                    return

                while True:
                    self.console_textbox.insert("end", f"Start: {t0.strftime('%H:%M:%S.%f')} - Playing...\n")
                    
                    # REPLAY STATE
                    replay_index = first_row_idx
                    total_data_rows = len(rows) - first_row_idx
                    
                    # We need a reference: (RealTime_Start) maps to (LogTime_Start)
                    # When seeking, we reset this reference.
                    start_real_time = time.time()
                    current_log_time_ref = t0 # The log time corresponding to start_real_time
                    
                    pkt_count = 0
                    
                    while self.is_replaying and replay_index < len(rows):
                        # 0. Handle Pause
                        if self.is_paused:
                            # If seeking while paused, we still want to apply the seek
                            if self.seek_request is not None:
                                # Apply seek logic below
                                pass 
                            else:
                                time.sleep(0.1)
                                # Keep real time strictly synced so we don't drift or jump
                                # Just shifting start_real_time forward by the sleep amount
                                start_real_time += 0.1
                                continue

                        # 1. Handle Seek
                        if self.seek_request is not None:
                            seek_pct = float(self.seek_request)
                            self.seek_request = None # Clear flag
                            
                            # Calculate New Index
                            new_offset = int(seek_pct * total_data_rows)
                            replay_index = first_row_idx + new_offset
                            if replay_index >= len(rows): replay_index = len(rows) - 1
                            
                            # Parse time at new index to reset sync
                            row = rows[replay_index]
                            ts_str = row[0].strip()
                            try:
                                if "." in ts_str:
                                    new_log_time = datetime.strptime(ts_str, "%H:%M:%S.%f")
                                else:
                                    new_log_time = datetime.strptime(ts_str, "%H:%M:%S")
                                    
                                # Reset Reference: NOW corresponds to New Log Time
                                start_real_time = time.time()
                                current_log_time_ref = new_log_time
                                
                                # Optional: Clear graphs if seeking backward?
                                # For now, we leave them dirty
                                
                            except:
                                pass # If fail, just continue linearly

                        # 2. Process Current Row
                        row = rows[replay_index]
                        replay_index += 1
                        
                        if len(row) < 4: continue
                        
                        ts_str = row[0].strip()
                        can_id_hex = row[1].strip()
                        dlc = row[2].strip()
                        data_str = row[3].strip()
                        
                        # Parse Time
                        try:
                            if "." in ts_str:
                                curr_req_time = datetime.strptime(ts_str, "%H:%M:%S.%f")
                            else:
                                curr_req_time = datetime.strptime(ts_str, "%H:%M:%S")
                        except:
                            continue 
                            
                        # Calculate delay relative to our current reference point
                        # Log Delta = (Current Row Time) - (Reference Log Time)
                        # Wall Target = (Reference Wall Time) + Log Delta
                        
                        log_delta = (curr_req_time - current_log_time_ref).total_seconds()
                        
                        # Handle midnight wrap if needed (simple check)
                        if log_delta < -60: log_delta += 86400
                        
                        target_time = start_real_time + log_delta
                        sleep_time = target_time - time.time()
                        
                        # If we are behind, sleep_time is negative (catch up)
                        # If we are ahead, sleep_time is positive (wait)
                        if sleep_time > 0:
                            time.sleep(sleep_time)

                        # Update UI Progress (Variable)
                        current_offset = replay_index - first_row_idx
                        if total_data_rows > 0:
                            self.current_replay_progress = current_offset / total_data_rows
                        self.current_replay_time_str = f"{curr_req_time.strftime('%H:%M:%S')}"

                        data_parts = [part for part in data_str.split() if part]

                        if can_id_hex.upper().startswith("KLINE-"):
                            try:
                                frame_bytes = [int(part, 16) for part in data_parts]
                            except ValueError:
                                self.raw_log_buffer.append(f"[REPLAY] K-Line invalido: {can_id_hex} {data_str}\n")
                                continue

                            direction = can_id_hex.split("-", 1)[1].upper()
                            self._replay_kline_row(direction, frame_bytes, target_time)
                        else:
                            data_commas = ",".join(data_parts)
                            pkt = f"PKT:{can_id_hex},{dlc},{data_commas}"
                            self.process_packet(pkt)
                        pkt_count += 1
                
                    if not self.is_replaying: break

                    if self.loop_replay.get():
                        self.console_textbox.insert("end", "Replay Loop: Restarting...\n")
                        # Reset Stats
                        if hasattr(self, 'gauge_rpm') and self.gauge_rpm: self.gauge_rpm.reset_stats()
                        if hasattr(self, 'gauge_temp') and self.gauge_temp: self.gauge_temp.reset_stats()
                        if hasattr(self, 'batt_gauge') and self.batt_gauge: self.batt_gauge.reset_stats()
                        if hasattr(self, 'gauge_exhaust') and self.gauge_exhaust: self.gauge_exhaust.reset_stats()
                        self.graph_data_points.clear()
                        self._reset_yamaha_graph_state(clear_selection=False)
                        
                        time.sleep(1.0)
                        continue
                    else:
                        self.console_textbox.insert("end", f"Replay Finished. Packets: {pkt_count}\n")
                        self.current_replay_progress = 1.0
                        break

        except Exception as e:
            self.console_textbox.insert("end", f"Replay Error: {e}\n")
            print(f"Replay Exception: {e}")
        
        self.is_replaying = False
        self.current_replay_progress = 0
        self.current_replay_time_str = "--:--"
        try:
            self.replay_btn.configure(text="REPLAY LOG", fg_color="#222222")
            self.replay_slider.set(0)
            self.replay_label.configure(text="--:-- / --:--")
        except: pass





    def on_canvas_resize(self, event):
        self.draw_graph()

    def draw_graph(self):
        """ Simple Star Topology Visualization """
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        cx, cy = width / 2, height / 2
        
        # Draw Central BUS
        self.canvas.create_oval(cx-20, cy-20, cx+20, cy+20, fill="#1f538d", outline="white")
        self.canvas.create_text(cx, cy, text="CAN", fill="white", font=("Arial", 10, "bold"))
        
        # Assign positions for nodes (Circle them around center)
        sorted_ids = sorted(self.can_data.keys())
        count = len(sorted_ids)
        if count == 0:
            return
            
        radius = min(width, height) / 3
        
        moment = time.time()
        
        for i, cid in enumerate(sorted_ids):
            angle = (2 * math.pi * i) / count
            nx = cx + radius * math.cos(angle)
            ny = cy + radius * math.sin(angle)
            
            node = self.can_data[cid]
            
            # Highlight if active recently (< 0.5s)
            is_active = (moment - node["ts"]) < 0.5
            color = "#00ff00" if is_active else "#555555"
            size = 15 + (5 if is_active else 0)
            
            # Draw Connection
            self.canvas.create_line(cx, cy, nx, ny, fill="gray", width=1)
            
            # Draw Node
            self.canvas.create_oval(nx-size, ny-size, nx+size, ny+size, fill=color, outline="white")
            self.canvas.create_text(nx, ny, text=f"{cid:X}", fill="black" if is_active else "white", font=("Arial", 9, "bold"))

    def create_monitor_row(self, cid):
        row_idx = len(self.monitor_rows) + 1
        widgets = []
        # Columns: ID, DLC, B0..B7, Count, Freq, Desc
        
        # ID Button/Label
        lbl_id = ctk.CTkButton(self.monitor_scroll, text=f"{cid:X}", width=50, height=20, fg_color="transparent", 
                               command=lambda c=cid: self.on_monitor_click(c))
        lbl_id.grid(row=row_idx, column=0, padx=2, pady=1)
        widgets.append(lbl_id)
        
        # DLC
        lbl_dlc = ctk.CTkLabel(self.monitor_scroll, text="0", width=30)
        lbl_dlc.grid(row=row_idx, column=1, padx=2)
        widgets.append(lbl_dlc)
        
        # Bytes 0-7
        for i in range(8):
            lbl_b = ctk.CTkLabel(self.monitor_scroll, text="-", width=35, font=("Consolas", 12))
            lbl_b.grid(row=row_idx, column=2+i, padx=2)
            widgets.append(lbl_b)
            
        # Count
        lbl_cnt = ctk.CTkLabel(self.monitor_scroll, text="0", width=50)
        lbl_cnt.grid(row=row_idx, column=10, padx=2)
        widgets.append(lbl_cnt)
        
        # Freq
        lbl_fr = ctk.CTkLabel(self.monitor_scroll, text="0.0", width=50)
        lbl_fr.grid(row=row_idx, column=11, padx=2)
        widgets.append(lbl_fr)
        
        # Desc
        lbl_desc = ctk.CTkLabel(self.monitor_scroll, text="", anchor="w")
        lbl_desc.grid(row=row_idx, column=12, padx=2, sticky="ew")
        widgets.append(lbl_desc)
        
        self.monitor_rows[cid] = {"widgets": widgets}

    def on_monitor_click(self, can_id):
        self.selected_graph_source = "can"
        self.selected_graph_id = can_id
        # self.graph_data_points.clear() # Optional: Keep history or clear?
        print(f"Selected ID: {can_id:X}")

    def on_tree_select(self, event):
        # Deprecated
        pass

if __name__ == "__main__":
    app = ECMDiagnosticApp()
    app.mainloop()

