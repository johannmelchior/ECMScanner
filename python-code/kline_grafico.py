"""
kline_grafico.py — Yamaha K-Line Bus Reverse Engineering Visualizer
====================================================================
Lê um CSV gravado pelo modo SNIFF passivo do app, remonta o stream
de bytes, sincroniza nos frames Yamaha (55 02 XX 06 ...) e plota
cada byte ao longo do tempo.

Uso:
    python kline_grafico.py <arquivo.csv>
    python kline_grafico.py           # abre diálogo de ficheiro
"""

import csv
import sys
import tkinter as tk
from tkinter import filedialog, ttk
from datetime import datetime
import struct

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np

# ---------------------------------------------------------------------------
# Configuração dos campos do frame Yamaha
# Frame: 55 02 SEQ CMD TPS RPM_H RPM_L ECT IAT TL TH B11 B12 B13 B14 00 00 55 55 55 CHK 2C
#         0   1   2   3   4    5     6   7   8   9  10  11  12  13  14  15 16  17  18  19  20  21
# ---------------------------------------------------------------------------
FRAME_LEN   = 22
SYNC_MAGIC  = (0x55, 0x02)   # primeiros 2 bytes de um frame tipo 2
SYNC_MAGIC1 = (0x55, 0x01)   # primeiros 2 bytes de um frame tipo 1 (painel→ECM)

FIELDS = [
    # (nome,          índice, fator, offset, unidade,        cor)
    ("SEQ",            2,     1,      0,     "counter",      "#AAAAAA"),
    ("CMD/Type",       3,     1,      0,     "",             "#888888"),
    ("TPS/Throttle",   4,     100/255,0,     "%",            "#00FF88"),
    ("RPM high",       5,     1,      0,     "raw",          "#FF8800"),
    ("RPM low",        6,     1,      0,     "raw",          "#FFAA00"),
    ("ECT (raw)",      7,     1,      0,     "raw",          "#FF4444"),
    ("IAT (raw)",      8,     1,      0,     "raw",          "#44AAFF"),
    ("Timer low",      9,     1,      0,     "raw",          "#888800"),
    ("Timer high",    10,     1,      0,     "raw",          "#444400"),
    ("B11",           11,     1,      0,     "raw",          "#CC44CC"),
    ("B12",           12,     1,      0,     "raw",          "#AA22AA"),
    ("B13",           13,     1,      0,     "raw",          "#880088"),
    ("B14",           14,     1,      0,     "raw",          "#660066"),
    ("CHK",           20,     1,      0,     "raw",          "#333333"),
]

# Campos derivados calculados depois
DERIVED = [
    # (nome,       função(frame_bytes),              unidade, cor)
    ("RPM (calc)", lambda f: (f[5] * 256 + f[6]),   "RPM",   "#FF6600"),
    ("ECT °C",     lambda f: (f[7] - 48) / 1.6,     "°C",    "#FF2222"),
    ("IAT °C",     lambda f: (f[8] - 48) / 1.6,     "°C",    "#2288FF"),
    ("Timer ms",   lambda f: (f[9] + f[10]*256),    "ms",    "#AAAA00"),
    ("TPS %",      lambda f: round(f[4] * 100/255, 1), "%",  "#00DD66"),
    ("B11 int",    lambda f: f[11],                  "raw",   "#CC44CC"),
    ("B12 int",    lambda f: f[12],                  "raw",   "#AA22AA"),
]


# ---------------------------------------------------------------------------
# Parsing CSV → stream de bytes → frames
# ---------------------------------------------------------------------------

def parse_csv(path: str):
    """Retorna lista de (timestamp_s, bytes_list) com ID=KLINE-BUS."""
    rows = []
    t0 = None
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["ID"] not in ("KLINE-BUS", "KLINE-RX", "KLINE-TX"):
                continue
            ts_str = row["Timestamp"]
            try:
                t = datetime.strptime(ts_str, "%H:%M:%S.%f")
                ts = t.hour*3600 + t.minute*60 + t.second + t.microsecond/1e6
            except Exception:
                continue
            if t0 is None:
                t0 = ts
            ts -= t0
            data_hex = row["Data"].strip()
            try:
                blist = [int(x, 16) for x in data_hex.split()]
            except Exception:
                continue
            rows.append((ts, blist))
    return rows


