"""
radar_visualizer.py — DEFCON Centro de Mando Táctico
Interfaz gráfica de visualización del sistema radar distribuido.
Escucha el broadcast UDP en 127.0.0.1:8081 emitido por server_central.py.

Dependencias: tkinter (built-in), socket, json, threading, math
"""
import tkinter as tk
import socket
import json
import threading
import math
import time
import subprocess
import sys
import os
import codecs

# ── Escalado de interfaz (pantallas HiDPI / Retina) ─────────────────────────────
UI_SCALE = 1.15   # afecta solo tamaños de fuente


def F(pt: int) -> int:
    """Tamaño de fuente escalado según UI_SCALE."""
    return max(6, round(pt * UI_SCALE))


# ── Dimensiones ───────────────────────────────────────────────────────────────
# Mismo ancho/alto TOTAL que el original (1620x820, ya validado en pantalla);
# se le resta espacio al canvas para dárselo al panel y evitar que el texto
# de las tarjetas de nodo se corte.
CANVAS_W = 1140
CANVAS_H = 820
PANEL_W  = 480
TOTAL_W  = CANVAS_W + PANEL_W
TOTAL_H  = CANVAS_H

UDP_PORT = 8081

CX = CANVAS_W // 2
CY = CANVAS_H - 90   # línea base visible con margen inferior

# ── Paleta ────────────────────────────────────────────────────────────────────
C_BG        = '#0a0a0a'
C_PANEL     = '#111111'
C_CARD      = '#1c1c1c'
C_BORDER    = '#2a2a2a'
C_WHITE     = '#ffffff'
C_GREEN     = '#00e676'
C_ORANGE    = '#ff6b35'
C_ZONE_BG   = '#0a2e0a'
C_GROUND    = '#0d1a0d'
C_BASELINE  = '#37474F'
C_PERIM     = '#1565c0'
C_VALLA     = '#4caf50'
C_D3        = '#f9a825'
C_D2        = '#ef6c00'
C_D1        = '#c62828'
C_NODE_ARC  = '#546E7A'

# Color de haz y borde por nodo
NODE_BEAM_FILL  = {1: '#0d2d3d', 2: '#0f3d0f', 3: '#2d1a0a'}
NODE_BEAM_EDGE  = {1: '#29B6F6', 2: '#66BB6A', 3: '#FFA726'}
NODE_DIAMOND_C  = {1: '#29B6F6', 2: '#66BB6A', 3: '#FFA726'}

# ── Valores por defecto ───────────────────────────────────────────────────────
DEFAULTS = {
    'zoom':     8.0,
    'perim':    8.0,   # radio del arco donde se sitúan los nodos (cm)
    'defcon1':  20.0,
    'defcon2':  35.0,
    'defcon3':  50.0,
    'valla':    65.0,
    'apertura': 90.0,
}

# Ángulos iniciales en canvas (grados, 0=derecha, antihorario)
NODE_CANVAS_ANGLE_DEFAULT = {1: 144, 2: 90, 3: 36}


# Posiciones físicas para proyección de hits en live mode
NODE_PHYS = {
    1: {'x': -25.0, 'y': 15.0, 'theta': 144.0},   # izquierda
    2: {'x':   0.0, 'y': 28.0, 'theta':  90.0},   # centro
    3: {'x':  25.0, 'y': 15.0, 'theta':  36.0},   # derecha
}

NODE_HIT_RADIUS = 18   # píxeles para detectar clic sobre nodo

# Rutas del servidor (relativas a este fichero)
_TOOLS_DIR      = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH     = os.path.normpath(os.path.join(_TOOLS_DIR, '..', 'server', 'server_central.py'))
SERVER_WD       = os.path.normpath(os.path.join(_TOOLS_DIR, '..'))
SERVER_LOG      = os.path.join(SERVER_WD, 'server', 'server.log')
SETTINGS_FILE   = os.path.join(_TOOLS_DIR, 'visualizer_settings.json')


class FlatButton(tk.Label):
    """Botón con bg/fg 100% custom. macOS/Aqua ignora bg y activebackground
    en tk.Button (no tiene chrome nativo propio), así que se simula con un
    Label clickeable — funciona igual en Windows."""

    def __init__(self, parent, command=None, **kwargs):
        kwargs.setdefault('cursor', 'hand2')
        kwargs.setdefault('pady', 8)
        super().__init__(parent, **kwargs)
        self._command   = command
        self._normal_bg = kwargs.get('bg', kwargs.get('background', self.cget('bg')))
        self.bind('<Button-1>', lambda e: self._command() if self._command else None)
        self.bind('<Enter>', lambda e: tk.Label.config(self, bg=self.cget('activebackground')))
        self.bind('<Leave>', lambda e: tk.Label.config(self, bg=self._normal_bg))

    def config(self, **kwargs):
        if 'command' in kwargs:
            self._command = kwargs.pop('command')
        if 'bg' in kwargs:
            self._normal_bg = kwargs['bg']
        elif 'background' in kwargs:
            self._normal_bg = kwargs['background']
        super().config(**kwargs)

    configure = config


