#!/usr/bin/env python3
"""Visualizador simples para logs K-Line Yamaha.

Carrega um arquivo de osciloscopio, decodifica bytes UART e extrai sequencias do tipo:
F8 -> canal -> valor

O app lista os canais encontrados e plota a evolucao temporal do canal selecionado.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from tkinter import filedialog, messagebox, ttk


THRESHOLD = 2.0
DEFAULT_BAUD = 15625
DEFAULT_CAPTURE_S = 5.0
PLOT_PADDING_X = 55
PLOT_PADDING_Y = 24


def load_capture(path: Path) -> tuple[list[int], float]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    clock_s = None
    size = None
    samples: list[float] = []

    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text.startswith("#CLOCK="):
            try:
                clock_s = float(text.split("=", 1)[1].split()[0])
            except Exception:
                clock_s = None
            continue
        if text.startswith("#SIZE="):
            try:
                size = int(text.split("=", 1)[1])
            except Exception:
                size = None
            continue
        if text.startswith("#"):
            continue
        samples.append(float(text))

    if not samples:
        raise ValueError(f"arquivo sem amostras: {path}")

    if clock_s and size:
        sample_period_us = clock_s * 1e6 / size
    else:
        sample_period_us = DEFAULT_CAPTURE_S * 1e6 / len(samples)

    bits = [1 if value > THRESHOLD else 0 for value in samples]
    return bits, sample_period_us


def find_active_start(bits: list[int]) -> int:
    for index in range(1, len(bits) - 10):
        if bits[index] == 1 and all(bits[index + offset] == 1 for offset in range(5)):
            return index
    return 0


def decode_uart(bits: list[int], sample_period_us: float, baud: int, start_index: int) -> list[tuple[float, int, bool]]:
    bit_samples = (1e6 / baud) / sample_period_us
    decoded: list[tuple[float, int, bool]] = []
    index = max(1, start_index)
    limit = len(bits) - int(10 * bit_samples) - 2

    while index < limit:
        if bits[index - 1] == 1 and bits[index] == 0:
            byte_value = 0
            valid = True
            for bit_number in range(8):
                sample_pos = int(index + (bit_number + 1.5) * bit_samples)
                if sample_pos >= len(bits):
                    valid = False
                    break
                byte_value |= bits[sample_pos] << bit_number

            stop_pos = int(index + 9.5 * bit_samples)
            stop_ok = stop_pos < len(bits) and bits[stop_pos] == 1

            if valid:
                decoded.append((index * sample_period_us / 1000.0, byte_value, stop_ok))
                index = max(index + 1, int(index + 10 * bit_samples))
                continue
        index += 1

    return decoded


def extract_f8_channels(decoded: list[tuple[float, int, bool]]) -> dict[int, list[tuple[float, int, int]]]:
    valid = [(timestamp_ms, byte_value) for timestamp_ms, byte_value, stop_ok in decoded if stop_ok]
    channels: dict[int, list[tuple[float, int, int]]] = defaultdict(list)

    for index in range(len(valid) - 2):
        timestamp_ms, byte0 = valid[index]
        _, byte1 = valid[index + 1]
        _, byte2 = valid[index + 2]
        if byte0 == 0xF8 and byte1 not in (0xF8, 0xFF):
            channels[byte1].append((timestamp_ms, byte2, byte2 & 0x7F))

    return dict(channels)


class KLineVisualizer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("K-Line Byte Visualizer")
        self.geometry("1180x760")

        self.file_path: Path | None = None
        self.channels: dict[int, list[tuple[float, int, int]]] = {}
        self.channel_keys: list[int] = []

        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self.status_var = tk.StringVar(value="Abra um log Yamaha para visualizar os canais.")
        self.show_raw_var = tk.BooleanVar(value=True)
        self.show_base_var = tk.BooleanVar(value=True)
        self.connect_points_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self) -> None:
        controls = ttk.Frame(self, padding=10)
        controls.pack(fill="x")

        ttk.Button(controls, text="Abrir Log", command=self.open_file).pack(side="left")
        ttk.Label(controls, text="Baud:").pack(side="left", padx=(10, 4))
        ttk.Entry(controls, textvariable=self.baud_var, width=8).pack(side="left")
        ttk.Button(controls, text="Recarregar", command=self.reload_file).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(controls, text="Raw", variable=self.show_raw_var, command=self.redraw_plot).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(controls, text="Base (v & 0x7F)", variable=self.show_base_var, command=self.redraw_plot).pack(side="left")
        ttk.Checkbutton(controls, text="Ligar pontos", variable=self.connect_points_var, command=self.redraw_plot).pack(side="left")

        ttk.Label(self, textvariable=self.status_var, padding=(10, 0, 10, 8)).pack(fill="x")

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(main, padding=8)
        right = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        main.add(right, weight=4)

        ttk.Label(left, text="Canais F8 -> canal -> valor", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.channel_list = tk.Listbox(left, exportselection=False, width=34, height=20)
        self.channel_list.pack(fill="both", expand=True, pady=(6, 8))
        self.channel_list.bind("<<ListboxSelect>>", self.on_channel_select)

        ttk.Label(left, text="Resumo", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.summary_text = tk.Text(left, height=18, width=34, wrap="word")
        self.summary_text.pack(fill="both", expand=True, pady=(6, 0))
        self.summary_text.configure(state="disabled")

        ttk.Label(right, text="Serie temporal", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.canvas = tk.Canvas(right, bg="#111111", highlightthickness=1, highlightbackground="#333333")
        self.canvas.pack(fill="both", expand=True, pady=(6, 8))
        self.canvas.bind("<Configure>", lambda _event: self.redraw_plot())

        legend = ttk.Label(
            right,
            text="Azul = valor bruto | Verde = valor base (v & 0x7F) | eixo X = tempo | eixo Y = valor do byte",
        )
        legend.pack(anchor="w")

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione o log K-Line",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not path:
            return
        self.file_path = Path(path)
        self.reload_file()

    def reload_file(self) -> None:
        if self.file_path is None:
            self.status_var.set("Nenhum arquivo carregado.")
            return

        try:
            baud = int(self.baud_var.get().strip())
        except ValueError:
            messagebox.showerror("Baud invalido", "Informe um baud inteiro, por exemplo 15625.")
            return

        try:
            bits, sample_period_us = load_capture(self.file_path)
            start_index = find_active_start(bits)
            decoded = decode_uart(bits, sample_period_us, baud, start_index)
            self.channels = extract_f8_channels(decoded)
            self.channel_keys = sorted(self.channels)
        except Exception as exc:
            messagebox.showerror("Erro ao carregar log", str(exc))
            return

        self.channel_list.delete(0, tk.END)
        for channel in self.channel_keys:
            samples = self.channels[channel]
            base_values = [value for _, _, value in samples]
            self.channel_list.insert(
                tk.END,
                f"0x{channel:02X}  amostras={len(samples):4d}  min={min(base_values):3d}  max={max(base_values):3d}",
            )

        if self.channel_keys:
            self.channel_list.selection_clear(0, tk.END)
            self.channel_list.selection_set(0)
            self.channel_list.activate(0)
            self.on_channel_select()

        self.status_var.set(
            f"{self.file_path.name} | baud={baud} | canais={len(self.channel_keys)} | selecione um canal para visualizar"
        )

    def on_channel_select(self, _event: object | None = None) -> None:
        selection = self.channel_list.curselection()
        if not selection:
            return
        channel = self.channel_keys[selection[0]]
        self.update_summary(channel)
        self.redraw_plot()

    def update_summary(self, channel: int) -> None:
        samples = self.channels[channel]
        raw_values = [raw for _, raw, _ in samples]
        base_values = [base for _, _, base in samples]
        raw_counter = Counter(raw_values)
        base_counter = Counter(base_values)
        transitions = sum(1 for index in range(1, len(base_values)) if base_values[index] != base_values[index - 1])

        lines = [
            f"Canal 0x{channel:02X}",
            f"Amostras: {len(samples)}",
            f"Tempo: {samples[0][0]:.3f} ms .. {samples[-1][0]:.3f} ms",
            f"Base min/max: {min(base_values)} / {max(base_values)}",
            f"Base media/mediana: {mean(base_values):.2f} / {median(base_values):.2f}",
            f"Transicoes base: {transitions}",
            "",
            "Top raw:",
        ]

        for value, count in raw_counter.most_common(8):
            lines.append(f"  0x{value:02X} ({value:3d}) : {count}")

        lines.extend(["", "Top base:"])
        for value, count in base_counter.most_common(8):
            lines.append(f"  {value:3d} (0x{value:02X}) : {count}")

        lines.extend(["", "Primeiras amostras:"])
        for timestamp_ms, raw_value, base_value in samples[:10]:
            lines.append(f"  {timestamp_ms:8.3f} ms  raw=0x{raw_value:02X}  base={base_value:3d}")

        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert("1.0", "\n".join(lines))
        self.summary_text.configure(state="disabled")

    def redraw_plot(self) -> None:
        self.canvas.delete("all")
        selection = self.channel_list.curselection()
        if not selection:
            self.draw_message("Sem canal selecionado")
            return

        channel = self.channel_keys[selection[0]]
        samples = self.channels[channel]
        if len(samples) < 2:
            self.draw_message("Dados insuficientes para plot")
            return

        width = max(200, self.canvas.winfo_width())
        height = max(200, self.canvas.winfo_height())
        left = PLOT_PADDING_X
        right = width - PLOT_PADDING_X
        top = PLOT_PADDING_Y
        bottom = height - PLOT_PADDING_Y - 20

        times = [timestamp_ms for timestamp_ms, _, _ in samples]
        raw_values = [raw for _, raw, _ in samples]
        base_values = [base for _, _, base in samples]
        min_time = times[0]
        max_time = times[-1]
        min_value = 0
        max_value = max(max(raw_values), max(base_values), 127)
        span_time = max(max_time - min_time, 1e-9)
        span_value = max(max_value - min_value, 1)

        self.canvas.create_rectangle(left, top, right, bottom, outline="#666666")

        for grid in range(6):
            x = left + (right - left) * grid / 5
            y = top + (bottom - top) * grid / 5
            self.canvas.create_line(x, top, x, bottom, fill="#222222")
            self.canvas.create_line(left, y, right, y, fill="#222222")

        for grid in range(6):
            x = left + (right - left) * grid / 5
            t_label = min_time + span_time * grid / 5
            self.canvas.create_text(x, bottom + 14, text=f"{t_label:.0f} ms", fill="#cccccc", font=("Consolas", 9))

            y = bottom - (bottom - top) * grid / 5
            v_label = min_value + span_value * grid / 5
            self.canvas.create_text(left - 28, y, text=f"{v_label:.0f}", fill="#cccccc", font=("Consolas", 9))

        if self.show_raw_var.get():
            self.draw_series(samples, raw_values, min_time, span_time, min_value, span_value, left, top, right, bottom, "#4ea3ff")
        if self.show_base_var.get():
            self.draw_series(samples, base_values, min_time, span_time, min_value, span_value, left, top, right, bottom, "#5fe07a")

        self.canvas.create_text(
            left + 8,
            top + 10,
            anchor="w",
            text=f"Canal 0x{channel:02X} | amostras={len(samples)}",
            fill="#ffffff",
            font=("Segoe UI", 10, "bold"),
        )

    def draw_series(
        self,
        samples: list[tuple[float, int, int]],
        values: list[int],
        min_time: float,
        span_time: float,
        min_value: int,
        span_value: int,
        left: int,
        top: int,
        right: int,
        bottom: int,
        color: str,
    ) -> None:
        coords: list[tuple[float, float]] = []
        for (timestamp_ms, _, _), value in zip(samples, values):
            x = left + (timestamp_ms - min_time) / span_time * (right - left)
            y = bottom - (value - min_value) / span_value * (bottom - top)
            coords.append((x, y))

        if self.connect_points_var.get() and len(coords) >= 2:
            flattened = [coord for pair in coords for coord in pair]
            self.canvas.create_line(*flattened, fill=color, width=2, smooth=False)

        radius = 2
        step = max(1, math.ceil(len(coords) / 800))
        for x, y in coords[::step]:
            self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="")

    def draw_message(self, message: str) -> None:
        width = max(200, self.canvas.winfo_width())
        height = max(200, self.canvas.winfo_height())
        self.canvas.create_text(width / 2, height / 2, text=message, fill="#cccccc", font=("Segoe UI", 11))


def main() -> None:
    app = KLineVisualizer()
    app.mainloop()


if __name__ == "__main__":
    main()