def reassemble_stream(rows):
    """Concatena todos os bytes do CSV em um único stream com timestamps."""
    stream = []  # list of (timestamp_s, byte)
    for ts, blist in rows:
        for b in blist:
            stream.append((ts, b))
    return stream


def find_frames(stream):
    """
    Sincroniza no padrão 55 02 ou 55 01 e extrai frames de FRAME_LEN bytes.
    Retorna lista de (timestamp_s, frame_bytes_list).
    """
    frames = []
    i = 0
    n = len(stream)
    while i < n - FRAME_LEN:
        b0 = stream[i][1]
        b1 = stream[i+1][1] if i+1 < n else -1
        if b0 == 0x55 and b1 in (0x01, 0x02):
            frame = [stream[i+k][1] for k in range(FRAME_LEN)]
            ts    = stream[i][0]
            frames.append((ts, frame))
            i += FRAME_LEN  # skip to after this frame
        else:
            i += 1
    return frames


def extract_series(frames):
    """
    Retorna dict: {nome: (times[], values[])}
    """
    series = {d[0]: ([], []) for d in DERIVED}
    series["frame_type"] = ([], [])
    series["SEQ_raw"]    = ([], [])

    for ts, f in frames:
        if len(f) < FRAME_LEN:
            continue
        series["frame_type"][0].append(ts)
        series["frame_type"][1].append(f[1])  # 01 or 02
        series["SEQ_raw"][0].append(ts)
        series["SEQ_raw"][1].append(f[2])

        for name, fn, unit, color in DERIVED:
            try:
                val = fn(f)
            except Exception:
                val = float("nan")
            series[name][0].append(ts)
            series[name][1].append(val)

    return series


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class KLineVisualizer(tk.Tk):
    def __init__(self, csv_path: str):
        super().__init__()
        self.title(f"K-Line Reverse Engineering — {csv_path.split('/')[-1].split(chr(92))[-1]}")
        self.configure(bg="#1a1a1a")
        self.state("zoomed")

        rows   = parse_csv(csv_path)
        stream = reassemble_stream(rows)
        self.frames = find_frames(stream)

        if not self.frames:
            tk.Label(self, text="Nenhum frame Yamaha encontrado no CSV.",
                     fg="red", bg="#1a1a1a", font=("Arial", 16)).pack(expand=True)
            return

        self.series = extract_series(self.frames)
        self._build_ui(csv_path)

    def _build_ui(self, csv_path):
        # --- top info bar ---
        info = tk.Frame(self, bg="#111111")
        info.pack(fill="x", pady=(4, 0))
        n = len(self.frames)
        dur = self.frames[-1][0] - self.frames[0][0] if n > 1 else 0
        fps = n / dur if dur > 0 else 0
        tk.Label(info,
                 text=f"  {n} frames  |  {dur:.1f}s  |  {fps:.1f} fps  |  {csv_path}",
                 fg="#AAAAAA", bg="#111111", font=("Consolas", 10)).pack(side="left")

        # --- channel selector ---
        ctrl = tk.Frame(self, bg="#1a1a1a")
        ctrl.pack(fill="x", padx=8, pady=4)
        tk.Label(ctrl, text="Canais:", fg="white", bg="#1a1a1a",
                 font=("Arial", 10)).pack(side="left")

        self._channel_vars = {}
        colors = {d[0]: d[3] for d in DERIVED}
        colors["frame_type"] = "#FFFFFF"
        colors["SEQ_raw"]    = "#555555"

        for name in list(self.series.keys()):
            var = tk.BooleanVar(value=(name in ("RPM (calc)", "ECT °C", "IAT °C", "TPS %")))
            self._channel_vars[name] = var
            cb = tk.Checkbutton(ctrl, text=name, variable=var, command=self._redraw,
                                fg=colors.get(name, "#FFFFFF"), bg="#1a1a1a",
                                selectcolor="#333333", activebackground="#1a1a1a",
                                activeforeground="white", font=("Arial", 9))
            cb.pack(side="left", padx=4)

        # --- matplotlib figure ---
        self.fig = plt.Figure(figsize=(14, 8), facecolor="#111111")
        self.ax  = self.fig.add_subplot(111, facecolor="#0d0d0d")
        self.ax.tick_params(colors="#AAAAAA")
        for spine in self.ax.spines.values():
            spine.set_edgecolor("#333333")
        self.ax.set_xlabel("Tempo (s)", color="#AAAAAA")
        self.ax.set_ylabel("Valor", color="#AAAAAA")
        self.ax.grid(True, color="#1e1e1e", linestyle="--", linewidth=0.5)

        canvas_frame = tk.Frame(self, bg="#1a1a1a")
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=canvas_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        toolbar_frame = tk.Frame(canvas_frame, bg="#1a1a1a")
        toolbar_frame.pack(fill="x")
        NavigationToolbar2Tk(self.canvas, toolbar_frame)

        # --- raw frame table ---
        table_frame = tk.LabelFrame(self, text="Frames decodificados",
                                    fg="#AAAAAA", bg="#1a1a1a",
                                    font=("Arial", 9))
        table_frame.pack(fill="x", padx=8, pady=(0, 6))

        cols = ("t(s)", "type", "SEQ", "TPS%", "RPM", "ECT raw", "ECT°C", "IAT raw", "IAT°C", "Timer", "B11", "B12", "B13", "B14", "CHK")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=6)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#111111", foreground="#DDDDDD",
                        fieldbackground="#111111", rowheight=16, font=("Consolas", 9))
        style.configure("Treeview.Heading", background="#222222", foreground="#FFFFFF",
                        font=("Arial", 8, "bold"))

        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=70, anchor="center")
        self.tree.column("t(s)", width=60)

        sb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=sb.set)
        self.tree.pack(fill="x")
        sb.pack(fill="x")

        for ts, f in self.frames[:200]:  # show first 200 frames
            if len(f) < FRAME_LEN:
                continue
            rpm  = f[5] * 256 + f[6]
            ect  = f[7]
            ectc = round((ect - 48) / 1.6, 1)
            iat  = f[8]
            iatc = round((iat - 48) / 1.6, 1)
            tps  = round(f[4] * 100 / 255, 1)
            timer = f[9] + f[10] * 256
            row = (f"{ts:.2f}", f"0{f[1]:01X}", f"{f[2]:02X}", f"{tps}",
                   rpm, ect, ectc, iat, iatc, timer,
                   f"{f[11]:02X}", f"{f[12]:02X}", f"{f[13]:02X}", f"{f[14]:02X}",
                   f"{f[20]:02X}")
            self.tree.insert("", "end", values=row)

        self._redraw()

        # --- heatmap button ---
        hm_btn = tk.Button(info, text="  Heatmap de bytes  ", command=self._show_heatmap,
                           bg="#1a4a6e", fg="white", relief="flat", font=("Arial", 9),
                           cursor="hand2")
        hm_btn.pack(side="right", padx=8)

    def _show_heatmap(self):
        """Abre janela com heatmap de todos os frames (linhas) × bytes (colunas)."""
        from matplotlib.colors import Normalize
        from matplotlib.cm import ScalarMappable

        if not self.frames:
            return

        arr = np.array([f for _, f in self.frames if len(f) == FRAME_LEN], dtype=np.uint8)
        if arr.size == 0:
            return

        win = tk.Toplevel(self)
        win.title("Heatmap — Todos os bytes × Todos os frames")
        win.configure(bg="#111111")
        win.state("zoomed")

        fig2, axes = plt.subplots(1, 2, figsize=(16, 8),
                                  facecolor="#111111",
                                  gridspec_kw={"width_ratios": [3, 1]})

        # Left: heatmap
        ax_hm = axes[0]
        ax_hm.set_facecolor("#0d0d0d")
        im = ax_hm.imshow(arr, aspect="auto", interpolation="nearest",
                          cmap="plasma", origin="upper")
        ax_hm.set_xlabel("Byte offset no frame", color="#AAAAAA")
        ax_hm.set_ylabel("Frame #", color="#AAAAAA")
        ax_hm.set_title("Heatmap : frame × byte (plasma = valor 0→255)", color="#CCCCCC")
        ax_hm.tick_params(colors="#AAAAAA")
        ax_hm.set_xticks(range(FRAME_LEN))
        ax_hm.set_xticklabels([f"B{i}" for i in range(FRAME_LEN)], rotation=45, fontsize=8, color="#AAAAAA")
        fig2.colorbar(im, ax=ax_hm, label="valor byte")

        # Right: std-dev per column (spots the "interesting" bytes)
        ax_sd = axes[1]
        ax_sd.set_facecolor("#0d0d0d")
        stds = arr.std(axis=0)
        colors_bar = plt.cm.plasma(stds / max(stds.max(), 1))
        bars = ax_sd.barh(range(FRAME_LEN), stds, color=colors_bar)
        ax_sd.set_yticks(range(FRAME_LEN))
        ax_sd.set_yticklabels([f"B{i}" for i in range(FRAME_LEN)], fontsize=8, color="#AAAAAA")
        ax_sd.tick_params(colors="#AAAAAA")
        ax_sd.set_xlabel("Desvio padrão", color="#AAAAAA")
        ax_sd.set_title("Variância por byte\n(alto = dado dinâmico)", color="#CCCCCC")
        ax_sd.invert_yaxis()

        # Annotate bytes we already know
        known = {0:"SYNC", 1:"type", 2:"SEQ", 3:"CMD",
                 4:"TPS", 5:"RPM_H", 6:"RPM_L", 7:"ECT",
                 8:"IAT", 9:"TL", 10:"TH", 20:"CHK", 21:"term?"}
        for idx, label in known.items():
            if idx < FRAME_LEN:
                ax_sd.text(stds[idx] + 0.3, idx, label, va="center",
                           fontsize=7, color="#FFFF88")

        fig2.tight_layout(pad=1.5)

        canvas2 = FigureCanvasTkAgg(fig2, master=win)
        canvas2.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(canvas2, win)
        canvas2.draw()

    def _redraw(self):
        self.ax.cla()
        self.ax.set_facecolor("#0d0d0d")
        self.ax.tick_params(colors="#AAAAAA")
        for spine in self.ax.spines.values():
            spine.set_edgecolor("#333333")
        self.ax.set_xlabel("Tempo (s)", color="#AAAAAA")
        self.ax.set_ylabel("Valor", color="#AAAAAA")
        self.ax.grid(True, color="#1e1e1e", linestyle="--", linewidth=0.5)

        colors = {d[0]: d[3] for d in DERIVED}
        colors["frame_type"] = "#FFFFFF"
        colors["SEQ_raw"]    = "#555555"
        units  = {d[0]: d[2] for d in DERIVED}

        any_plotted = False
        for name, var in self._channel_vars.items():
            if not var.get():
                continue
            ts_list, val_list = self.series[name]
            if not ts_list:
                continue
            self.ax.plot(ts_list, val_list,
                         label=f"{name} ({units.get(name,'')})",
                         color=colors.get(name, "#FFFFFF"),
                         linewidth=1.2, marker=".", markersize=2)
            any_plotted = True

        if any_plotted:
            legend = self.ax.legend(facecolor="#111111", labelcolor="#DDDDDD",
                                    edgecolor="#333333", fontsize=8, loc="upper right")

        self.ax.set_title("Yamaha K-Line — Engenharia Reversa de Sensores",
                          color="#CCCCCC", fontsize=11)
        self.canvas.draw()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Selecione o CSV K-Line",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir="z:/projetoCAN"
        )
        root.destroy()
        if not path:
            print("Nenhum arquivo selecionado.")
            sys.exit(0)

    app = KLineVisualizer(path)
    app.mainloop()