class RadarVisualizer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DEFCON - Centro de Mando Táctico")
        self.root.configure(bg=C_BG)
        self.root.resizable(False, False)

        self.settings    = {k: tk.DoubleVar(value=v) for k, v in DEFAULTS.items()}
        self.mode        = 'design'
        self._udp_state     = None
        self._udp_lock      = threading.Lock()
        self._udp_last_recv : float = 0.0

        self._server_proc: subprocess.Popen | None = None
        self._server_log                           = None
        self._server_btns: list                    = []

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.node_labels : dict[int, tk.Label] = {}

        # Ángulos de nodo como DoubleVar → enlazados a sliders del panel
        self.node_angle_vars: dict[int, tk.DoubleVar] = {
            nid: tk.DoubleVar(value=v)
            for nid, v in NODE_CANVAS_ANGLE_DEFAULT.items()
        }
        self._drag_node:     int | None = None
        self._selected_node: int | None = None
        self._angle_labels:  dict[int, tk.Label] = {}

        # Cache de estado para renderizado por capas
        self._bg_state:    tuple = ()
        self._nodes_state: tuple = ()
        self._last_hits: dict = {}   # caché de última detección por nodo en modo TRACK

        self._load_settings()
        self._build_layout()
        self._show_design_panel()
        self._start_udp()
        self._render_loop()
        self._server_status_loop()

    # ── Persistencia de configuración visual ─────────────────────────────────

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, var in self.settings.items():
                if k in data:
                    var.set(data[k])
            angles = data.get('node_angles', {})
            for nid, var in self.node_angle_vars.items():
                key = str(nid)
                if key in angles:
                    var.set(angles[key])
        except Exception:
            pass

    def _save_settings(self):
        try:
            data = {k: var.get() for k, var in self.settings.items()}
            data['node_angles'] = {str(nid): var.get() for nid, var in self.node_angle_vars.items()}
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    # ── Estructura principal ──────────────────────────────────────────────────

    def _build_layout(self):
        self.frame_canvas = tk.Frame(self.root, bg=C_BG,
                                     width=CANVAS_W, height=CANVAS_H)
        self.frame_canvas.pack(side=tk.LEFT, fill=tk.BOTH)
        self.frame_canvas.pack_propagate(False)

        self.frame_panel = tk.Frame(self.root, bg=C_PANEL,
                                    width=PANEL_W, height=TOTAL_H)
        self.frame_panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.frame_panel.pack_propagate(False)

        self.canvas = tk.Canvas(self.frame_canvas, width=CANVAS_W, height=CANVAS_H,
                                bg=C_BG, highlightthickness=0)
        self.canvas.pack()

        # Eventos de ratón sobre el canvas
        self.canvas.bind('<ButtonPress-1>',   self._on_press)
        self.canvas.bind('<B1-Motion>',       self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<Motion>',          self._on_hover)


    def _clear_panel(self):
        for w in self.frame_panel.winfo_children():
            w.destroy()
        self.node_labels.clear()
        self._server_btns.clear()

    # ── Panel Diseño ──────────────────────────────────────────────────────────

    def _show_design_panel(self):
        self._clear_panel()
        self._angle_labels.clear()
        self.mode = 'design'
        p = self.frame_panel

        tk.Label(p, text="CENTRO DE DISEÑO", bg=C_PANEL, fg=C_WHITE,
                 font=('Arial', F(15), 'bold')).pack(pady=(20, 4))

        self._add_server_control(p)

        # ── Sliders de posición de nodos ──────────────────────────────────────
        tk.Frame(p, bg='#1e1e1e', height=1).pack(fill=tk.X, padx=16, pady=(4, 4))
        tk.Label(p, text="POSICIÓN DE NODOS  (°)",
                 bg=C_PANEL, fg='#78909C',
                 font=('Arial', F(8), 'bold')).pack(anchor=tk.W, padx=20)

        for nid in [1, 2, 3]:
            col = NODE_DIAMOND_C[nid]
            self._make_node_slider(p, nid, col)


        # ── Sliders de zonas ─────────────────────────────────────────────────
        tk.Frame(p, bg='#1e1e1e', height=1).pack(fill=tk.X, padx=16, pady=(2, 4))
        tk.Label(p, text="ZONAS DE ALERTA",
                 bg=C_PANEL, fg='#78909C',
                 font=('Arial', F(8), 'bold')).pack(anchor=tk.W, padx=20)

        sliders = [
            ('zoom',     'Zoom (px/cm)',                1.0,  15.0),
            ('perim',    'Radio Perímetro (cm)',         5.0, 150.0),
            ('defcon1',  'Ancho DEFCON 1 (cm)',          5.0,  40.0),
            ('defcon2',  'Ancho DEFCON 2 (cm)',         10.0,  60.0),
            ('defcon3',  'Ancho DEFCON 3 (cm)',         15.0,  80.0),
            ('valla',    'Ancho VALLA (cm)',            20.0, 100.0),
            ('apertura', 'Apertura Haz por Nodo (°)',   20.0, 120.0),
        ]
        for key, label, lo, hi in sliders:
            self._make_slider(p, key, label, lo, hi)

        tk.Frame(p, bg=C_PANEL).pack(expand=True, fill=tk.Y)

        FlatButton(p, text="RESTAURAR POR DEFECTO",
                  bg='#b71c1c', fg=C_WHITE, font=('Arial', F(10), 'bold'),
                  relief=tk.FLAT, cursor='hand2',
                  activebackground='#7f0000', activeforeground=C_WHITE,
                  command=self._reset_defaults
                  ).pack(fill=tk.X, padx=20, pady=(0, 8))

        FlatButton(p, text="GUARDAR Y EJECUTAR",
                  bg='#1b5e20', fg=C_WHITE, font=('Arial', F(11), 'bold'),
                  relief=tk.FLAT, cursor='hand2',
                  activebackground='#003300', activeforeground=C_WHITE,
                  command=lambda: [self._save_settings(), self._show_live_panel()]
                  ).pack(fill=tk.X, padx=20, pady=(0, 22))

    # ── Panel Live ────────────────────────────────────────────────────────────

    def _show_live_panel(self):
        self._clear_panel()
        self.mode = 'live'
        self._drag_node = None
        p = self.frame_panel

        tk.Label(p, text="TELEMETRÍA EN VIVO", bg=C_PANEL, fg=C_GREEN,
                 font=('Arial', F(16), 'bold')).pack(pady=(28, 15))

        self._add_server_control(p)

        self._make_slider(p, 'zoom', 'Zoom (px/cm)', 1.0, 15.0)

        tk.Frame(p, bg=C_BORDER, height=1).pack(fill=tk.X, padx=20, pady=14)

        for nid in [1, 2, 3]:
            card = tk.Frame(p, bg=C_CARD,
                            highlightbackground=NODE_DIAMOND_C[nid],
                            highlightthickness=1)
            card.pack(fill=tk.X, padx=20, pady=6)

            tk.Label(card, text=f"NODO {nid}",
                     bg=C_CARD, fg=NODE_DIAMOND_C[nid],
                     font=('Arial', F(13), 'bold')
                     ).pack(anchor=tk.W, padx=15, pady=(12, 2))

            lbl = tk.Label(card, text="DESCONECTADO / SIN DATOS",
                           bg=C_CARD, fg=C_ORANGE,
                           font=('Arial', F(10), 'bold'))
            lbl.pack(anchor=tk.W, padx=15, pady=(0, 12))
            self.node_labels[nid] = lbl

        tk.Frame(p, bg=C_PANEL).pack(expand=True, fill=tk.Y)

        FlatButton(p, text="MODIFICAR DISEÑO",
                  bg='#1b5e20', fg=C_WHITE, font=('Arial', F(11), 'bold'),
                  relief=tk.FLAT, cursor='hand2',
                  activebackground='#003300', activeforeground=C_WHITE,
                  command=self._show_design_panel
                  ).pack(fill=tk.X, padx=20, pady=(0, 22))

    # ── Slider helpers ────────────────────────────────────────────────────────

    def _make_node_slider(self, parent, nid: int, color: str):
        """Slider de ángulo para un nodo, con nombre y valor en color."""
        var = self.node_angle_vars[nid]
        frame = tk.Frame(parent, bg=C_PANEL)
        frame.pack(fill=tk.X, padx=20, pady=3)

        # Cabecera: nombre coloreado + valor live (Label readonly) + Entry editable
        row = tk.Frame(frame, bg=C_PANEL)
        row.pack(fill=tk.X)
        tk.Label(row, text=f'◆ N{nid}', bg=C_PANEL, fg=color,
                 font=('Arial', F(9), 'bold')).pack(side=tk.LEFT)
        val_lbl = tk.Label(row, bg=C_PANEL, fg=color,
                           font=('Arial', F(9), 'bold'), width=7, anchor=tk.E)
        val_lbl.pack(side=tk.RIGHT)
        self._angle_labels[nid] = val_lbl

        entry_var = tk.StringVar(value=f"{var.get():.1f}")
        _busy = [False]
        entry = tk.Entry(row, textvariable=entry_var,
                         bg='#1e1e1e', fg=color, font=('Arial', F(9), 'bold'),
                         width=6, insertbackground=C_WHITE,
                         relief=tk.FLAT, highlightthickness=1,
                         highlightbackground='#444', highlightcolor=color)
        entry.pack(side=tk.RIGHT, padx=(0, 4))

        def on_change(*_):
            val_lbl.config(text=f'{var.get():.1f}°')
            if not _busy[0]:
                entry_var.set(f"{var.get():.1f}")
            self._selected_node = nid   # mover slider = seleccionar nodo

        def on_commit(*_):
            _busy[0] = True
            try:
                val = float(entry_var.get().replace(',', '.'))
                var.set(round(max(5.0, min(175.0, val)), 1))
                entry_var.set(f"{var.get():.1f}")
            except ValueError:
                entry_var.set(f"{var.get():.1f}")
            finally:
                _busy[0] = False

        var.trace_add('write', on_change)
        entry.bind('<Return>',   on_commit)
        entry.bind('<FocusOut>', on_commit)
        on_change()   # valor inicial

        tk.Scale(frame, variable=var, from_=5.0, to=175.0,
                 orient=tk.HORIZONTAL, resolution=0.5,
                 bg=C_PANEL, fg=color,
                 troughcolor='#1e3a1e',
                 highlightthickness=0, sliderrelief=tk.FLAT,
                 showvalue=False
                 ).pack(fill=tk.X)

    def _make_slider(self, parent, key, label_text, lo, hi):
        frame = tk.Frame(parent, bg=C_PANEL)
        frame.pack(fill=tk.X, padx=20, pady=5)
        row = tk.Frame(frame, bg=C_PANEL)
        row.pack(fill=tk.X)
        tk.Label(row, text=label_text, bg=C_PANEL, fg=C_WHITE,
                 font=('Arial', F(9))).pack(side=tk.LEFT)
        var = self.settings[key]
        entry_var = tk.StringVar(value=f"{var.get():.1f}")
        _busy = [False]
        entry = tk.Entry(row, textvariable=entry_var,
                         bg='#1e1e1e', fg=C_WHITE, font=('Arial', F(9)),
                         width=6, insertbackground=C_WHITE,
                         relief=tk.FLAT, highlightthickness=1,
                         highlightbackground='#444', highlightcolor='#66BB6A')
        entry.pack(side=tk.RIGHT)
        def on_slider(*_):
            if not _busy[0]:
                entry_var.set(f"{var.get():.1f}")
        def on_commit(*_):
            _busy[0] = True
            try:
                val = float(entry_var.get().replace(',', '.'))
                var.set(round(max(lo, min(hi, val)), 1))
                entry_var.set(f"{var.get():.1f}")
            except ValueError:
                entry_var.set(f"{var.get():.1f}")
            finally:
                _busy[0] = False
        var.trace_add('write', on_slider)
        entry.bind('<Return>',   on_commit)
        entry.bind('<FocusOut>', on_commit)
        tk.Scale(frame, variable=var, from_=lo, to=hi, orient=tk.HORIZONTAL,
                 resolution=0.1, bg=C_PANEL, fg=C_WHITE,
                 troughcolor='#333333', highlightthickness=0,
                 sliderrelief=tk.FLAT, showvalue=False).pack(fill=tk.X)

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _reset_defaults(self):
        for k, v in DEFAULTS.items():
            self.settings[k].set(v)
        self._reset_node_angles()

    def _reset_node_angles(self):
        for nid, v in NODE_CANVAS_ANGLE_DEFAULT.items():
            self.node_angle_vars[nid].set(v)

    def _get_angle(self, nid: int) -> float:
        return self.node_angle_vars[nid].get()

    def _set_angle(self, nid: int, val: float):
        self.node_angle_vars[nid].set(max(5.0, min(175.0, val)))



    # ── Arrastre de nodos ─────────────────────────────────────────────────────

    def _r_nodes(self):
        return max(self.settings['perim'].get() * self.settings['zoom'].get(), 20)

    def _node_pos(self, nid):
        ang = self._get_angle(nid)
        rad = math.radians(ang)
        r   = self._r_nodes()
        return CX + r * math.cos(rad), CY - r * math.sin(rad)

    def _on_press(self, event):
        if self.mode != 'design':
            return
        for nid in [1, 2, 3]:
            nx, ny = self._node_pos(nid)
            if math.hypot(event.x - nx, event.y - ny) < NODE_HIT_RADIUS:
                self._drag_node = nid
                self._selected_node = nid        # clic también selecciona
                self.canvas.config(cursor='fleur')
                return
        self._drag_node = None
        self._selected_node = None               # clic en vacío deselecciona

    def _on_drag(self, event):
        if self._drag_node is None or self.mode != 'design':
            return
        dx = event.x - CX
        dy = -(event.y - CY)
        angle = math.degrees(math.atan2(dy, dx))
        angle = max(5.0, min(175.0, angle))
        self._set_angle(self._drag_node, angle)
        self._draw_radar()

    def _on_release(self, event):
        self._drag_node = None
        self.canvas.config(cursor='')

    def _on_hover(self, event):
        if self.mode != 'design':
            return
        for nid in [1, 2, 3]:
            nx, ny = self._node_pos(nid)
            if math.hypot(event.x - nx, event.y - ny) < NODE_HIT_RADIUS:
                self.canvas.config(cursor='hand2')
                return
        if self._drag_node is None:
            self.canvas.config(cursor='')

    # ── Dibujo del radar — renderizado por capas ─────────────────────────────

    def _current_bg_state(self):
        s = self.settings
        return (
            round(s['zoom'].get(),     2),
            round(s['perim'].get(),    2),
            round(s['defcon1'].get(),  2),
            round(s['defcon2'].get(),  2),
            round(s['defcon3'].get(),  2),
            round(s['valla'].get(),    2),
            round(s['apertura'].get(), 2),
            self.mode,
            round(self._get_angle(1), 1),
            round(self._get_angle(2), 1),
            round(self._get_angle(3), 1),
        )

    def _current_nodes_state(self):
        s = self.settings
        return (
            self.mode,
            round(self._get_angle(1), 1),
            round(self._get_angle(2), 1),
            round(self._get_angle(3), 1),
            self._selected_node,
            round(s['perim'].get(), 2),
            round(s['zoom'].get(),  2),
        )

    def _draw_radar(self):
        c = self.canvas

        bg_state    = self._current_bg_state()
        nodes_state = self._current_nodes_state()

        bg_changed    = (bg_state    != self._bg_state)
        nodes_changed = (nodes_state != self._nodes_state)

        if not bg_changed and not nodes_changed and self.mode != 'live':
            return

        zoom      = self.settings['zoom'].get()
        perim_cm  = self.settings['perim'].get()
        r_nodes   = max(perim_cm * zoom, 20)
        r_d1      = (perim_cm + self.settings['defcon1'].get()) * zoom
        r_d2      = (perim_cm + self.settings['defcon2'].get()) * zoom
        r_d3      = (perim_cm + self.settings['defcon3'].get()) * zoom
        r_valla   = (perim_cm + self.settings['valla'].get())   * zoom
        half_beam = self.settings['apertura'].get() / 2.0
        r_outer   = r_valla   # el límite exterior visible es la valla

        if bg_changed:
            c.delete('bg')
            self._draw_bg_layer(c, r_d1, r_d2, r_d3, r_valla,
                                r_outer, r_nodes, half_beam)
            self._bg_state = bg_state

        if nodes_changed:
            c.delete('nodes')
            self._draw_nodes_layer(c, r_nodes)
            self._nodes_state = nodes_state

        c.delete('hits')
        if self.mode == 'live':
            self._draw_hits_layer(c, zoom)

        if c.find_withtag('bg'):    c.tag_lower('bg')
        if c.find_withtag('nodes'): c.tag_raise('nodes')
        if c.find_withtag('hits'):  c.tag_raise('hits')

    def _draw_bg_layer(self, c, r_d1, r_d2, r_d3, r_valla, r_outer, r_nodes, half_beam):
        T = 'bg'
        pts = [CX, CY] + self._semicircle_points(CX, CY, r_outer) + [CX, CY]
        c.create_polygon(pts, fill=C_ZONE_BG, outline='', tags=T)

        if self.mode == 'design':
            for nid in [1, 2, 3]:
                self._draw_node_beam(c, r_nodes, r_outer, nid, half_beam, T)

        c.create_rectangle(0, CY, CANVAS_W, CANVAS_H,
                           fill=C_GROUND, outline='', tags=T)
        c.create_line(0, CY, CANVAS_W, CY, fill='#455A64', width=1, tags=T)
        c.create_line(CX - r_outer, CY, CX + r_outer, CY,
                      fill='#90A4AE', width=3, tags=T)

        for sign in [-1, 1]:
            for frac in [0.33, 0.66, 1.0]:
                tx = CX + sign * r_outer * frac
                c.create_line(tx, CY - 6, tx, CY + 6,
                              fill='#78909C', width=1, tags=T)

        c.create_text(CX, CY + 22, text="▲  ZONA VIGILADA  ▲",
                      fill='#546E7A', font=('Arial', F(9), 'bold'), tags=T)
        c.create_oval(CX - 6, CY - 6, CX + 6, CY + 6,
                      fill=C_PERIM, outline=C_WHITE, width=1, tags=T)
        c.create_text(CX, CY + 40, text="PUNTO DE ORIGEN",
                      fill=C_PERIM, font=('Arial', F(8)), tags=T)

        for r, color, w in [
            (r_valla, C_VALLA, 2),
            (r_d3,    C_D3,    2),
            (r_d2,    C_D2,    2),
            (r_d1,    C_D1,    2),
        ]:
            self._draw_arc_line(c, CX, CY, r, color, w, T)

        self._draw_arc_line(c, CX, CY, r_nodes, C_NODE_ARC, 1, T)

    def _draw_nodes_layer(self, c, r_nodes):
        T = 'nodes'
        for nid in [1, 2, 3]:
            ang = self._get_angle(nid)
            rad = math.radians(ang)
            nx  = CX + r_nodes * math.cos(rad)
            ny  = CY - r_nodes * math.sin(rad)
            col = NODE_DIAMOND_C[nid]
            selected = (self._selected_node == nid and self.mode == 'design')

            if selected:
                c.create_oval(nx - 18, ny - 18, nx + 18, ny + 18,
                              outline=col, width=2, tags=T)
                c.create_oval(nx - 22, ny - 22, nx + 22, ny + 22,
                              outline=col, width=1, dash=(4, 3), tags=T)

            size = 11 if selected else 9
            c.create_polygon(
                nx,        ny - size,
                nx + size, ny,
                nx,        ny + size,
                nx - size, ny,
                fill=col, outline=C_BG, width=1, tags=T
            )

            ox = -22 * math.cos(rad)
            oy =  18 * math.sin(rad)
            if 70 < ang < 110:
                ox, oy = 0, -18
            c.create_text(nx + ox, ny - oy, text=f"N{nid}", fill=col,
                          font=('Arial', F(10), 'bold'), tags=T)

            if self.mode == 'design' and not selected:
                c.create_oval(nx - NODE_HIT_RADIUS, ny - NODE_HIT_RADIUS,
                              nx + NODE_HIT_RADIUS, ny + NODE_HIT_RADIUS,
                              outline=col, width=1, dash=(3, 4), tags=T)

            lbl = self._angle_labels.get(nid)
            if lbl:
                try:
                    lbl.config(text=f'{ang:.1f}°',
                               fg=col if selected else C_WHITE)
                except tk.TclError:
                    pass

    def _draw_hits_layer(self, c, zoom):
        T = 'hits'

        # Si no ha llegado ningún paquete UDP en los últimos 3 s, no dibujar nada
        if time.time() - self._udp_last_recv > 3.0:
            return

        with self._udp_lock:
            state = self._udp_state
        if not state:
            return

        r_valla = (self.settings['perim'].get() + self.settings['valla'].get()) * zoom

        # Línea de apuntado: desde el diamante → hacia fuera → hasta la valla
        radars = state.get('radars', {})
        for nid in [1, 2, 3]:
            cfg    = NODE_PHYS.get(nid)
            r_data = radars.get(str(nid)) or radars.get(nid)
            if not cfg or not r_data:
                continue
            cur_ang = r_data.get('current_angle', 0.0)

            nx, ny = self._node_pos(nid)
            g_rad = math.radians(cfg['theta'] - cur_ang)
            cos_g = math.cos(g_rad)
            sin_g = math.sin(g_rad)

            # Intersección del rayo con el círculo de la valla
            dx, dy = nx - CX, ny - CY
            B      = 2.0 * (dx * cos_g - dy * sin_g)
            C_coef = dx**2 + dy**2 - r_valla**2
            disc   = B**2 - 4.0 * C_coef
            if disc >= 0:
                sq    = math.sqrt(disc)
                cands = [t for t in [(-B + sq) / 2.0, (-B - sq) / 2.0] if t > 0]
                length = min(cands) if cands else r_valla
            else:
                length = r_valla

            ex = nx + length * cos_g
            ey = ny - length * sin_g
            col = NODE_BEAM_EDGE[nid]
            c.create_line(nx, ny, ex, ey, fill=col, width=2,
                          arrow=tk.LAST, arrowshape=(8, 10, 4), tags=T)

        detections = state.get('detections', state.get('hits', {}))
        d1_t = self.settings['defcon1'].get()
        d2_t = self.settings['defcon2'].get()
        d3_t = self.settings['defcon3'].get()
        dv_t = self.settings['valla'].get()

        for nid in [1, 2, 3]:
            cfg    = NODE_PHYS.get(nid)
            r_data = radars.get(str(nid)) or radars.get(nid)
            if not cfg:
                continue
            det   = detections.get(str(nid)) or detections.get(nid)
            mode  = r_data.get('mode', '') if r_data else ''
            stale = False
            if not det and mode == 'TRACK' and nid in self._last_hits:
                det   = self._last_hits[nid]
                stale = True
            if not det:
                continue

            d     = det['dist']
            nx, ny = self._node_pos(nid)
            g_rad = math.radians(cfg['theta'] - det['angle'])
            px    = nx + d * zoom * math.cos(g_rad)
            py    = ny - d * zoom * math.sin(g_rad)

            if py > CY:
                continue

            rd = 7
            dot_col = ('#ff1744' if d <= d1_t
                       else '#ffa726' if d <= d2_t
                       else '#ffca28' if d <= d3_t
                       else '#4fc3f7' if d <= dv_t
                       else '#b0bec5')
            c.create_oval(px-rd, py-rd, px+rd, py+rd,
                          fill=dot_col, outline=C_WHITE, width=2, tags=T)
            if stale:
                c.create_oval(px-rd-3, py-rd-3, px+rd+3, py+rd+3,
                              outline=dot_col, width=1, dash=(4, 3), tags=T)
            c.create_text(px, py-16, text=f"{d:.1f}cm",
                          fill=C_WHITE, font=('Arial', F(8)), tags=T)

        # Punto combinado: punto medio visual de los dos nodos detectados en zona sucia
        for pair, nids in [('N1-N2', (1, 2)), ('N2-N3', (2, 3))]:
            if pair not in state.get('trilat', {}):
                continue
            pts = []
            for nid in nids:
                cfg2   = NODE_PHYS.get(nid)
                det2   = detections.get(str(nid)) or detections.get(nid)
                if not cfg2 or not det2:
                    continue
                n2x, n2y = self._node_pos(nid)
                g2 = math.radians(cfg2['theta'] - det2['angle'])
                pts.append((n2x + det2['dist'] * zoom * math.cos(g2),
                             n2y - det2['dist'] * zoom * math.sin(g2)))
            if len(pts) == 2:
                tx = (pts[0][0] + pts[1][0]) / 2
                ty = (pts[0][1] + pts[1][1]) / 2
                r  = 10
                c.create_oval(tx - r, ty - r, tx + r, ty + r,
                              outline='yellow', width=3, fill='', tags=T)
                pos = state['trilat'][pair]
                c.create_text(tx, ty - 20,
                              text=f"({pos['x']:.1f},{pos['y']:.1f})",
                              fill='yellow', font=('Arial', F(8), 'bold'), tags=T)

    def _draw_node_beam(self, c, r_nodes, r_outer, nid, half_beam, tag=''):
        ang_deg = self._get_angle(nid)
        rad_ang = math.radians(ang_deg)
        nx = CX + r_nodes * math.cos(rad_ang)
        ny = CY - r_nodes * math.sin(rad_ang)
        beam_r = r_outer - r_nodes + r_outer * 0.12
        edge_col = NODE_BEAM_EDGE[nid]

        pts = [nx, ny]
        for deg in range(int(ang_deg - half_beam), int(ang_deg + half_beam) + 1, 1):
            rad = math.radians(deg)
            pts.append(nx + beam_r * math.cos(rad))
            pts.append(ny - beam_r * math.sin(rad))
        pts += [nx, ny]
        if len(pts) >= 8:
            c.create_polygon(pts, fill=edge_col, outline='',
                             stipple='gray25', tags=tag)

        for side in [-1, 1]:
            edge_rad = math.radians(ang_deg + side * half_beam)
            ex = nx + beam_r * math.cos(edge_rad)
            ey = ny - beam_r * math.sin(edge_rad)
            c.create_line(nx, ny, ex, ey,
                          fill=edge_col, width=2, dash=(8, 4), tags=tag)

        ax = nx + beam_r * math.cos(rad_ang)
        ay = ny - beam_r * math.sin(rad_ang)
        c.create_line(nx, ny, ax, ay,
                      fill=edge_col, width=1, dash=(3, 6), tags=tag)

    # ── Primitivas de dibujo ──────────────────────────────────────────────────

    def _semicircle_points(self, cx, cy, r, step=1):
        pts = []
        for deg in range(0, 181, step):
            rad = math.radians(deg)
            pts.append(cx + r * math.cos(rad))
            pts.append(cy - r * math.sin(rad))
        return pts

    def _draw_arc_line(self, c, cx, cy, r, color, width, tag=''):
        pts = self._semicircle_points(cx, cy, r, step=2)
        if len(pts) >= 4:
            c.create_line(pts, fill=color, width=width, smooth=True, tags=tag)

    def _draw_diamond(self, c, x, y, size, color):
        c.create_polygon(
            x,        y - size,
            x + size, y,
            x,        y + size,
            x - size, y,
            fill=color, outline=C_BG, width=1
        )

    # ── Control del servidor ──────────────────────────────────────────────────

    def _on_close(self):
        self._save_settings()
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
        if self._server_log:
            try:
                self._server_log.close()
            except Exception:
                pass
        self.root.destroy()

    def _server_is_running(self) -> bool:
        return self._server_proc is not None and self._server_proc.poll() is None

    def _toggle_server(self):
        if self._server_is_running():
            self._server_proc.terminate()
            self._server_proc = None
            if self._server_log:
                try:
                    self._server_log.close()
                except Exception:
                    pass
                self._server_log = None
        else:
            try:
                self._server_log = open(SERVER_LOG, 'w', encoding='utf-8')
                env = os.environ.copy()
                env['PYTHONUTF8'] = '1'
                kwargs = {}
                if sys.platform == 'win32':
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                self._server_proc = subprocess.Popen(
                    [sys.executable, '-u', SERVER_PATH],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    cwd=SERVER_WD,
                    env=env,
                    **kwargs,
                )
                threading.Thread(target=self._server_reader, daemon=True).start()
            except Exception as e:
                print(f"[GUI] Error al iniciar servidor: {e}")
        self._refresh_server_btns()

    def _refresh_server_btns(self):
        running = self._server_is_running()
        for btn, dot in self._server_btns:
            try:
                if running:
                    btn.config(text="■  DETENER SERVIDOR",
                               bg='#7f0000', activebackground='#4a0000')
                    dot.config(fg='#ef5350', text='● ACTIVO')
                else:
                    btn.config(text="▶  INICIAR SERVIDOR",
                               bg='#1b5e20', activebackground='#003300')
                    dot.config(fg='#546E7A', text='● PARADO')
            except tk.TclError:
                pass

    def _server_status_loop(self):
        self._refresh_server_btns()
        # Si no llegan datos UDP en >3s, resetear tarjetas a DESCONECTADO
        if self.mode == 'live' and time.time() - self._udp_last_recv > 3.0:
            self._last_hits.clear()
            for nid, lbl in self.node_labels.items():
                try:
                    lbl.config(text="DESCONECTADO / SIN DATOS", fg=C_ORANGE)
                except tk.TclError:
                    pass
        self.root.after(1000, self._server_status_loop)

    def _add_server_control(self, parent):
        frame = tk.Frame(parent, bg='#161616',
                         highlightbackground='#2a2a2a', highlightthickness=1)
        frame.pack(fill=tk.X, padx=20, pady=(4, 8))

        row = tk.Frame(frame, bg='#161616')
        row.pack(fill=tk.X, padx=10, pady=(6, 2))
        tk.Label(row, text='SERVIDOR', bg='#161616', fg='#78909C',
                 font=('Arial', F(8), 'bold')).pack(side=tk.LEFT)
        running = self._server_is_running()
        dot = tk.Label(row,
                       text='● ACTIVO' if running else '● PARADO',
                       bg='#161616',
                       fg='#ef5350' if running else '#546E7A',
                       font=('Arial', F(8), 'bold'))
        dot.pack(side=tk.RIGHT)

        btn = FlatButton(frame,
                        text="■  DETENER SERVIDOR" if running else "▶  INICIAR SERVIDOR",
                        bg='#7f0000' if running else '#1b5e20',
                        fg=C_WHITE, font=('Arial', F(9), 'bold'),
                        relief=tk.FLAT, cursor='hand2',
                        activeforeground=C_WHITE,
                        activebackground='#4a0000' if running else '#003300',
                        command=self._toggle_server)
        btn.pack(fill=tk.X, padx=10, pady=(2, 8))

        self._server_btns.append((btn, dot))

    def _server_reader(self):
        """Hilo: lee stdout del servidor byte a byte, vuelca al log y detecta el prompt de sesión."""
        proc = self._server_proc
        buf  = ""
        prompt_fired = False
        # Decodificador incremental: un carácter UTF-8 puede ocupar varios
        # bytes (tildes, °, etc). Decodificar byte a byte de forma aislada
        # rompe esos caracteres multibyte y los reemplaza por '�'.
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        while proc and proc.poll() is None:
            try:
                ch = proc.stdout.read(1)
            except Exception:
                break
            if not ch:
                break
            char = decoder.decode(ch)
            if not char:
                continue
            buf += char
            if self._server_log:
                try:
                    self._server_log.write(char)
                    self._server_log.flush()
                except Exception:
                    pass
            # El prompt de input() no tiene '\n', detectamos en cuanto aparece en el buffer
            if not prompt_fired and 'Deseas reanudar' in buf:
                prompt_fired = True
                self.root.after(0, self._ask_resume_session)
            # Evitar que el buffer crezca indefinidamente
            if len(buf) > 4096:
                buf = buf[-2048:]

    def _ask_resume_session(self):
        import tkinter.messagebox as mb
        result = mb.askyesno(
            "Sesión anterior detectada",
            "💾 Se ha detectado una sesión anterior.\n\n"
            "¿Deseas reanudar las posiciones de los radares?\n"
            "(Sí = continuar desde el último estado  ·  No = empezar desde 0°)",
            parent=self.root,
        )
        if self._server_proc and self._server_proc.stdin:
            try:
                self._server_proc.stdin.write(b's\n' if result else b'n\n')
                self._server_proc.stdin.flush()
            except Exception:
                pass

    # ── UDP listener ──────────────────────────────────────────────────────────

    def _start_udp(self):
        def listen():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', UDP_PORT))
            except OSError:
                return
            s.settimeout(1.0)
            while True:
                try:
                    data, _ = s.recvfrom(4096)
                    state = json.loads(data.decode())
                    with self._udp_lock:
                        self._udp_state     = state
                        self._udp_last_recv = time.time()
                    self.root.after(0, self._update_node_cards, state)
                except socket.timeout:
                    continue
                except Exception:
                    continue
        threading.Thread(target=listen, daemon=True).start()

    def _update_node_cards(self, state):
        if self.mode != 'live':
            return
        radars     = state.get('radars', {})
        detections = state.get('detections', state.get('hits', {}))
        for nid in [1, 2, 3]:
            lbl = self.node_labels.get(nid)
            if not lbl:
                continue
            r_data = radars.get(str(nid)) or radars.get(nid)
            if not r_data:
                lbl.config(text="DESCONECTADO / SIN DATOS", fg=C_ORANGE)
                self._last_hits.pop(nid, None)
                continue
            mode  = r_data.get('mode', '?')
            angle = r_data.get('current_angle', 0.0)
            det   = detections.get(str(nid)) or detections.get(nid)
            if det and mode == 'TRACK':
                self._last_hits[nid] = det
            elif mode != 'TRACK':
                self._last_hits.pop(nid, None)
            display_det = det or (self._last_hits.get(nid) if mode == 'TRACK' else None)
            d1 = self.settings['defcon1'].get()
            d2 = self.settings['defcon2'].get()
            if display_det:
                d     = display_det['dist']
                stale = ''  if det else ' [último]'
                text  = f"{mode}  |  {angle:+.1f}°  |  {d:.1f} cm{stale}"
                color = ('#ff1744' if d <= d1 else '#ffa726' if d <= d2 else C_GREEN)
            else:
                text  = f"{mode}  |  {angle:+.1f}°  |  sin obstáculo"
                color = C_GREEN
            lbl.config(text=text, fg=color)

    # ── Bucle de render ───────────────────────────────────────────────────────

    def _render_loop(self):
        self._draw_radar()
        self.root.after(20, self._render_loop)   # ~50 fps


if __name__ == '__main__':
    root = tk.Tk()
    root.geometry(f"{TOTAL_W}x{TOTAL_H}")
    RadarVisualizer(root)
    root.mainloop()
