import ctypes
import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import keyboard
import mouse
import pyautogui

# ── Configuração do pyautogui ────────────────────────────────────────────────
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True  # mova o mouse para o canto superior-esquerdo para abortar

# ── Win32 para posição precisa do mouse ──────────────────────────────────────
try:
    _user32 = ctypes.windll.user32
    _user32.SetProcessDPIAware()  # evita escalonamento de DPI

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def _get_cursor_pos():
        pt = _POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
except Exception:
    def _get_cursor_pos():
        return mouse.get_position()

# ── Constantes ───────────────────────────────────────────────────────────────
DEFAULT_FILE = "events.json"
MOVE_THRESHOLD_PX = 3          # ignora micro-movimentos menores que 3 px
MOVE_MIN_INTERVAL = 0.015      # intervalo mínimo entre movimentos gravados (s)
HOTKEY_RECORD = "F9"
HOTKEY_PLAY = "F10"
HOTKEY_STOP = "F11"

# Win32 — constantes para scroll
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
WHEEL_DELTA = 120              # unidade padrão do Windows por "notch"

# ── Classe principal ─────────────────────────────────────────────────────────
class MacroRecorderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Automator - by: dbener")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self.events: list[dict] = []
        self.recording = False
        self.playing = False
        self.stop_flag = False
        self._start_time = 0.0
        self._last_move_time = 0.0
        self._last_move_pos = (0, 0)
        self._pressed_keys: set[str] = set()  # teclas atualmente pressionadas
        self._iteration_count = 0

        self._build_ui()
        self._build_mini_bar()
        self._register_hotkeys()

    # ── Interface gráfica ────────────────────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style()
        style.configure("Rec.TButton", foreground="red")

        # --- Toolbar ---
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(fill=tk.X)

        self.btn_record = ttk.Button(
            toolbar, text=f"⏺ Gravar ({HOTKEY_RECORD})", width=18,
            style="Rec.TButton", command=self._toggle_record)
        self.btn_record.pack(side=tk.LEFT, padx=2)

        self.btn_play = ttk.Button(
            toolbar, text=f"▶ Reproduzir ({HOTKEY_PLAY})", width=18,
            command=self._toggle_play)
        self.btn_play.pack(side=tk.LEFT, padx=2)

        self.btn_stop = ttk.Button(
            toolbar, text=f"⏹ Parar ({HOTKEY_STOP})", width=14,
            command=self._stop_all, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=2)

        # --- Opções ---
        opts = ttk.LabelFrame(self.root, text="Opções", padding=8)
        opts.pack(fill=tk.X, padx=8, pady=(4, 2))

        # Velocidade
        row0 = ttk.Frame(opts)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="Velocidade:").pack(side=tk.LEFT)
        self.speed_var = tk.DoubleVar(value=1.0)
        speeds = [0.25, 0.5, 1.0, 1.5, 2.0, 4.0, 8.0]
        self.speed_combo = ttk.Combobox(
            row0, textvariable=self.speed_var, values=speeds, width=6, state="readonly")
        self.speed_combo.set("1.0")
        self.speed_combo.pack(side=tk.LEFT, padx=6)
        ttk.Label(row0, text="x").pack(side=tk.LEFT)

        # Repetições
        row1 = ttk.Frame(opts)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Repetições:").pack(side=tk.LEFT)
        self.repeat_var = tk.IntVar(value=1)
        self.repeat_spin = ttk.Spinbox(row1, from_=1, to=9999, width=6,
                                       textvariable=self.repeat_var)
        self.repeat_spin.pack(side=tk.LEFT, padx=6)
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="Loop infinito",
                        variable=self.loop_var).pack(side=tk.LEFT, padx=6)

        # Gravar movimentos
        row2 = ttk.Frame(opts)
        row2.pack(fill=tk.X, pady=2)
        self.rec_moves_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="Gravar movimentos do mouse",
                        variable=self.rec_moves_var).pack(side=tk.LEFT)

        # --- Arquivo ---
        file_frame = ttk.LabelFrame(self.root, text="Arquivo", padding=8)
        file_frame.pack(fill=tk.X, padx=8, pady=(2, 4))

        self.file_var = tk.StringVar(value=os.path.abspath(DEFAULT_FILE))
        ttk.Entry(file_frame, textvariable=self.file_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(file_frame, text="Salvar como…",
                   command=self._save_as).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_frame, text="Abrir…",
                   command=self._open_file).pack(side=tk.LEFT, padx=2)

        # --- Status bar ---
        self.status_var = tk.StringVar(value="Pronto")
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W, padding=4)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # --- Event list ---
        list_frame = ttk.LabelFrame(self.root, text="Eventos gravados", padding=4)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        cols = ("n", "tipo", "detalhe", "tempo")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                 height=12)
        self.tree.heading("n", text="#")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("detalhe", text="Detalhe")
        self.tree.heading("tempo", text="Tempo (s)")
        self.tree.column("n", width=40, anchor=tk.CENTER)
        self.tree.column("tipo", width=100)
        self.tree.column("detalhe", width=220)
        self.tree.column("tempo", width=80, anchor=tk.E)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ── Mini-bar flutuante ────────────────────────────────────────────────────
    def _build_mini_bar(self):
        """Cria a barra compacta que aparece no canto superior-esquerdo
        durante gravação ou reprodução."""
        self._minibar = tk.Toplevel(self.root)
        self._minibar.title("Macro")
        self._minibar.overrideredirect(True)          # sem borda / barra de título
        self._minibar.attributes("-topmost", True)
        self._minibar.attributes("-alpha", 0.92)
        self._minibar.withdraw()                      # começa escondida

        bar = tk.Frame(self._minibar, bg="#1e1e1e", padx=8, pady=4)
        bar.pack(fill=tk.BOTH, expand=True)

        self._mini_label = tk.Label(
            bar, text="", fg="white", bg="#1e1e1e",
            font=("Segoe UI", 10, "bold"), anchor=tk.W)
        self._mini_label.pack(side=tk.LEFT, padx=(0, 10))

        self._mini_iter_label = tk.Label(
            bar, text="", fg="#aaaaaa", bg="#1e1e1e",
            font=("Segoe UI", 9), anchor=tk.W)
        self._mini_iter_label.pack(side=tk.LEFT, padx=(0, 10))

        self._mini_hotkey_label = tk.Label(
            bar, text="", fg="#888888", bg="#1e1e1e",
            font=("Segoe UI", 9), anchor=tk.W)
        self._mini_hotkey_label.pack(side=tk.LEFT, padx=(0, 10))

        self._mini_stop_btn = tk.Button(
            bar, text="⏹ Parar", fg="white", bg="#c0392b",
            activebackground="#e74c3c", activeforeground="white",
            font=("Segoe UI", 9, "bold"), bd=0, padx=10, pady=2,
            command=self._stop_all)
        self._mini_stop_btn.pack(side=tk.LEFT, padx=(0, 4))

    def _show_mini_bar(self, mode: str):
        """Esconde a janela principal e mostra a mini-bar.
        mode: 'recording' ou 'playing'"""
        self.root.withdraw()

        if mode == "recording":
            self._mini_label.config(text="🔴 Gravando", fg="#ff4444")
            self._mini_iter_label.config(text="")
            self._mini_hotkey_label.config(
                text=f"{HOTKEY_STOP} ou ESC = Parar")
        else:
            self._mini_label.config(text="▶ Reproduzindo", fg="#44ff44")
            self._mini_iter_label.config(text="Iteração: 0")
            self._mini_hotkey_label.config(
                text=f"{HOTKEY_STOP} = Parar")

        # Posiciona no canto superior-esquerdo
        self._minibar.geometry("+4+4")
        self._minibar.deiconify()
        self._minibar.lift()

    def _update_mini_bar_iteration(self, n: int):
        """Atualiza o contador de iterações na mini-bar (thread-safe via after)."""
        self._mini_iter_label.config(text=f"Iteração: {n}")

    def _hide_mini_bar(self):
        """Esconde a mini-bar e restaura a janela principal."""
        self._minibar.withdraw()
        self.root.deiconify()
        self.root.lift()

    # ── Hotkeys globais ──────────────────────────────────────────────────────
    def _register_hotkeys(self):
        keyboard.add_hotkey(HOTKEY_RECORD, self._toggle_record, suppress=True)
        keyboard.add_hotkey(HOTKEY_PLAY, self._toggle_play, suppress=True)
        keyboard.add_hotkey(HOTKEY_STOP, self._stop_all, suppress=True)

    # ── Gravar ───────────────────────────────────────────────────────────────
    def _toggle_record(self):
        if self.playing:
            return
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self.events.clear()
        self._pressed_keys.clear()
        self.recording = True
        self._start_time = time.time()
        self._last_move_time = 0.0
        self._last_move_pos = _get_cursor_pos()

        self.btn_record.config(text="⏺ Gravando…", state=tk.DISABLED)
        self.btn_play.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_var.set("🔴 Gravando… Pressione F11 ou ESC para parar.")
        self._clear_tree()
        self._show_mini_bar("recording")

        # hooks
        keyboard.hook(self._on_key_event)
        mouse.hook(self._on_mouse_event)

    def _stop_recording(self):
        self.recording = False
        keyboard.unhook_all()
        mouse.unhook_all()

        # Remove eventos das hotkeys de controle no final
        self._filter_control_keys()

        self._save_events()
        self._populate_tree()

        self.btn_record.config(text=f"⏺ Gravar ({HOTKEY_RECORD})", state=tk.NORMAL)
        self.btn_play.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set(f"Gravação finalizada — {len(self.events)} eventos salvos.")
        self._hide_mini_bar()
        self._register_hotkeys()

    def _filter_control_keys(self):
        """Remove eventos de F9/F10/F11 que são hotkeys do app."""
        hotkeys = {HOTKEY_RECORD.lower(), HOTKEY_PLAY.lower(), HOTKEY_STOP.lower(), "esc"}
        self.events = [e for e in self.events
                       if not (e["type"] in ("key_down", "key_up")
                               and e.get("key", "").lower() in hotkeys)]

    # ── Callbacks de gravação ────────────────────────────────────────────────
    def _on_key_event(self, event: keyboard.KeyboardEvent):
        if not self.recording:
            return
        # ESC para parar gravação
        if event.name and event.name.lower() == "esc":
            self.root.after(0, self._stop_recording)
            return

        ts = time.time() - self._start_time
        if event.event_type == "down":
            if event.name not in self._pressed_keys:
                self._pressed_keys.add(event.name)
                self.events.append({
                    "type": "key_down",
                    "key": event.name,
                    "scan_code": event.scan_code,
                    "time": ts
                })
        else:  # up
            self._pressed_keys.discard(event.name)
            self.events.append({
                "type": "key_up",
                "key": event.name,
                "scan_code": event.scan_code,
                "time": ts
            })

    def _on_mouse_event(self, event):
        if not self.recording:
            return
        ts = time.time() - self._start_time

        if isinstance(event, mouse.MoveEvent):
            if not self.rec_moves_var.get():
                return
            x, y = event.x, event.y
            dx = abs(x - self._last_move_pos[0])
            dy = abs(y - self._last_move_pos[1])
            if dx < MOVE_THRESHOLD_PX and dy < MOVE_THRESHOLD_PX:
                return
            if (ts - self._last_move_time) < MOVE_MIN_INTERVAL:
                return
            self._last_move_time = ts
            self._last_move_pos = (x, y)
            self.events.append({
                "type": "mouse_move",
                "x": x, "y": y,
                "time": ts
            })

        elif isinstance(event, mouse.ButtonEvent):
            x, y = _get_cursor_pos()
            self.events.append({
                "type": "mouse_click",
                "x": x, "y": y,
                "button": event.button,
                "pressed": event.event_type == "down",
                "time": ts
            })

        elif isinstance(event, mouse.WheelEvent):
            x, y = _get_cursor_pos()
            self.events.append({
                "type": "mouse_scroll",
                "x": x, "y": y,
                "delta": event.delta,
                "time": ts
            })

    # ── Reproduzir ───────────────────────────────────────────────────────────
    def _toggle_play(self):
        if self.recording:
            return
        if self.playing:
            self._stop_all()
        else:
            self._start_play()

    def _start_play(self):
        filepath = self.file_var.get()
        if not os.path.isfile(filepath):
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{filepath}")
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                events = json.load(f)
        except Exception as e:
            messagebox.showerror("Erro ao ler arquivo", str(e))
            return
        if not events:
            messagebox.showinfo("Aviso", "Nenhum evento para reproduzir.")
            return

        self.playing = True
        self.stop_flag = False
        self._iteration_count = 0
        self.btn_play.config(text="▶ Reproduzindo…", state=tk.DISABLED)
        self.btn_record.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self._show_mini_bar("playing")

        speed = self.speed_var.get()
        repeats = self.repeat_var.get()
        loop = self.loop_var.get()

        thread = threading.Thread(
            target=self._replay_worker,
            args=(events, speed, repeats, loop),
            daemon=True)
        thread.start()

    def _replay_worker(self, events, speed, repeats, loop):
        iteration = 0
        try:
            while not self.stop_flag:
                iteration += 1
                self._iteration_count = iteration
                self.root.after(0, self.status_var.set,
                                f"▶ Reproduzindo… iteração {iteration}")
                self.root.after(0, self._update_mini_bar_iteration, iteration)
                start = time.time()
                for ev in events:
                    if self.stop_flag:
                        break
                    target = ev["time"] / speed
                    elapsed = time.time() - start
                    delay = target - elapsed
                    if delay > 0:
                        # dormir em fatias pequenas para poder parar rápido
                        end_sleep = time.time() + delay
                        while time.time() < end_sleep:
                            if self.stop_flag:
                                break
                            time.sleep(min(0.01, end_sleep - time.time()))

                    if self.stop_flag:
                        break
                    self._execute_event(ev)

                if not loop:
                    repeats -= 1
                    if repeats <= 0:
                        break
        finally:
            self.root.after(0, self._on_play_finished)

    def _execute_event(self, ev):
        t = ev["type"]
        if t == "mouse_move":
            ctypes.windll.user32.SetCursorPos(int(ev["x"]), int(ev["y"]))
        elif t == "mouse_click":
            ctypes.windll.user32.SetCursorPos(int(ev["x"]), int(ev["y"]))
            time.sleep(0.002)  # pequena pausa para o cursor achar a posição
            if ev["pressed"]:
                pyautogui.mouseDown(button=ev["button"], _pause=False)
            else:
                pyautogui.mouseUp(button=ev["button"], _pause=False)
        elif t == "mouse_scroll":
            ctypes.windll.user32.SetCursorPos(int(ev["x"]), int(ev["y"]))
            # Usa Win32 mouse_event diretamente para fidelidade total no scroll.
            # dwData precisa ser múltiplo de WHEEL_DELTA (120) para o Windows.
            dw = ctypes.c_long(int(ev["delta"] * WHEEL_DELTA))
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, dw, 0)
        elif t == "key_down":
            keyboard.press(ev["key"])
        elif t == "key_up":
            keyboard.release(ev["key"])
        elif t == "key_press":
            # compatibilidade com eventos antigos
            keyboard.press_and_release(ev["key"])

    def _on_play_finished(self):
        total = self._iteration_count
        self.playing = False
        self.stop_flag = False
        self.btn_play.config(text=f"▶ Reproduzir ({HOTKEY_PLAY})", state=tk.NORMAL)
        self.btn_record.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set(f"Reprodução finalizada — {total} iterações realizadas.")
        self._hide_mini_bar()

    # ── Parar tudo ───────────────────────────────────────────────────────────
    def _stop_all(self):
        if self.recording:
            self._stop_recording()
        if self.playing:
            self.stop_flag = True

    # ── Arquivo ──────────────────────────────────────────────────────────────
    def _save_events(self):
        filepath = self.file_var.get()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.events, f, indent=4, ensure_ascii=False)

    def _save_as(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if path:
            self.file_var.set(path)
            if self.events:
                self._save_events()

    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if path:
            self.file_var.set(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.events = json.load(f)
                self._populate_tree()
                self.status_var.set(f"Arquivo carregado — {len(self.events)} eventos.")
            except Exception as e:
                messagebox.showerror("Erro", str(e))

    # ── Treeview ─────────────────────────────────────────────────────────────
    def _clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _populate_tree(self):
        self._clear_tree()
        for i, ev in enumerate(self.events, 1):
            t = ev["type"]
            if t == "mouse_move":
                detail = f"({ev['x']}, {ev['y']})"
            elif t == "mouse_click":
                action = "↓" if ev.get("pressed") else "↑"
                detail = f"{ev.get('button','left')} {action} ({ev['x']}, {ev['y']})"
            elif t == "mouse_scroll":
                detail = f"delta={ev.get('delta',0)} ({ev['x']}, {ev['y']})"
            elif t in ("key_down", "key_up"):
                arrow = "↓" if t == "key_down" else "↑"
                detail = f"{ev['key']} {arrow}"
            elif t == "key_press":
                detail = ev["key"]
            else:
                detail = str(ev)

            tipo_map = {
                "mouse_move": "Mouse Move",
                "mouse_click": "Mouse Click",
                "mouse_scroll": "Scroll",
                "key_down": "Tecla ↓",
                "key_up": "Tecla ↑",
                "key_press": "Tecla",
            }
            self.tree.insert("", tk.END, values=(
                i, tipo_map.get(t, t), detail, f"{ev['time']:.3f}"))

    # ── Encerrar ─────────────────────────────────────────────────────────────
    def on_close(self):
        self.stop_flag = True
        self.recording = False
        try:
            keyboard.unhook_all()
            mouse.unhook_all()
        except Exception:
            pass
        try:
            self._minibar.destroy()
        except Exception:
            pass
        self.root.destroy()


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = MacroRecorderApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop() 
