#!/usr/bin/env python3
"""
Genera los 3 diagramas UML del TFG como PNG de alta resolución.
  - diagrama_estados_modos.png   (Diagrama de Estados UML — SEARCH/TRACK)
  - diagrama_clases.png          (Diagrama de Clases UML)
  - diagrama_componentes.png     (Diagrama de Componentes UML)

Requisito: pip install matplotlib
Uso:       python generate_uml_diagrams.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import os

DPI    = 200
OUTDIR = os.path.dirname(os.path.abspath(__file__))

# ─── primitivas ──────────────────────────────────────────────────────────────

def box(ax, x, y, w, h, fc='#EBF5FB', ec='#1A5276', lw=2.0, rad=0.08, z=2):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f'round,pad={rad}',
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z))

def hline(ax, x, y, w, color='#555', lw=1.0):
    ax.plot([x, x + w], [y, y], color=color, lw=lw, zorder=3)

def t(ax, x, y, s, fs=11, color='#1C2833', bold=False,
      ha='left', va='center', italic=False, mono=False, z=3):
    kw = dict(ha=ha, va=va, fontsize=fs, color=color, zorder=z)
    if bold:   kw['fontweight'] = 'bold'
    if italic: kw['fontstyle']  = 'italic'
    if mono:   kw['fontfamily'] = 'monospace'
    ax.text(x, y, s, **kw)

def arr(ax, x1, y1, x2, y2, color='#2c3e50', lw=1.8,
        style='->', cs='arc3,rad=0.0', label='',
        lfs=10, lox=0, loy=0.2, z=4):
    # '-->' and '--' are not valid matplotlib arrowstyles; translate to linestyle='dashed'
    if style == '-->':
        real_style, dashed = '->', True
    elif style == '--':
        real_style, dashed = '-', True
    else:
        real_style, dashed = style, False
    ap = dict(arrowstyle=real_style, color=color, lw=lw, connectionstyle=cs)
    if dashed:
        ap['linestyle'] = 'dashed'
    ax.annotate('',
        xy=(x2, y2), xytext=(x1, y1),
        arrowprops=ap, zorder=z)
    if label:
        ax.text((x1 + x2) / 2 + lox, (y1 + y2) / 2 + loy,
                label, ha='center', va='center',
                fontsize=lfs, color=color, zorder=z,
                bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.93))

def dot(ax, x, y, r=0.18, color='#2c3e50'):
    ax.add_patch(plt.Circle((x, y), r, color=color, zorder=5))

def state_box(ax, x, y, w, h, title, subtitle, hc, bc, lines, lfs=11):
    """Caja de estado UML con cabecera coloreada y contenido."""
    box(ax, x, y, w, h, fc=bc, ec=hc, lw=2.5)
    box(ax, x, y + h - 1.0, w, 1.0, fc=hc, ec=hc, lw=1, rad=0.06, z=3)
    t(ax, x + w/2, y + h - 0.5,  title,    fs=14, bold=True,   color='white', ha='center')
    t(ax, x + w/2, y + h - 0.82, subtitle, fs=11, italic=True, color='white', ha='center', z=3)
    hline(ax, x, y + h - 1.0, w, color=hc)
    for i, l in enumerate(lines):
        t(ax, x + 0.15, y + h - 1.55 - i * 0.54, l, fs=lfs, mono=True, color='#1C2833')

def uml_class(ax, x, y, w, name, stereotype=None,
              attrs=None, methods=None,
              hc='#2874A6', bc='#EBF5FB', lfs=10):
    """Caja de clase UML con 3 compartimentos."""
    attrs   = attrs   or []
    methods = methods or []
    rh  = 0.32                           # altura por fila
    hh  = 0.72 if stereotype else 0.55   # cabecera
    ah  = max(len(attrs)   * rh, 0.25)
    mh  = max(len(methods) * rh, 0.25)
    h   = hh + ah + mh
    box(ax, x, y, w, h, fc=bc, ec=hc, lw=1.8)
    # cabecera
    box(ax, x, y + h - hh, w, hh, fc=hc, ec=hc, lw=1, rad=0.05, z=3)
    if stereotype:
        t(ax, x + w/2, y + h - 0.22, f'«{stereotype}»',
          fs=lfs - 1, italic=True, color='white', ha='center', z=4)
        t(ax, x + w/2, y + h - 0.52, name,
          fs=lfs + 1, bold=True, color='white', ha='center', z=4)
    else:
        t(ax, x + w/2, y + h - hh/2, name,
          fs=lfs + 1, bold=True, color='white', ha='center', z=4)
    # atributos
    dy_a = y + h - hh
    hline(ax, x, dy_a, w, color=hc, lw=0.9)
    for i, a in enumerate(attrs):
        t(ax, x + 0.1, dy_a - (i + 0.58) * rh, a, fs=lfs, mono=True, color='#1C2833')
    # métodos
    dy_m = dy_a - ah
    hline(ax, x, dy_m, w, color=hc, lw=0.9)
    for i, m in enumerate(methods):
        t(ax, x + 0.1, dy_m - (i + 0.58) * rh, m, fs=lfs, mono=True, color='#154360')
    return h   # devuelve la altura total para posicionar flechas

def pkg_box(ax, x, y, w, h, label, color='#555'):
    """Paquete UML (rectángulo con etiqueta en pestaña superior)."""
    box(ax, x, y, w, h, fc='#FDFEFE', ec=color, lw=1.5, rad=0.05)
    box(ax, x, y + h, 2.8, 0.4, fc=color, ec=color, lw=1, rad=0.03, z=3)
    t(ax, x + 0.1, y + h + 0.2, label, fs=11, bold=True, color='white', z=4)


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAMA 1 — Estados SEARCH / TRACK
# ═══════════════════════════════════════════════════════════════════════════════

def dia_estados():
    """Diagrama visual polar de los modos SEARCH/TRACK del nodo radar."""
    import numpy as np
    import matplotlib.patches as mpatches

    W, H = 26, 13.5
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')
    fig.patch.set_facecolor('white')

    C_BLUE   = '#1A5276'; C_BLUE_L   = '#D6EAF8'
    C_PURPLE = '#6C3483'; C_PURPLE_L = '#F5EEF8'
    C_GREEN  = '#1E8449'; C_GREEN_L  = '#D5F5E3'
    C_YELLOW = '#9A7D0A'; C_YELLOW_L = '#FEF9E7'
    C_RED    = '#C0392B'; C_RED_L    = '#FDEDEC'
    C_GRAY   = '#5D6D7E'

    # ── título ───────────────────────────────────────────────────────────────────
    t(ax, W/2, H - 0.35,
      'Modos de Operación del Nodo Radar',
      fs=18, bold=True, ha='center', color='#2c3e50')
    t(ax, W/2, H - 0.88,
      'Gestionado por el Servidor Central  ·  server_central.py',
      fs=12, italic=True, ha='center', color='#7f8c8d')

    # ── marcos de panel ──────────────────────────────────────────────────────────
    box(ax, 0.30, 0.30, 11.5, 12.0, fc='#EAF4FB', ec=C_BLUE,   lw=2.5, rad=0.1, z=1)
    box(ax, 14.2, 0.30, 11.5, 12.0, fc='#F5EEF8', ec=C_PURPLE, lw=2.5, rad=0.1, z=1)

    t(ax,  6.05, 11.92, 'SEARCH',              fs=17, bold=True,   ha='center', color=C_BLUE)
    t(ax,  6.05, 11.44, '(Modo Búsqueda)',      fs=12, italic=True, ha='center', color=C_BLUE)
    t(ax, 19.95, 11.92, 'TRACK',               fs=17, bold=True,   ha='center', color=C_PURPLE)
    t(ax, 19.95, 11.44, '(Modo Seguimiento)',   fs=12, italic=True, ha='center', color=C_PURPLE)

    # ═════════════════════════════════════════════════════════════════════════════
    # PANEL SEARCH — visualización polar
    # ═════════════════════════════════════════════════════════════════════════════
    NX_S, NY_S = 6.05, 1.5
    R_S = 7.2

    # abanico completo ±45° (relleno semitransparente)
    ax.add_patch(mpatches.Wedge((NX_S, NY_S), R_S, 45, 135,
        facecolor=C_BLUE_L, edgecolor=C_BLUE, lw=1.5, alpha=0.40, zorder=2))

    # rayos fantasma en distintas posiciones del barrido
    for ang in [50, 62, 75, 90, 108, 120, 130]:
        rad = np.radians(ang)
        alpha = 0.10 + 0.28 * (1 - abs(ang - 90) / 50)
        ax.plot([NX_S, NX_S + R_S * np.cos(rad)],
                [NY_S, NY_S + R_S * np.sin(rad)],
                color=C_BLUE, lw=1.5, alpha=alpha, zorder=3)

    # rayo principal (posición actual del haz)
    main_r = np.radians(108)
    ax.plot([NX_S, NX_S + R_S * np.cos(main_r)],
            [NY_S, NY_S + R_S * np.sin(main_r)],
            color=C_BLUE, lw=3.0, alpha=0.92, zorder=4)

    # flechas curvas indicando dirección de barrido
    for r_frac, a0, a1 in [(0.52, 92, 122), (0.72, 58, 88)]:
        r_draw = R_S * r_frac
        pts = np.linspace(np.radians(a0), np.radians(a1), 35)
        xs = NX_S + r_draw * np.cos(pts)
        ys = NY_S + r_draw * np.sin(pts)
        ax.plot(xs[:-1], ys[:-1], color=C_BLUE, lw=1.8, alpha=0.65, zorder=4)
        ax.annotate('', xy=(xs[-1], ys[-1]), xytext=(xs[-2], ys[-2]),
                    arrowprops=dict(arrowstyle='->', color=C_BLUE, lw=1.8), zorder=5)

    # líneas de límite angular (±45°)
    for lim in [45, 135]:
        lr = np.radians(lim)
        ax.plot([NX_S, NX_S + R_S * np.cos(lr)],
                [NY_S, NY_S + R_S * np.sin(lr)],
                color=C_GRAY, lw=1.2, linestyle='dashed', alpha=0.55, zorder=2)
    t(ax, NX_S + R_S*0.80*np.cos(np.radians(34)),
          NY_S + R_S*0.80*np.sin(np.radians(34)),
      '+45°', fs=10, color=C_GRAY, ha='center', z=5)
    t(ax, NX_S + R_S*0.80*np.cos(np.radians(146)),
          NY_S + R_S*0.80*np.sin(np.radians(146)),
      '−45°', fs=10, color=C_GRAY, ha='center', z=5)
    t(ax, NX_S, NY_S + R_S + 0.32, '0°', fs=9.5, color=C_GRAY, ha='center', italic=True, z=5)

    # nodo sensor SEARCH
    ax.add_patch(plt.Circle((NX_S, NY_S), 0.32,
                            facecolor=C_BLUE_L, edgecolor=C_BLUE, lw=2.5, zorder=6))
    t(ax, NX_S, NY_S, 'N', fs=10, bold=True, ha='center', color=C_BLUE, z=7)

    # pseudoestado inicial
    dot(ax, NX_S, NY_S + R_S + 0.92)
    arr(ax, NX_S, NY_S + R_S + 0.74, NX_S, NY_S + R_S + 0.04, color='#2c3e50', lw=2.0)

    # propiedades SEARCH
    for i, p in enumerate(['Barrido ±45°  (dientes de sierra)',
                            'Paso angular: 2.5° / supertrama',
                            'Inversión automática en límites ±45°',
                            'Estado inicial y de recuperación']):
        t(ax, 0.65, 4.4 - i*0.60, f'• {p}', fs=10.5, color='#2c3e50', z=5)

    # ═════════════════════════════════════════════════════════════════════════════
    # PANEL TRACK — visualización polar con subestados
    # ═════════════════════════════════════════════════════════════════════════════
    NX_T, NY_T = 19.95, 1.5
    R_T = 7.2
    DEFCON1_R = R_T * 0.62     # umbral DEFCON 1

    # abanico base ±45°
    ax.add_patch(mpatches.Wedge((NX_T, NY_T), R_T, 45, 135,
        facecolor='#EDE0F5', edgecolor=C_PURPLE, lw=1.2, alpha=0.28, zorder=2))

    # zona BORDE — anillo exterior (entre DEFCON1_R y R_T)
    ax.add_patch(mpatches.Wedge((NX_T, NY_T), R_T, 45, 135,
        width=R_T - DEFCON1_R,
        facecolor=C_YELLOW_L, edgecolor=C_YELLOW, lw=1.2, alpha=0.78, zorder=3))

    # zona MIDIENDO — sector interior (hasta DEFCON1_R)
    ax.add_patch(mpatches.Wedge((NX_T, NY_T), DEFCON1_R, 45, 135,
        facecolor=C_GREEN_L, edgecolor=C_GREEN, lw=1.8, alpha=0.80, zorder=4))

    # arco límite DEFCON 1 (punteado)
    theta_arc = np.linspace(np.radians(45), np.radians(135), 60)
    ax.plot(NX_T + DEFCON1_R * np.cos(theta_arc),
            NY_T + DEFCON1_R * np.sin(theta_arc),
            color=C_YELLOW, lw=2.2, linestyle='dashed', alpha=0.95, zorder=5)
    a_lbl = np.radians(130)
    t(ax, NX_T + DEFCON1_R * np.cos(a_lbl) - 0.12,
          NY_T + DEFCON1_R * np.sin(a_lbl) + 0.05,
      'DEFCON 1', fs=9.5, color=C_YELLOW, ha='right', z=6)

    # rayo fijo al objetivo
    obj_a = np.radians(82)
    obj_r = DEFCON1_R * 0.68
    obj_pos = (NX_T + obj_r * np.cos(obj_a), NY_T + obj_r * np.sin(obj_a))
    ax.plot([NX_T, obj_pos[0]], [NY_T, obj_pos[1]],
            color=C_PURPLE, lw=3.2, alpha=0.92, zorder=5)
    ax.plot(obj_pos[0], obj_pos[1], 'x',
            color=C_RED, markersize=16, markeredgewidth=3.0, zorder=8)
    t(ax, obj_pos[0] + 0.42, obj_pos[1] + 0.15,
      'objetivo', fs=10, bold=True, color=C_RED, ha='left', z=8)

    # etiquetas de zona (dentro del abanico)
    mid_r = DEFCON1_R * 0.50
    t(ax, NX_T, NY_T + mid_r + 0.18, 'MIDIENDO',
      fs=11, bold=True, ha='center', color=C_GREEN, z=7)
    t(ax, NX_T, NY_T + mid_r - 0.32, 'eco ≤ DEFCON 1',
      fs=9, italic=True, ha='center', color=C_GREEN, z=7)

    borde_r = (DEFCON1_R + R_T) * 0.50
    t(ax, NX_T, NY_T + borde_r + 0.18, 'BORDE',
      fs=11, bold=True, ha='center', color=C_YELLOW, z=7)
    t(ax, NX_T, NY_T + borde_r - 0.32, 'eco > DEFCON 1',
      fs=9, italic=True, ha='center', color=C_YELLOW, z=7)

    # zona MISS — arco punteado exterior
    miss_r = R_T + 0.62
    ax.plot(NX_T + miss_r * np.cos(theta_arc),
            NY_T + miss_r * np.sin(theta_arc),
            color=C_RED, lw=2.0, linestyle='dotted', alpha=0.80, zorder=4)
    t(ax, NX_T, NY_T + miss_r + 0.28, 'MISS — sin eco en ventana ToF',
      fs=10.5, bold=True, ha='center', color=C_RED, z=6)

    # líneas de límite angular
    for lim in [45, 135]:
        lr = np.radians(lim)
        ax.plot([NX_T, NX_T + R_T * np.cos(lr)],
                [NY_T, NY_T + R_T * np.sin(lr)],
                color=C_GRAY, lw=1.2, linestyle='dashed', alpha=0.55, zorder=2)
    t(ax, NX_T + R_T*0.80*np.cos(np.radians(34)),
          NY_T + R_T*0.80*np.sin(np.radians(34)),
      '+45°', fs=10, color=C_GRAY, ha='center', z=5)
    t(ax, NX_T + R_T*0.80*np.cos(np.radians(146)),
          NY_T + R_T*0.80*np.sin(np.radians(146)),
      '−45°', fs=10, color=C_GRAY, ha='center', z=5)

    # nodo sensor TRACK
    ax.add_patch(plt.Circle((NX_T, NY_T), 0.32,
                            facecolor='#EDE0F5', edgecolor=C_PURPLE, lw=2.5, zorder=6))
    t(ax, NX_T, NY_T, 'N', fs=10, bold=True, ha='center', color=C_PURPLE, z=7)

    # propiedades TRACK
    for i, p in enumerate(['track_lock: 6 SF inmunidad',
                            'track_entry_sf: 1.ª detección',
                            'MAX_MISSES = 3',
                            'MAX_EDGE_FLIPS = 5']):
        t(ax, 14.50, 4.4 - i*0.60, f'• {p}', fs=10.5, color='#2c3e50', z=5)

    # ── flechas de transición (hueco central) ─────────────────────────────────
    # SEARCH → TRACK
    arr(ax, 11.8, 8.6, 14.2, 8.6, color=C_BLUE, lw=2.8,
        label='Detección ≤ DEFCON 1\n[sin conflicto / ganó zona sucia]',
        lfs=10.5, loy=0.52)

    # TRACK → SEARCH (3 condiciones)
    arr(ax, 14.2, 7.4, 11.8, 7.4, color=C_RED, lw=2.0,
        label='misses ≥ 3', lfs=10, loy=-0.40)
    arr(ax, 14.2, 6.4, 11.8, 6.4, color=C_RED, lw=2.0,
        label='edge_flips ≥ 5', lfs=10, loy=-0.40)
    arr(ax, 14.2, 5.4, 11.8, 5.4, color=C_RED, lw=2.0,
        label='perdedor zona sucia', lfs=10, loy=-0.40)

    out = os.path.join(OUTDIR, 'diagrama_estados_modos.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAMA 2 — Clases UML
# ═══════════════════════════════════════════════════════════════════════════════

def dia_clases():
    W, H = 24, 17
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')
    fig.patch.set_facecolor('white')

    t(ax, W/2, H - 0.3,
      'Diagrama de Clases UML — Sistema de Vigilancia Distribuido',
      fs=16, bold=True, ha='center', color='#2c3e50')

    # ── Paquete Firmware ──────────────────────────────────────────────────────
    pkg_box(ax, 0.4, 0.4, 14.8, H - 1.4, 'Firmware ESP32  (C++ / FreeRTOS)', '#2874A6')

    # SystemManager
    sm_h = uml_class(ax, 0.8, 10.5, 5.6, 'SystemManager',
        stereotype='Singleton',
        attrs=['currentState : SystemState',
               'queueCommands : QueueHandle_t',
               'queueResults : QueueHandle_t',
               'radarId : uint8_t',
               't0_last_superframe : uint32_t',
               'current_angle_logic : float',
               'motorDirInvert : bool',
               'reedTriggerLevel : int'],
        methods=['+ instance() : SystemManager&',
                 '+ init() : void',
                 '+ changeState(s) : void'],
        hc='#1F618D', bc='#D6EAF8', lfs=10)

    # RadarHardware
    rh_h = uml_class(ax, 0.8, 6.5, 5.6, 'RadarHardware',
        attrs=['- currentAngle : float'],
        methods=['+ init() : void',
                 '+ moveToAngle(a : float) : void',
                 '+ goHome() : void',
                 '+ syncPosition(a : float) : void',
                 '+ getDistance() : float'],
        hc='#1F618D', bc='#D6EAF8', lfs=10)

    # HwCommand
    hw_h = uml_class(ax, 0.8, 4.2, 5.6, 'HwCommand',
        stereotype='struct',
        attrs=['+ type : HwCmdType',
               '+ param : float',
               '+ execution_time_ms : uint32_t'],
        hc='#1A5276', bc='#EAF2FF', lfs=10)

    # HwResult
    hr_h = uml_class(ax, 0.8, 2.1, 5.6, 'HwResult',
        stereotype='struct',
        attrs=['+ type : HwResType',
               '+ value : float',
               '+ angle : float'],
        hc='#1A5276', bc='#EAF2FF', lfs=10)

    # TaskComms
    tc_h = uml_class(ax, 8.0, 10.5, 6.6, 'TaskComms',
        stereotype='task: Core 0',
        attrs=['(hilo daemon)'],
        methods=['+ run() : void',
                 '- connectToServer() : bool',
                 '- sendPacket(...) : void',
                 '- calcularSiguienteAngulo() : float'],
        hc='#1F618D', bc='#D6EAF8', lfs=10)

    # TaskRadar
    tr_h = uml_class(ax, 8.0, 7.8, 6.6, 'TaskRadar',
        stereotype='task: Core 1',
        attrs=['(hilo daemon)'],
        methods=['+ run() : void'],
        hc='#1F618D', bc='#D6EAF8', lfs=10)

    # ── Paquete Servidor ──────────────────────────────────────────────────────
    pkg_box(ax, 15.6, 8.0, 8.0, 7.5, 'Servidor Central  (Python)', '#7D3C98')

    srv_h = uml_class(ax, 16.0, 8.4, 7.2, 'ArbitroServer',
        attrs=['+ seq : int',
               '+ track_states : dict',
               '+ track_lock : dict',
               '+ latest_reports : dict',
               '+ defcon1_limit : float',
               '+ valla_limit : float'],
        methods=['+ get_state(r_id) : dict',
                 '+ calculate_global_coords(...) : tuple',
                 '+ orchestration_loop() : void',
                 '+ handle_client(conn, addr) : void',
                 '+ load_grid() : dict',
                 '+ save_state() : void',
                 '+ start() : void'],
        hc='#7D3C98', bc='#F4ECF7', lfs=10)

    # ── Paquete Visualizador ──────────────────────────────────────────────────
    pkg_box(ax, 15.6, 0.4, 8.0, 7.0, 'Visualizador  (Python / tkinter)', '#1E8449')

    uml_class(ax, 16.0, 0.8, 7.2, 'RadarVisualizer',
        attrs=['- mode : str',
               '- settings : dict[str, DoubleVar]',
               '- node_angle_vars : dict[int, DoubleVar]',
               '- _udp_state : dict',
               '- _server_proc : Popen',
               '- _last_hits : dict'],
        methods=['+ _show_design_panel() : void',
                 '+ _show_live_panel() : void',
                 '+ _draw_radar() : void',
                 '+ _start_udp() : void',
                 '+ _update_node_cards(s) : void',
                 '+ _toggle_server() : void'],
        hc='#1E8449', bc='#D5F5E3', lfs=10)

    # ── relaciones ────────────────────────────────────────────────────────────

    # TaskComms usa SystemManager
    arr(ax, 8.0, 12.2, 6.4, 12.2,
        color='#555', lw=1.4, style='-->', cs='arc3,rad=0.0',
        label='usa (Singleton)', lfs=9, loy=0.22)

    # TaskRadar usa SystemManager
    arr(ax, 8.0, 9.3, 6.4, 10.8,
        color='#555', lw=1.4, style='-->',
        label='usa (Singleton)', lfs=9, lox=0.3, loy=0.25)

    # TaskRadar controla RadarHardware  (composición)
    arr(ax, 8.0, 8.5, 6.4, 8.0,
        color='#1F618D', lw=1.6, style='-|>',
        label='controla', lfs=9, loy=0.22)

    # SystemManager ── queueCommands ──► HwCommand
    arr(ax, 0.8 + 5.6/2, 4.2 + hw_h, 0.8 + 5.6/2, 10.5,
        color='#1A5276', lw=1.4, style='--',
        label='queueCommands', lfs=9, lox=0.9, loy=0)

    # SystemManager ── queueResults ──► HwResult
    arr(ax, 0.8 + 5.6/2 - 0.3, 2.1 + hr_h, 0.8 + 5.6/2 - 0.3, 10.5,
        color='#1A5276', lw=1.4, style='--',
        label='queueResults', lfs=9, lox=-1.1, loy=0)

    # ArbitroServer → RadarVisualizer (UDP)
    arr(ax, 16.0 + 7.2/2, 8.4, 16.0 + 7.2/2, 7.8,
        color='#7D3C98', lw=1.6, style='-->',
        label='UDP JSON\npuerto 8081', lfs=9, lox=1.6, loy=0)

    out = os.path.join(OUTDIR, 'diagrama_clases.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAMA 3 — Componentes UML
# ═══════════════════════════════════════════════════════════════════════════════

def comp(ax, x, y, w, h, name, color='#1F618D'):
    """Componente UML con icono en esquina."""
    box(ax, x, y, w, h, fc='#EBF5FB', ec=color, lw=1.8, rad=0.05, z=3)
    # icono UML de componente (rectángulo + 2 rectángulos pequeños a la izquierda)
    ix, iy = x + 0.1, y + h - 0.35
    ax.add_patch(FancyBboxPatch((ix, iy), 0.4, 0.25, boxstyle='square,pad=0',
                                 fc='white', ec=color, lw=1, zorder=5))
    ax.add_patch(FancyBboxPatch((ix - 0.12, iy + 0.05), 0.15, 0.06,
                                 boxstyle='square,pad=0', fc='white', ec=color, lw=1, zorder=5))
    ax.add_patch(FancyBboxPatch((ix - 0.12, iy + 0.14), 0.15, 0.06,
                                 boxstyle='square,pad=0', fc='white', ec=color, lw=1, zorder=5))
    t(ax, x + w/2, y + h/2, name, fs=12, bold=True, color=color, ha='center', z=4)

def dia_componentes():
    W, H = 22, 13
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')
    fig.patch.set_facecolor('white')

    t(ax, W/2, H - 0.3,
      'Diagrama de Componentes UML — Arquitectura de Software del Sistema',
      fs=16, bold=True, ha='center', color='#2c3e50')

    # ── Nodo ESP32 ────────────────────────────────────────────────────────────
    NX, NY, NW, NH = 0.5, 1.2, 6.8, 10.4
    box(ax, NX, NY, NW, NH, fc='#EBF5FB', ec='#1A5276', lw=2.5, rad=0.12)
    t(ax, NX + NW/2, NY + NH - 0.35, 'Nodo ESP32  (×3)',
      fs=14, bold=True, color='#1A5276', ha='center')
    t(ax, NX + NW/2, NY + NH - 0.7, 'FreeRTOS / C++',
      fs=11, italic=True, color='#2874A6', ha='center')

    comp(ax, NX + 0.4, NY + 7.2, NW - 0.8, 1.6,
         'TaskComms\n«task: Core 0»', '#1F618D')
    comp(ax, NX + 0.4, NY + 5.2, NW - 0.8, 1.6,
         'TaskRadar\n«task: Core 1»', '#1F618D')
    comp(ax, NX + 0.4, NY + 3.0, NW - 0.8, 1.7,
         'SystemManager\n«Singleton»\nqueueCommands | queueResults', '#1A5276')
    comp(ax, NX + 0.4, NY + 1.0, NW - 0.8, 1.6,
         'RadarHardware\n«HAL: GPIO Step/Dir, Trig/Echo»', '#1F618D')

    # flechas internas ESP32
    arr(ax, NX + NW/2, NY + 7.2, NX + NW/2, NY + 6.5,
        color='#1A5276', lw=1.5, label='HwCommand', lfs=9, lox=0.9, loy=0)
    arr(ax, NX + NW/2, NY + 5.2, NX + NW/2, NY + 4.7,
        color='#1A5276', lw=1.5, label='HwResult', lfs=9, lox=0.8, loy=0)
    arr(ax, NX + NW/2, NY + 3.0, NX + NW/2, NY + 2.6,
        color='#1F618D', lw=1.5, style='->')

    # ── Servidor Central ──────────────────────────────────────────────────────
    SX, SY, SW, SH = 8.8, 2.5, 6.5, 9.1
    box(ax, SX, SY, SW, SH, fc='#F4ECF7', ec='#7D3C98', lw=2.5, rad=0.12)
    t(ax, SX + SW/2, SY + SH - 0.35, 'Servidor Central',
      fs=14, bold=True, color='#7D3C98', ha='center')
    t(ax, SX + SW/2, SY + SH - 0.7, 'Python / TCP port 8080',
      fs=11, italic=True, color='#884EA0', ha='center')

    comp(ax, SX + 0.4, SY + 6.5, SW - 0.8, 1.6,
         'handle_client\n«hilo por nodo»\nParser TCP + Watchdog 15s', '#7D3C98')
    comp(ax, SX + 0.4, SY + 4.2, SW - 0.8, 1.9,
         'orchestration_loop\n«hilo demonio»\nTDMA · Conflictos · Trilateración', '#7D3C98')
    comp(ax, SX + 0.4, SY + 1.0, SW - 0.8, 2.8,
         'Estado Compartido\n[Threading.Lock]\nclient_sockets | track_states\nlatest_reports | track_lock', '#6C3483')

    # flechas internas servidor
    arr(ax, SX + SW/2, SY + 6.5, SX + SW/2, SY + 6.1,
        color='#7D3C98', lw=1.5, label='R/W', lfs=9, lox=0.5, loy=0)
    arr(ax, SX + SW/2, SY + 4.2, SX + SW/2, SY + 3.8,
        color='#7D3C98', lw=1.5, label='R/W', lfs=9, lox=0.5, loy=0)

    # ── Visualizador ──────────────────────────────────────────────────────────
    VX, VY, VW, VH = 16.8, 2.5, 4.8, 9.1
    box(ax, VX, VY, VW, VH, fc='#EAFAF1', ec='#1E8449', lw=2.5, rad=0.12)
    t(ax, VX + VW/2, VY + VH - 0.35, 'Visualizador',
      fs=14, bold=True, color='#1E8449', ha='center')
    t(ax, VX + VW/2, VY + VH - 0.7, 'Python / tkinter',
      fs=11, italic=True, color='#27AE60', ha='center')

    comp(ax, VX + 0.3, VY + 6.0, VW - 0.6, 1.6,
         'RadarVisualizer\nModo Diseño | Modo Telemetría', '#1E8449')
    comp(ax, VX + 0.3, VY + 4.0, VW - 0.6, 1.6,
         'Canvas 2D\n3 capas: bg / nodos / hits', '#1E8449')
    comp(ax, VX + 0.3, VY + 1.8, VW - 0.6, 1.8,
         'UDP Listener\n«hilo daemon»\npuerto 8081', '#27AE60')

    # flechas internas visualizador
    arr(ax, VX + VW/2, VY + 6.0, VX + VW/2, VY + 5.6,
        color='#1E8449', lw=1.5)
    arr(ax, VX + VW/2, VY + 4.0, VX + VW/2, VY + 3.6,
        color='#1E8449', lw=1.5)

    # ── flechas entre nodos ───────────────────────────────────────────────────

    # ESP32 ↔ Servidor (TCP)
    arr(ax, NX + NW, NY + NH * 0.68, SX, SY + SH * 0.68,
        color='#1A5276', lw=2.5,
        label='TCP / WiFi  puerto 8080\n[MSG_* binario little-endian]',
        lfs=11, loy=0.5)
    arr(ax, SX, SY + SH * 0.58, NX + NW, NY + NH * 0.58,
        color='#1A5276', lw=2.5,
        label='', lfs=10)

    # Servidor → Visualizador (UDP)
    arr(ax, SX + SW, SY + SH * 0.55, VX, VY + VH * 0.55,
        color='#1E8449', lw=2.5,
        label='UDP loopback  puerto 8081\n[JSON state por supertrama]',
        lfs=11, loy=0.5)

    out = os.path.join(OUTDIR, 'diagrama_componentes.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ─── diagrama FSM nodo ESP32 ──────────────────────────────────────────────────

def dia_fsm_nodo():
    """Flowchart del ciclo de vida del nodo ESP32 (FSM completa)."""
    fig, ax = plt.subplots(figsize=(14, 22))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 22)
    ax.axis('off')
    ax.set_facecolor('white')
    fig.patch.set_facecolor('white')
    ax.set_title('FSM del Nodo Sensor ESP32', fontsize=16, fontweight='bold',
                 color='#1C2833', pad=14)

    # ── colores ───────────────────────────────────────────────────────────────
    C_GREEN  = '#1E8449';  C_GREEN_L  = '#D5F5E3'
    C_ORANGE = '#CA6F1E';  C_ORANGE_L = '#FDEBD0'
    C_YELLOW = '#B7950B';  C_YELLOW_L = '#FEF9E7'
    C_BLUE   = '#1A5276';  C_BLUE_L   = '#D6EAF8'
    C_GRAY   = '#5D6D7E';  C_GRAY_L   = '#EBF5FB'
    C_RED    = '#922B21'

    # ── primitivas específicas del flowchart ──────────────────────────────────
    def fbox(x, y, w, h, label, fc, ec, fs=11):
        """Rectángulo de proceso."""
        ax.add_patch(FancyBboxPatch((x - w/2, y - h/2), w, h,
            boxstyle='round,pad=0.05', facecolor=fc, edgecolor=ec,
            linewidth=2.0, zorder=3))
        ax.text(x, y, label, ha='center', va='center',
                fontsize=fs, color='#1C2833', fontweight='bold',
                zorder=4, wrap=True,
                multialignment='center')

    def diamond(x, y, w, h, label, fc=C_YELLOW_L, ec=C_YELLOW, fs=10):
        """Rombo de decisión."""
        dx, dy = w/2, h/2
        xs = [x,      x+dx, x,      x-dx, x]
        ys = [y+dy,   y,    y-dy,   y,    y+dy]
        ax.fill(xs, ys, facecolor=fc, edgecolor=ec, linewidth=2.0, zorder=3)
        ax.text(x, y, label, ha='center', va='center',
                fontsize=fs, color='#1C2833', fontweight='bold',
                zorder=4, multialignment='center')

    def state_label(x, y, w, h, label):
        """Etiqueta de estado con borde discontinuo azul claro."""
        ax.add_patch(FancyBboxPatch((x - w/2, y - h/2), w, h,
            boxstyle='round,pad=0.1', facecolor='#EAF4FB', edgecolor='#5DADE2',
            linewidth=1.5, linestyle='dashed', zorder=1, alpha=0.55))
        ax.text(x, y + h/2 - 0.18, label, ha='center', va='top',
                fontsize=9, color='#1A5276', fontstyle='italic', zorder=5)

    def arrow(x1, y1, x2, y2, color='#2c3e50', lw=1.8, label='', lox=0, loy=0):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        if label:
            ax.text((x1+x2)/2 + lox, (y1+y2)/2 + loy, label,
                    ha='center', va='center', fontsize=9, color=color, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.9))

    def arrow_path(pts, color='#2c3e50', lw=1.8, label='', lox=0, loy=0):
        """Flecha multi-segmento; dibuja línea por los puntos y punta en el último."""
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, zorder=4,
                solid_capstyle='round')
        ax.annotate('', xy=pts[-1], xytext=pts[-2],
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        if label:
            mx = (xs[0]+xs[-1])/2 + lox
            my = (ys[0]+ys[-1])/2 + loy
            ax.text(mx, my, label, ha='center', va='center',
                    fontsize=9, color=color, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.9))

    # ── coordenadas X central ─────────────────────────────────────────────────
    CX = 7.0   # columna central
    BW = 4.2   # ancho caja proceso
    BH = 0.65  # alto caja proceso
    DW = 3.2   # ancho rombo
    DH = 0.80  # alto rombo

    # ── posiciones Y (de arriba a abajo, margen superior = 21.5) ─────────────
    Y_START   = 21.2
    Y_CFG1    = 20.2   # proceso: init queues
    Y_CFG2    = 19.3   # proceso: read MAC + NodeProfile
    Y_W4C_LBL = 17.8   # etiqueta estado
    Y_W4C_1   = 18.4   # proceso: escanear KNOWN_NETWORKS + LED 4 Hz
    Y_DEC1    = 17.2   # decisión: WIFI_GOT_IP?
    Y_SYNC_LBL= 15.3
    Y_SYNC_1  = 15.95  # proceso: arrancar TaskComms Core 0
    Y_DEC2    = 14.8   # decisión: IP en caché?
    Y_SYNC_2  = 13.75  # proceso: mDNS lookup
    Y_SYNC_3  = 12.85  # proceso: TCP connect
    Y_DEC3    = 11.75  # decisión: conexión TCP OK?
    Y_IO1     = 10.75  # I/O: enviar MSG_HELLO_REQ
    Y_DEC4    = 9.75   # decisión: MSG_HELLO_ACK?
    Y_RADAR_LBL=7.9
    Y_RADAR_1 = 8.55   # proceso: arrancar TaskRadar Core 1
    Y_RADAR_2 = 7.6    # proceso: ciclo TDMA continuo
    Y_DEC5    = 6.5    # decisión: TCP timeout 5000ms?
    Y_DEC6    = 5.2    # decisión: WiFi disconnect?
    Y_END     = 4.0    # RADAR operativo (estado terminal verde)

    # ── nodo INICIO ──────────────────────────────────────────────────────────
    fbox(CX, Y_START, 3.0, BH, 'Reset / Arranque', C_GREEN_L, C_GREEN, fs=12)
    arrow(CX, Y_START - BH/2, CX, Y_CFG1 + BH/2, color=C_GRAY)

    # ── CONFIGURACION ────────────────────────────────────────────────────────
    state_label(CX, (Y_CFG1 + Y_CFG2)/2, 6.5, 1.75, 'CONFIGURACIÓN')
    fbox(CX, Y_CFG1, BW, BH, 'Inicializar colas IPC (queueCommands / queueResults)', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_CFG1 - BH/2, CX, Y_CFG2 + BH/2, color=C_GRAY)
    fbox(CX, Y_CFG2, BW, BH, 'Leer MAC → cargar NodeProfile\n(id, motorDirInvert, reedTriggerLevel)', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_CFG2 - BH/2, CX, Y_W4C_1 + BH/2, color=C_GRAY)

    # ── WAITING_FOR_CONNECTION ───────────────────────────────────────────────
    state_label(CX, (Y_W4C_1 + Y_DEC1)/2 - 0.1, 6.8, 1.95, 'WAITING_FOR_CONNECTION')
    fbox(CX, Y_W4C_1, BW, BH, 'Escanear KNOWN_NETWORKS\nLED parpadeo 4 Hz', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_W4C_1 - BH/2, CX, Y_DEC1 + DH/2, color=C_GRAY)
    diamond(CX, Y_DEC1, DW, DH, '¿WIFI_GOT_IP?')
    # No → retorno izquierda
    arrow_path([(CX - DW/2, Y_DEC1),
                (2.2, Y_DEC1),
                (2.2, Y_W4C_1),
                (CX - BW/2, Y_W4C_1)],
               color=C_RED, label='No', lox=-0.4, loy=0.3)
    # Sí ↓
    arrow(CX, Y_DEC1 - DH/2, CX, Y_SYNC_1 + BH/2, color=C_GREEN, label='Sí', lox=0.3, loy=0.0)

    # ── SYNC_CONTROL ─────────────────────────────────────────────────────────
    state_label(CX, (Y_SYNC_1 + Y_DEC4)/2 - 0.1, 6.8, 7.1, 'SYNC_CONTROL')
    fbox(CX, Y_SYNC_1, BW, BH, 'Arrancar TaskComms en Core 0', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_SYNC_1 - BH/2, CX, Y_DEC2 + DH/2, color=C_GRAY)
    diamond(CX, Y_DEC2, DW, DH, '¿IP servidor en caché?')
    # Sí → saltar mDNS (rama derecha)
    arrow_path([(CX + DW/2, Y_DEC2),
                (10.8, Y_DEC2),
                (10.8, Y_SYNC_3),
                (CX + BW/2, Y_SYNC_3)],
               color=C_GREEN, label='Sí', lox=0.35, loy=0.3)
    # No ↓
    arrow(CX, Y_DEC2 - DH/2, CX, Y_SYNC_2 + BH/2, color=C_RED, label='No', lox=0.3, loy=0.0)
    fbox(CX, Y_SYNC_2, BW, BH, 'mDNS lookup (radar-server.local)\no IP gateway como fallback', C_BLUE_L, C_BLUE)
    arrow(CX, Y_SYNC_2 - BH/2, CX, Y_SYNC_3 + BH/2, color=C_GRAY)
    fbox(CX, Y_SYNC_3, BW, BH, 'Intentar conexión TCP\n(puerto 8080)', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_SYNC_3 - BH/2, CX, Y_DEC3 + DH/2, color=C_GRAY)
    diamond(CX, Y_DEC3, DW, DH, '¿Conexión TCP OK?')
    # No → reintentar (rama izquierda, vuelve a TCP connect)
    arrow_path([(CX - DW/2, Y_DEC3),
                (2.2, Y_DEC3),
                (2.2, Y_SYNC_3),
                (CX - BW/2, Y_SYNC_3)],
               color=C_RED, label='No', lox=-0.4, loy=0.3)
    # Sí ↓
    ax.add_patch(FancyBboxPatch((CX - BW/2, Y_IO1 - BH/2), BW, BH,
        boxstyle='round,pad=0.05', facecolor='#D6EAF8', edgecolor=C_BLUE,
        linewidth=2.0, zorder=3))
    ax.plot([CX - BW/2, CX - BW/2 - 0.25, CX - BW/2],
            [Y_IO1 - BH/2, Y_IO1, Y_IO1 + BH/2],
            color=C_BLUE, lw=2.0, zorder=4)
    ax.plot([CX + BW/2, CX + BW/2 + 0.25, CX + BW/2],
            [Y_IO1 - BH/2, Y_IO1, Y_IO1 + BH/2],
            color=C_BLUE, lw=2.0, zorder=4)
    ax.text(CX, Y_IO1, 'Enviar MSG_HELLO_REQ', ha='center', va='center',
            fontsize=11, color='#1C2833', fontweight='bold', zorder=5)
    arrow(CX, Y_DEC3 - DH/2, CX, Y_IO1 + BH/2, color=C_GREEN, label='Sí', lox=0.3, loy=0.0)
    arrow(CX, Y_IO1 - BH/2, CX, Y_DEC4 + DH/2, color=C_GRAY)
    diamond(CX, Y_DEC4, DW, DH, '¿MSG_HELLO_ACK\nrecibido?')
    # No → timeout, reiniciar SYNC (rama izquierda vuelve a TaskComms)
    arrow_path([(CX - DW/2, Y_DEC4),
                (1.5, Y_DEC4),
                (1.5, Y_SYNC_1),
                (CX - BW/2, Y_SYNC_1)],
               color=C_RED, label='No/timeout', lox=-0.5, loy=0.5)
    # Sí ↓
    arrow(CX, Y_DEC4 - DH/2, CX, Y_RADAR_1 + BH/2, color=C_GREEN, label='Sí', lox=0.3, loy=0.0)

    # ── RADAR ────────────────────────────────────────────────────────────────
    state_label(CX, (Y_RADAR_1 + Y_DEC6)/2 + 0.1, 6.8, 5.2, 'RADAR')
    fbox(CX, Y_RADAR_1, BW, BH, 'Arrancar TaskRadar en Core 1', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_RADAR_1 - BH/2, CX, Y_RADAR_2 + BH/2, color=C_GRAY)
    fbox(CX, Y_RADAR_2, BW, BH, 'Ciclo TDMA continuo\n(HOME → SYNC_POS → EXECUTE_SLOT)', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_RADAR_2 - BH/2, CX, Y_DEC5 + DH/2, color=C_GRAY)
    diamond(CX, Y_DEC5, DW, DH, '¿TCP timeout\n(> 5 000 ms)?')
    # Sí → HOME + volver a SYNC_CONTROL (rama derecha)
    arrow_path([(CX + DW/2, Y_DEC5),
                (11.5, Y_DEC5),
                (11.5, Y_SYNC_1),
                (CX + BW/2, Y_SYNC_1)],
               color=C_RED, label='Sí → HOME\n→ SYNC_CONTROL', lox=0.55, loy=0.3)
    # No ↓
    arrow(CX, Y_DEC5 - DH/2, CX, Y_DEC6 + DH/2, color=C_GREEN, label='No', lox=0.3, loy=0.0)
    diamond(CX, Y_DEC6, DW, DH, '¿WiFi disconnect?')
    # Sí → WAITING_FOR_CONNECTION (rama izquierda)
    arrow_path([(CX - DW/2, Y_DEC6),
                (1.0, Y_DEC6),
                (1.0, Y_W4C_1),
                (CX - BW/2, Y_W4C_1)],
               color=C_RED, label='Sí → WAITING', lox=-0.5, loy=0.3)
    # No ↓
    arrow(CX, Y_DEC6 - DH/2, CX, Y_END + BH/2, color=C_GREEN, label='No', lox=0.3, loy=0.0)
    fbox(CX, Y_END, 3.4, BH, 'RADAR operativo\n(ciclo nominal)', C_GREEN_L, C_GREEN, fs=12)
    # retorno ciclo continuo (loop hacia arriba al ciclo TDMA)
    arrow_path([(CX + 3.4/2, Y_END),
                (12.2, Y_END),
                (12.2, Y_RADAR_2),
                (CX + BW/2, Y_RADAR_2)],
               color=C_GREEN, lw=1.5, label='continúa', lox=0.5, loy=0.3)

    out = os.path.join(OUTDIR, 'diagrama_fsm_nodo.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ─── diagrama de secuencia EXECUTE_SLOT ──────────────────────────────────────

def dia_secuencia_slot():
    """Diagrama de secuencia UML del ciclo completo EXECUTE_SLOT."""
    fig, ax = plt.subplots(figsize=(13, 16))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 16)
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_title('Diagrama de Secuencia — Ciclo EXECUTE_SLOT',
                 fontsize=15, fontweight='bold', color='#1C2833', pad=14)

    C_BLUE   = '#1A5276'; C_BLUE_L   = '#D6EAF8'
    C_ORANGE = '#CA6F1E'; C_ORANGE_L = '#FDEBD0'
    C_RED    = '#922B21'; C_RED_L    = '#FADBD8'
    C_GREEN  = '#1E8449'; C_GREEN_L  = '#D5F5E3'
    C_GRAY   = '#5D6D7E'

    parts = [
        (1.4,  'Servidor\nCentral',      C_BLUE,   C_BLUE_L),
        (4.5,  'TaskComms\n(Core 0)',     C_ORANGE, C_ORANGE_L),
        (8.2,  'TaskRadar\n(Core 1)',     C_RED,    C_RED_L),
        (11.6, 'RadarHardware\n(GPIO)',   C_GREEN,  C_GREEN_L),
    ]
    Y_TOP = 15.2; BOX_H = 0.72; BOX_W = 1.75; Y_BOT = 0.6

    for x, lbl, ec, fc in parts:
        ax.add_patch(FancyBboxPatch((x - BOX_W/2, Y_TOP - BOX_H/2), BOX_W, BOX_H,
            boxstyle='round,pad=0.06', facecolor=fc, edgecolor=ec,
            linewidth=2.2, zorder=3))
        ax.text(x, Y_TOP, lbl, ha='center', va='center', fontsize=10,
                fontweight='bold', color='#1C2833', zorder=4, multialignment='center')
        ax.plot([x, x], [Y_TOP - BOX_H/2, Y_BOT],
                color=C_GRAY, lw=1.2, linestyle='dashed', zorder=1)

    x_srv, x_tc, x_tr, x_hw = [p[0] for p in parts]

    def msg(x1, x2, y, lbl, color, note=None):
        ax.annotate('', xy=(x2, y), xytext=(x1, y),
            arrowprops=dict(arrowstyle='->', color=color, lw=1.8,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        ax.text((x1+x2)/2, y+0.13, lbl, ha='center', va='bottom',
                fontsize=8.8, color=color, zorder=5,
                bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.92))
        if note:
            ax.text((x1+x2)/2, y-0.16, note, ha='center', va='top',
                    fontsize=7.8, color=C_GRAY, fontstyle='italic', zorder=5)

    def self_loop(x, y, lbl, color, w=0.85, h=0.5):
        ax.plot([x, x+w, x+w], [y, y, y-h], color=color, lw=1.8, zorder=4,
                solid_capstyle='round')
        ax.annotate('', xy=(x, y-h), xytext=(x+w, y-h),
            arrowprops=dict(arrowstyle='->', color=color, lw=1.8,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        ax.text(x+w+0.1, y-h/2, lbl, ha='left', va='center',
                fontsize=8.5, color=color, zorder=5)

    def act(x, y1, y2, fc, ec, w=0.24):
        ax.add_patch(FancyBboxPatch((x-w/2, y2), w, y1-y2,
            boxstyle='square,pad=0', facecolor=fc, edgecolor=ec,
            linewidth=1.0, alpha=0.55, zorder=2))

    def phase(y, lbl):
        ax.plot([0.2, 12.8], [y, y], color='#BDC3C7', lw=0.9,
                linestyle='dotted', zorder=2)
        ax.text(0.25, y+0.09, lbl, ha='left', va='bottom',
                fontsize=8.2, color='#7F8C8D', fontstyle='italic', zorder=5)

    def note_box(x, y, lbl, fc, ec):
        ax.text(x, y, lbl, ha='center', va='center', fontsize=8.8,
                color='#1C2833', fontweight='bold', zorder=5,
                bbox=dict(boxstyle='round,pad=0.3', fc=fc, ec=ec,
                          alpha=0.88, lw=1.3))

    # ── 1. Servidor envía comando ─────────────────────────────────────────────
    phase(14.3, '1  Recepción del comando')
    msg(x_srv, x_tc, 14.0,
        'MSG_SLOT (ángulo θ, t_ejecución)',
        C_BLUE)
    act(x_tc, 13.85, 13.4, C_ORANGE_L, C_ORANGE)

    # ── 2. TaskComms despacha a queueCommands ─────────────────────────────────
    phase(13.2, '2  Despacho IPC  →  queueCommands')
    msg(x_tc, x_tr, 12.9,
        'HwCommand { EXECUTE_SLOT, θ, t_ms }',
        C_ORANGE,
        note='encolado con portMAX_DELAY  —  TaskRadar desbloquea')
    act(x_tr, 12.75, 12.3, C_RED_L, C_RED)

    # ── 3. Posicionamiento del motor ──────────────────────────────────────────
    phase(12.1, '3  Posicionamiento del motor paso a paso')
    msg(x_tr, x_hw, 11.8, 'moverA(θ)', C_RED)
    act(x_hw, 11.65, 10.85, C_GREEN_L, C_GREEN)
    msg(x_hw, x_tr, 10.9, 'posición confirmada', C_GREEN)

    # ── 4. Espera hasta slot TDMA ─────────────────────────────────────────────
    phase(10.6, '4  Espera hasta el instante t_ejecución  (slot TDMA)')
    note_box((x_tr+x_hw)/2, 10.25,
             'delay hasta execution_time_ms\n[sincronización supertrama]',
             '#FEF9E7', '#B7950B')

    # ── 5. Medición ToF ───────────────────────────────────────────────────────
    phase(9.7, '5  Medición por tiempo de vuelo (ToF)')
    msg(x_tr, x_hw, 9.4, 'dispararPulso()', C_RED)
    act(x_hw, 9.27, 8.15, C_GREEN_L, C_GREEN)
    self_loop(x_hw, 9.0, 'esperar eco\n(timeout 15 ms)', C_GREEN)
    msg(x_hw, x_tr, 8.2, 't_eco  [µs]', C_GREEN)

    # ── 6. Cálculo de distancia ───────────────────────────────────────────────
    phase(7.95, '6  Cálculo de distancia')
    note_box((x_tr+x_hw)/2, 7.6,
             'd  =  t_eco / 58,0   [cm]',
             C_RED_L, C_RED)

    # ── 7. Resultado IPC → queueResults ──────────────────────────────────────
    phase(7.2, '7  Resultado IPC  →  queueResults')
    msg(x_tr, x_tc, 6.9,
        'HwResult { distancia, ángulo }',
        C_RED,
        note='encolado con portMAX_DELAY  —  TaskComms desbloquea')
    act(x_tc, 6.75, 6.2, C_ORANGE_L, C_ORANGE)

    # ── 8. Envío al servidor ──────────────────────────────────────────────────
    phase(6.0, '8  Envío del resultado al servidor')
    msg(x_tc, x_srv, 5.7,
        'MSG_RESULT (distancia, ángulo)',
        C_BLUE)

    # ── nota reintentos ───────────────────────────────────────────────────────
    ax.text(6.5, 4.9,
            '* Ante medición fallida: hasta 2 reintentos antes de notificar fuera de rango al servidor',
            ha='center', va='center', fontsize=8, color=C_GRAY,
            fontstyle='italic', zorder=5,
            bbox=dict(boxstyle='round,pad=0.25', fc='#FDFEFE',
                      ec='#BDC3C7', alpha=0.9, lw=0.9))

    out = os.path.join(OUTDIR, 'diagrama_secuencia_slot.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ─── diagrama trilateración ───────────────────────────────────────────────────

def dia_trilateracion():
    """Diagrama de localización cooperativa por par activo (N1-N2 o N2-N3)."""
    import numpy as np
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(13, 10))
    ax.set_xlim(-1.2, 13.8)
    ax.set_ylim(-1.8, 10.5)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_title('Localización Cooperativa — Cálculo de Coordenadas por Par Activo',
                 fontsize=14, fontweight='bold', color='#1C2833', pad=14)

    C_N1 = '#1A5276'; C_N1L = '#D6EAF8'
    C_N2 = '#1E8449'; C_N2L = '#D5F5E3'
    C_N3 = '#7D3C98'; C_N3L = '#E8DAEF'
    C_OBJ = '#C0392B'
    C_MID = '#E67E22'
    C_GRAY = '#5D6D7E'

    # ── posiciones de los nodos ────────────────────────────────────────────────
    N1 = (1.0,  0.5)
    N2 = (6.5,  0.5)
    N3 = (12.0, 0.5)
    target_real = (4.5, 7.5)

    # ── estimaciones polares de cada nodo (con error angular pequeño) ──────────
    dx1 = target_real[0] - N1[0]; dy1 = target_real[1] - N1[1]
    d1  = np.hypot(dx1, dy1)
    a1  = np.degrees(np.arctan2(dy1, dx1))
    P1  = (N1[0] + d1 * np.cos(np.radians(a1 + 2.5)),
           N1[1] + d1 * np.sin(np.radians(a1 + 2.5)))

    dx2 = target_real[0] - N2[0]; dy2 = target_real[1] - N2[1]
    d2  = np.hypot(dx2, dy2)
    a2  = np.degrees(np.arctan2(dy2, dx2))
    P2  = (N2[0] + d2 * np.cos(np.radians(a2 - 2.5)),
           N2[1] + d2 * np.sin(np.radians(a2 - 2.5)))

    Pfinal = ((P1[0] + P2[0]) / 2, (P1[1] + P2[1]) / 2)

    # ── rayos de medición (línea discontinua de cada nodo a su estimación) ────
    ax.plot([N1[0], P1[0]], [N1[1], P1[1]],
            color=C_N1, lw=2.0, linestyle='dashed', alpha=0.75, zorder=3)
    ax.plot([N2[0], P2[0]], [N2[1], P2[1]],
            color=C_N2, lw=2.0, linestyle='dashed', alpha=0.75, zorder=3)

    # ── arcos de ángulo ────────────────────────────────────────────────────────
    for node, angle, color in [(N1, a1, C_N1), (N2, a2, C_N2)]:
        arc = mpatches.Arc(node, 2.2, 2.2, angle=0,
                           theta1=0, theta2=angle,
                           color=color, lw=1.4, linestyle='dotted', zorder=4)
        ax.add_patch(arc)

    # ── etiquetas de ángulo ────────────────────────────────────────────────────
    ax.text(N1[0] + 1.35, N1[1] + 0.55, f'θ₁ ≈ {a1:.0f}°',
            ha='left', va='center', fontsize=8.5, color=C_N1, fontweight='bold', zorder=6)
    ax.text(N2[0] - 1.45, N2[1] + 0.55, f'θ₂ ≈ {a2:.0f}°',
            ha='right', va='center', fontsize=8.5, color=C_N2, fontweight='bold', zorder=6)

    # ── estimaciones locales P1, P2 ───────────────────────────────────────────
    ax.add_patch(plt.Circle(P1, 0.22, facecolor=C_N1L, edgecolor=C_N1, lw=2.0, zorder=5))
    ax.text(P1[0] - 0.6, P1[1] + 0.4, 'P₁\n(est. N1)',
            ha='center', va='bottom', fontsize=8.5, color=C_N1, fontweight='bold', zorder=6)

    ax.add_patch(plt.Circle(P2, 0.22, facecolor=C_N2L, edgecolor=C_N2, lw=2.0, zorder=5))
    ax.text(P2[0] + 0.6, P2[1] + 0.4, 'P₂\n(est. N2)',
            ha='center', va='bottom', fontsize=8.5, color=C_N2, fontweight='bold', zorder=6)

    # ── línea de promedio P1→P2 ───────────────────────────────────────────────
    ax.plot([P1[0], P2[0]], [P1[1], P2[1]],
            color=C_MID, lw=1.6, linestyle='dotted', zorder=4)

    # ── etiquetas de distancia ────────────────────────────────────────────────
    mx1 = (N1[0] + P1[0]) / 2; my1 = (N1[1] + P1[1]) / 2
    ax.text(mx1 - 0.65, my1, f'd₁ = {d1:.1f} cm',
            ha='center', va='center', fontsize=9, color=C_N1, fontweight='bold', zorder=5,
            bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.85))
    mx2 = (N2[0] + P2[0]) / 2; my2 = (N2[1] + P2[1]) / 2
    ax.text(mx2 + 0.65, my2, f'd₂ = {d2:.1f} cm',
            ha='center', va='center', fontsize=9, color=C_N2, fontweight='bold', zorder=5,
            bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.85))

    # ── objetivo final ────────────────────────────────────────────────────────
    ax.add_patch(plt.Circle(Pfinal, 0.32, facecolor='#FADBD8',
                            edgecolor=C_OBJ, lw=2.5, zorder=6))
    ax.plot(Pfinal[0], Pfinal[1], 'x',
            color=C_OBJ, markersize=15, markeredgewidth=2.5, zorder=8)
    ax.text(Pfinal[0] + 0.55, Pfinal[1] + 0.4,
            f'P_final = ({Pfinal[0]:.1f}, {Pfinal[1]:.1f})',
            ha='left', va='center', fontsize=10, fontweight='bold', color=C_OBJ, zorder=7,
            bbox=dict(boxstyle='round,pad=0.3', fc='#FADBD8', ec=C_OBJ, alpha=0.9, lw=1.5))

    # ── nodos ─────────────────────────────────────────────────────────────────
    node_defs = [('N1', N1, C_N1, C_N1L, 1.0),
                 ('N2', N2, C_N2, C_N2L, 1.0),
                 ('N3', N3, C_N3, C_N3L, 0.28)]
    for name, pos, c, cl, alpha in node_defs:
        ax.add_patch(plt.Circle(pos, 0.35, facecolor=cl, edgecolor=c,
                                lw=2.5, zorder=6, alpha=alpha))
        ax.text(pos[0], pos[1], name, ha='center', va='center',
                fontsize=11, fontweight='bold', color=c, zorder=7, alpha=alpha)
        ax.text(pos[0], pos[1] - 0.65, f'({pos[0]:.0f}, {pos[1]:.0f})',
                ha='center', va='top', fontsize=8, color=C_GRAY, zorder=7, alpha=alpha)

    ax.text(N3[0], N3[1] + 0.75, 'inactivo\nen este par',
            ha='center', va='bottom', fontsize=8, color=C_N3,
            fontstyle='italic', alpha=0.45, zorder=6)

    # ── perímetro defensivo ───────────────────────────────────────────────────
    ax.plot([-0.8, 13.2], [0.0, 0.0],
            color='#2C3E50', lw=2.5, zorder=3, solid_capstyle='round')
    ax.text(13.3, 0.0, 'Perímetro\ndefensivo',
            ha='left', va='center', fontsize=8.5, color='#2C3E50', fontstyle='italic')

    # ── fórmulas ──────────────────────────────────────────────────────────────
    eq_x, eq_y = -1.0, 10.2
    ax.text(eq_x, eq_y, 'Cálculo por par activo  (ej. N1–N2):',
            ha='left', va='top', fontsize=9.5,
            color='#1C2833', fontweight='bold', zorder=5)
    eqs = [
        ('P₁ = (x₁ + d₁·cos θ₁,  y₁ + d₁·sin θ₁)', C_N1),
        ('P₂ = (x₂ + d₂·cos θ₂,  y₂ + d₂·sin θ₂)', C_N2),
        ('P_final = (P₁ + P₂) / 2                  ', C_OBJ),
    ]
    for i, (eq, c) in enumerate(eqs):
        ax.text(eq_x + 0.3, eq_y - 0.78 - i * 0.66, eq,
                ha='left', va='top', fontsize=9,
                color=c, fontfamily='monospace', zorder=5,
                bbox=dict(boxstyle='round,pad=0.2', fc='white', ec=c, alpha=0.7, lw=1.0))
    ax.text(eq_x + 0.3, eq_y - 0.78 - 3 * 0.66 - 0.1,
            'Pares activos:  N1–N2  o  N2–N3   (CONFLICT_PAIRS)',
            ha='left', va='top', fontsize=8.5, color=C_GRAY, fontstyle='italic', zorder=5,
            bbox=dict(boxstyle='round,pad=0.2', fc='#F8F9FA', ec='#BDC3C7', alpha=0.9, lw=0.8))

    # ── leyenda ───────────────────────────────────────────────────────────────
    leg_x, leg_y = 8.8, 10.2
    ax.add_patch(FancyBboxPatch((leg_x - 0.2, leg_y - 3.45), 4.5, 3.65,
        boxstyle='round,pad=0.1', facecolor='#F8F9FA',
        edgecolor='#BDC3C7', linewidth=1.2, zorder=4))
    ax.text(leg_x + 2.05, leg_y, 'Leyenda',
            ha='center', va='top', fontsize=9.5,
            fontweight='bold', color='#1C2833', zorder=5)
    legend_items = [
        (C_N1,  'N1, N2 — Nodos del par activo'),
        (C_N3,  'N3 — Nodo no participante'),
        (C_OBJ, 'P_final — Posición estimada'),
        (C_MID, 'P₁, P₂ — Estimaciones locales'),
    ]
    for i, (c, lbl) in enumerate(legend_items):
        ax.add_patch(plt.Circle((leg_x + 0.15, leg_y - 0.62 - i * 0.58),
                                0.13, facecolor=c, edgecolor=c, zorder=5))
        ax.text(leg_x + 0.45, leg_y - 0.62 - i * 0.58, lbl,
                ha='left', va='center', fontsize=8.8, color='#1C2833', zorder=5)

    out = os.path.join(OUTDIR, 'diagrama_trilateracion.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ─── flowchart bucle orquestación servidor ────────────────────────────────────

def dia_fsm_servidor():
    """Flowchart del bucle de orquestación del servidor central (ArbitroServer)."""
    W, H = 14, 25
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')
    fig.patch.set_facecolor('white')

    C_GREEN  = '#1E8449'; C_GREEN_L  = '#D5F5E3'
    C_BLUE   = '#1A5276'; C_BLUE_L   = '#D6EAF8'
    C_ORANGE = '#CA6F1E'; C_ORANGE_L = '#FDEBD0'
    C_PURPLE = '#6C3483'; C_PURPLE_L = '#E8DAEF'
    C_CYAN   = '#117A65'; C_CYAN_L   = '#D1F2EB'
    C_RED    = '#922B21'
    C_GRAY   = '#5D6D7E'

    ax.text(W/2, H - 0.30,
            'Diagrama de Flujo — Bucle de Orquestación del Servidor Central',
            ha='center', va='center', fontsize=14, fontweight='bold', color='#2c3e50')
    ax.text(W/2, H - 0.78,
            'ArbitroServer  ·  server_central.py',
            ha='center', va='center', fontsize=11, fontstyle='italic', color='#7f8c8d')

    CX = 7.0; BW = 4.8; BH = 0.68; DW = 3.4; DH = 0.88

    def fbox(cx, cy, w, h, label, fc, ec, fs=10):
        ax.add_patch(FancyBboxPatch((cx - w/2, cy - h/2), w, h,
            boxstyle='round,pad=0.05', facecolor=fc, edgecolor=ec,
            linewidth=2.0, zorder=3))
        ax.text(cx, cy, label, ha='center', va='center',
                fontsize=fs, color='#1C2833', fontweight='bold',
                zorder=4, multialignment='center')

    def diamond(cx, cy, w, h, label):
        xs = [cx, cx+w/2, cx, cx-w/2, cx]
        ys = [cy+h/2, cy, cy-h/2, cy, cy+h/2]
        ax.fill(xs, ys, facecolor='#FCF3CF', edgecolor='#9A7D0A', lw=2.0, zorder=3)
        ax.text(cx, cy, label, ha='center', va='center',
                fontsize=9, color='#1C2833', fontweight='bold',
                zorder=4, multialignment='center')

    def state_region(cx, cy, w, h, label, ec, fc, tc):
        ax.add_patch(FancyBboxPatch((cx - w/2, cy - h/2), w, h,
            boxstyle='round,pad=0.12', facecolor=fc, edgecolor=ec,
            linewidth=1.8, linestyle='dashed', zorder=1, alpha=0.45))
        ax.text(cx + w/2 + 0.18, cy, label,
                ha='left', va='center', fontsize=10, fontweight='bold',
                color=tc, fontstyle='italic', zorder=5, multialignment='center')

    def arrow(x1, y1, x2, y2, color='#2c3e50', lw=1.8, label='', lox=0, loy=0):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        if label:
            ax.text((x1+x2)/2 + lox, (y1+y2)/2 + loy, label,
                    ha='center', va='center', fontsize=9, color=color, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.9))

    def arrow_path(pts, color='#2c3e50', lw=1.8, label='', lox=0, loy=0):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, zorder=4, solid_capstyle='round')
        ax.annotate('', xy=pts[-1], xytext=pts[-2],
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        if label:
            ax.text((xs[0]+xs[-1])/2 + lox, (ys[0]+ys[-1])/2 + loy, label,
                    ha='center', va='center', fontsize=9, color=color, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.9))

    # Y positions (top to bottom)
    Y_START  = 23.5
    Y_INIT1  = 22.4
    Y_INIT2  = 21.3
    Y_DEC_NC = 20.1
    Y_F1     = 18.8
    Y_F2     = 17.6
    Y_DEC_A  = 16.5
    Y_F3     = 15.2
    Y_F4     = 14.1
    Y_WAIT   = 12.9
    Y_F5     = 11.8
    Y_F6     = 10.7
    Y_DEC_R  =  9.5
    Y_PROC   =  8.3
    Y_UDP    =  7.2
    Y_SAVE   =  6.1
    Y_INC    =  5.1

    # state regions
    state_region(CX, (Y_START + Y_INIT2) / 2,
                 BW + 1.2, Y_START - Y_INIT2 + BH + 0.6,
                 'ARRANQUE', C_GREEN, C_GREEN_L, C_GREEN)
    state_region(CX, (Y_F1 + Y_INC) / 2,
                 BW + 1.2, Y_F1 - Y_INC + BH + 0.8,
                 'SUPERTRAMA\n(loop continuo)', C_PURPLE, '#F5EEF8', C_PURPLE)

    # ARRANQUE
    fbox(CX, Y_START, 3.4, BH, 'Arranque\n(server_central.py)', C_GREEN_L, C_GREEN, fs=11)
    arrow(CX, Y_START - BH/2, CX, Y_INIT1 + BH/2, color=C_GRAY)
    fbox(CX, Y_INIT1, BW, BH,
         'Registrar mDNS (radar-server.local)  ·  TCP listen :8080',
         C_BLUE_L, C_BLUE)
    arrow(CX, Y_INIT1 - BH/2, CX, Y_INIT2 + BH/2, color=C_GRAY)
    fbox(CX, Y_INIT2, BW, BH,
         'Hilo orquestación  +  1 hilo handler TCP por nodo',
         C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_INIT2 - BH/2, CX, Y_DEC_NC + DH/2, color=C_GRAY)

    # decision: nodos conectados
    diamond(CX, Y_DEC_NC, DW, DH, '¿Nodos\nconectados?')
    arrow_path([(CX - DW/2, Y_DEC_NC),
                (2.4,        Y_DEC_NC),
                (2.4,        Y_INIT2),
                (CX - BW/2,  Y_INIT2)],
               color=C_RED, label='No\n(sleep 0.5 s)', lox=-0.55, loy=0.35)
    arrow(CX, Y_DEC_NC - DH/2, CX, Y_F1 + BH/2,
          color=C_GREEN, label='Sí', lox=0.3, loy=0)

    # FASE 1
    fbox(CX, Y_F1, BW, BH,
         'FASE 1  ·  Difundir MSG_SUPERFRAME_START\n'
         '(t₀ = instante de recepción en cada nodo)',
         C_PURPLE_L, C_PURPLE)
    arrow(CX, Y_F1 - BH/2, CX, Y_F2 + BH/2, color=C_GRAY)

    # FASE 2
    fbox(CX, Y_F2, BW, BH,
         'FASE 2  ·  Esperar MSG_ANGLE_REQ\n'
         '(ventana 500 ms  ·  un mensaje por nodo activo)',
         C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_F2 - BH/2, CX, Y_DEC_A + DH/2, color=C_GRAY)
    diamond(CX, Y_DEC_A, DW, DH, '¿ANGLE_REQ\nrecibido?')
    arrow_path([(CX + DW/2,  Y_DEC_A),
                (12.0,        Y_DEC_A),
                (12.0,        Y_F3 + 0.15),
                (CX + BW/2,   Y_F3 + 0.15)],
               color=C_RED,
               label='No → strike++\n(kick en strike 7)\ncontinua sin él',
               lox=1.05, loy=0.3)
    arrow(CX, Y_DEC_A - DH/2, CX, Y_F3 + BH/2,
          color=C_GREEN, label='Sí', lox=0.3, loy=0)

    # FASE 3
    fbox(CX, Y_F3, BW, BH,
         'FASE 3  ·  Calcular asignación de slots\n'
         '(zona sucia >30°  ·  separación angular <30°)',
         C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_F3 - BH/2, CX, Y_F4 + BH/2, color=C_GRAY)

    # FASE 4
    fbox(CX, Y_F4, BW, BH,
         'FASE 4  ·  Enviar MSG_SLOT_ASSIGN\n'
         '(ángulo confirmado  +  delay_from_sf_ms por nodo)',
         C_PURPLE_L, C_PURPLE)
    arrow(CX, Y_F4 - BH/2, CX, Y_WAIT + BH/2, color=C_GRAY)
    fbox(CX, Y_WAIT, BW, BH,
         'Esperar  T_mov,max + offset de slot\n'
         '(nodos en movimiento y midiendo de forma autónoma)',
         C_CYAN_L, C_CYAN)
    arrow(CX, Y_WAIT - BH/2, CX, Y_F5 + BH/2, color=C_GRAY)

    # FASE 5
    fbox(CX, Y_F5, BW, BH,
         'FASE 5  ·  Enviar MSG_REPORT_REQ a todos\n'
         '(señal de recogida  ·  payload vacío)',
         C_PURPLE_L, C_PURPLE)
    arrow(CX, Y_F5 - BH/2, CX, Y_F6 + BH/2, color=C_GRAY)
    fbox(CX, Y_F6, BW, BH,
         'Esperar MSG_DATA_REPORT\n'
         '(timeout: T_mov,max + 400 ms)',
         C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_F6 - BH/2, CX, Y_DEC_R + DH/2, color=C_GRAY)
    diamond(CX, Y_DEC_R, DW, DH, '¿DATA_REPORT\nrecibido?')
    arrow_path([(CX + DW/2,  Y_DEC_R),
                (12.0,        Y_DEC_R),
                (12.0,        Y_PROC + 0.15),
                (CX + BW/2,   Y_PROC + 0.15)],
               color=C_RED,
               label='No → strike++\n(kick en strike 7)\ncontinua sin él',
               lox=1.05, loy=0.3)
    arrow(CX, Y_DEC_R - DH/2, CX, Y_PROC + BH/2,
          color=C_GREEN, label='Sí', lox=0.3, loy=0)

    # FASE 6
    fbox(CX, Y_PROC, BW, BH,
         'FASE 6  ·  Actualizar estado SEARCH/TRACK\n'
         '(conflictos zona sucia  ·  coordenadas globales)',
         C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_PROC - BH/2, CX, Y_UDP + BH/2, color=C_GRAY)
    fbox(CX, Y_UDP, BW, BH,
         'Emitir JSON por UDP :8081\n(estado completo al visualizador)',
         C_BLUE_L, C_BLUE)
    arrow(CX, Y_UDP - BH/2, CX, Y_SAVE + BH/2, color=C_GRAY)
    fbox(CX, Y_SAVE, BW, BH,
         'Guardar radar_state.json\n(cada 15 superframes)',
         C_GREEN_L, C_GREEN)
    arrow(CX, Y_SAVE - BH/2, CX, Y_INC + BH/2, color=C_GRAY)
    fbox(CX, Y_INC, 2.8, BH, 'seq++', C_PURPLE_L, C_PURPLE)

    # loop back
    arrow_path([(CX - 2.8/2, Y_INC),
                (2.3,         Y_INC),
                (2.3,         Y_F1),
                (CX - BW/2,   Y_F1)],
               color=C_PURPLE, lw=2.0,
               label='siguiente\nsupertrama', lox=-0.65, loy=0.3)

    out = os.path.join(OUTDIR, 'diagrama_fsm_servidor.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ─── diagrama descubrimiento mDNS ────────────────────────────────────────────

def dia_mdns():
    """Flowchart del descubrimiento automático del servidor (mDNS + fallback)."""
    W, H = 11, 18
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')
    fig.patch.set_facecolor('white')

    C_GREEN  = '#1E8449'; C_GREEN_L  = '#D5F5E3'
    C_BLUE   = '#1A5276'; C_BLUE_L   = '#D6EAF8'
    C_ORANGE = '#CA6F1E'; C_ORANGE_L = '#FDEBD0'
    C_RED    = '#922B21'
    C_GRAY   = '#5D6D7E'

    ax.text(W/2, H - 0.28,
            'Descubrimiento Automático del Servidor',
            ha='center', va='center', fontsize=13, fontweight='bold', color='#2c3e50')
    ax.text(W/2, H - 0.72,
            'Ejecutado por TaskComms tras obtener IP WiFi',
            ha='center', va='center', fontsize=10, fontstyle='italic', color='#7f8c8d')

    CX = 5.5; BW = 4.2; BH = 0.68; DW = 3.4; DH = 0.85

    def fbox(cx, cy, w, h, label, fc, ec, fs=10):
        ax.add_patch(FancyBboxPatch((cx - w/2, cy - h/2), w, h,
            boxstyle='round,pad=0.05', facecolor=fc, edgecolor=ec,
            linewidth=2.0, zorder=3))
        ax.text(cx, cy, label, ha='center', va='center',
                fontsize=fs, color='#1C2833', fontweight='bold',
                zorder=4, multialignment='center')

    def iobox(cx, cy, w, h, label, fc, ec, fs=10):
        """Caja de I/O con bordes en paralelo (estilo I/O de flowchart)."""
        sk = 0.22
        xs = [cx-w/2+sk, cx+w/2+sk, cx+w/2-sk, cx-w/2-sk, cx-w/2+sk]
        ys = [cy-h/2,    cy-h/2,    cy+h/2,    cy+h/2,    cy-h/2   ]
        ax.fill(xs, ys, facecolor=fc, edgecolor=ec, lw=2.0, zorder=3)
        ax.text(cx, cy, label, ha='center', va='center',
                fontsize=fs, color='#1C2833', fontweight='bold',
                zorder=4, multialignment='center')

    def diamond(cx, cy, w, h, label):
        xs = [cx, cx+w/2, cx, cx-w/2, cx]
        ys = [cy+h/2, cy, cy-h/2, cy, cy+h/2]
        ax.fill(xs, ys, facecolor='#FCF3CF', edgecolor='#9A7D0A', lw=2.0, zorder=3)
        ax.text(cx, cy, label, ha='center', va='center',
                fontsize=9, color='#1C2833', fontweight='bold',
                zorder=4, multialignment='center')

    def arrow(x1, y1, x2, y2, color='#2c3e50', lw=1.8, label='', lox=0, loy=0):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        if label:
            ax.text((x1+x2)/2 + lox, (y1+y2)/2 + loy, label,
                    ha='center', va='center', fontsize=9, color=color, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.9))

    def arrow_path(pts, color='#2c3e50', lw=1.8, label='', lox=0, loy=0):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, zorder=4, solid_capstyle='round')
        ax.annotate('', xy=pts[-1], xytext=pts[-2],
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            connectionstyle='arc3,rad=0.0'), zorder=4)
        if label:
            ax.text((xs[0]+xs[-1])/2 + lox, (ys[0]+ys[-1])/2 + loy, label,
                    ha='center', va='center', fontsize=9, color=color, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.9))

    # ── Y positions ───────────────────────────────────────────────────────────
    Y_START   = 16.8
    Y_PWRSAVE = 15.7
    Y_DEC_C   = 14.6   # ¿IP en caché?
    Y_MDNS    = 13.3   # consultar mDNS
    Y_DEC_M   = 12.2   # ¿mDNS OK?
    Y_GW      = 11.1   # usar gateway
    Y_TCP     = 10.0   # intentar conexión TCP  ← punto de convergencia
    Y_DEC_T   =  8.9   # ¿conexión OK?
    Y_INVAL   =  7.9   # invalidar caché + esperar
    Y_CACHE   =  7.7   # cachear IP + Nagle off  (rama Sí)
    Y_HELLO   =  6.5   # enviar MSG_HELLO_REQ
    Y_END     =  5.3   # fin: esperando ACK

    # ── nodo inicio ──────────────────────────────────────────────────────────
    fbox(CX, Y_START, 3.2, BH, 'Inicio: WiFi conectado', C_GREEN_L, C_GREEN, fs=11)
    arrow(CX, Y_START - BH/2, CX, Y_PWRSAVE + BH/2, color=C_GRAY)

    fbox(CX, Y_PWRSAVE, BW, BH,
         'Deshabilitar modo ahorro\nde energía WiFi', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_PWRSAVE - BH/2, CX, Y_DEC_C + DH/2, color=C_GRAY)

    # ── decisión caché ────────────────────────────────────────────────────────
    diamond(CX, Y_DEC_C, DW, DH, '¿IP del servidor\nen caché?')

    # Sí: salta directamente a Y_TCP (rama derecha)
    arrow_path([(CX + DW/2, Y_DEC_C),
                (9.4,        Y_DEC_C),
                (9.4,        Y_TCP),
                (CX + BW/2,  Y_TCP)],
               color=C_GREEN, label='Sí', lox=0.35, loy=0.3)

    # No: baja a mDNS
    arrow(CX, Y_DEC_C - DH/2, CX, Y_MDNS + BH/2,
          color=C_RED, label='No', lox=0.3, loy=0)

    # ── mDNS ─────────────────────────────────────────────────────────────────
    fbox(CX, Y_MDNS, BW, BH,
         'Consultar mDNS:\nradar-server.local (2 intentos)', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_MDNS - BH/2, CX, Y_DEC_M + DH/2, color=C_GRAY)

    diamond(CX, Y_DEC_M, DW, DH, '¿Respuesta\nmDNS recibida?')

    # Sí: salta a Y_TCP (rama derecha, misma columna que caché)
    arrow_path([(CX + DW/2, Y_DEC_M),
                (9.4,        Y_DEC_M),
                (9.4,        Y_TCP),
                (CX + BW/2,  Y_TCP)],
               color=C_GREEN, label='Sí', lox=0.35, loy=0.3)

    # No: baja a gateway
    arrow(CX, Y_DEC_M - DH/2, CX, Y_GW + BH/2,
          color=C_RED, label='No', lox=0.3, loy=0)

    fbox(CX, Y_GW, BW, BH,
         'Usar IP del gateway\ncomo fallback', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_GW - BH/2, CX, Y_TCP + BH/2, color=C_GRAY)

    # ── TCP (punto de convergencia) ───────────────────────────────────────────
    fbox(CX, Y_TCP, BW, BH,
         'Intentar conexión TCP\nal puerto 8080', C_BLUE_L, C_BLUE)
    arrow(CX, Y_TCP - BH/2, CX, Y_DEC_T + DH/2, color=C_GRAY)

    diamond(CX, Y_DEC_T, DW, DH, '¿Conexión TCP\nexitosa?')

    # No: invalidar caché + esperar → loop al principio
    arrow_path([(CX - DW/2,  Y_DEC_T),
                (1.1,         Y_DEC_T),
                (1.1,         Y_DEC_C),
                (CX - DW/2,   Y_DEC_C)],
               color=C_RED,
               label='No\nInvalidar caché\nEsperar 2 s', lox=-0.7, loy=0.3)

    # Sí: cachear + Nagle off
    arrow(CX, Y_DEC_T - DH/2, CX, Y_CACHE + BH/2,
          color=C_GREEN, label='Sí', lox=0.3, loy=0)

    fbox(CX, Y_CACHE, BW, BH,
         'Cachear IP  ·  Activar TCP\nsin retardo de Nagle', C_ORANGE_L, C_ORANGE)
    arrow(CX, Y_CACHE - BH/2, CX, Y_HELLO + BH/2, color=C_GRAY)

    # ── I/O MSG_HELLO_REQ ─────────────────────────────────────────────────────
    iobox(CX, Y_HELLO, BW, BH,
          'Enviar MSG_HELLO_REQ\n(dirección MAC)', C_BLUE_L, C_BLUE)
    arrow(CX, Y_HELLO - BH/2, CX, Y_END + BH/2, color=C_GRAY)

    fbox(CX, Y_END, 3.4, BH,
         'Fin: esperando\nMSG_HELLO_ACK', C_GREEN_L, C_GREEN, fs=11)

    out = os.path.join(OUTDIR, 'diagrama_mdns.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'OK {out}')


# ─── main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('Generando diagramas UML...')
    dia_estados()
    dia_clases()
    dia_componentes()
    dia_fsm_nodo()
    dia_secuencia_slot()
    dia_trilateracion()
    dia_fsm_servidor()
    dia_mdns()
    print('Listo. Imágenes guardadas en:', OUTDIR)
