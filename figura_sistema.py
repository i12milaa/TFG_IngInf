import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Wedge, FancyArrowPatch

fig, ax = plt.subplots(figsize=(10, 8))
ax.set_xlim(-1.5, 9.5)
ax.set_ylim(-1.2, 8.0)
ax.set_aspect('equal')
ax.axis('off')

# --- Posiciones ---
A   = np.array([0.0, 0.0])   # Nodo A, inferior izquierdo
B   = np.array([8.0, 0.0])   # Nodo B, inferior derecho
C   = np.array([4.0, 6.5])   # Nodo C, superior
S   = np.array([4.0, 2.5])   # Servidor central
OBJ = np.array([3.4, 1.8])   # Objeto detectado

# --- Perímetro vigilado ---
triangle = plt.Polygon([A, B, C], closed=True,
                       fill=False, edgecolor='gray',
                       linestyle='--', linewidth=1.5, zorder=1)
ax.add_patch(triangle)

# --- Sectores de barrido ---
# Nodo A: apunta hacia el interior (~15° a 65°)
wedge_A = Wedge(A, 4.8, 15, 65, facecolor='royalblue', alpha=0.18,
                edgecolor='royalblue', linewidth=0.8, zorder=2)
ax.add_patch(wedge_A)

# Nodo B: apunta hacia el interior (~115° a 165°)
wedge_B = Wedge(B, 4.8, 115, 165, facecolor='crimson', alpha=0.18,
                edgecolor='crimson', linewidth=0.8, zorder=2)
ax.add_patch(wedge_B)

# Nodo C: apunta hacia el interior (~242° a 298°)
wedge_C = Wedge(C, 4.8, 242, 298, facecolor='seagreen', alpha=0.18,
                edgecolor='seagreen', linewidth=0.8, zorder=2)
ax.add_patch(wedge_C)

# --- Conexiones WiFi (líneas discontinuas al servidor) ---
for node in [A, B, C]:
    ax.plot([node[0], S[0]], [node[1], S[1]],
            color='gray', linestyle='--', linewidth=1.2, zorder=3, alpha=0.7)

ax.text(6.2, 1.55, 'WiFi', fontsize=8, color='gray', alpha=0.85)

# --- Servidor ---
server_box = mpatches.FancyBboxPatch(S - np.array([0.75, 0.35]),
                                     1.5, 0.7,
                                     boxstyle="round,pad=0.1",
                                     facecolor='#FFF9C4', edgecolor='goldenrod',
                                     linewidth=1.5, zorder=5)
ax.add_patch(server_box)
ax.text(S[0], S[1], 'Servidor', ha='center', va='center',
        fontsize=10, fontweight='bold', zorder=6)

# --- Líneas de distancia (trilateración) ---
ax.annotate('', xy=OBJ, xytext=A,
            arrowprops=dict(arrowstyle='->', color='royalblue', lw=2.0),
            zorder=7)
mid_A = (A + OBJ) / 2
ax.text(mid_A[0] - 0.45, mid_A[1] + 0.15, r'$d_A$',
        fontsize=12, color='royalblue', fontweight='bold', zorder=8)

ax.annotate('', xy=OBJ, xytext=B,
            arrowprops=dict(arrowstyle='->', color='crimson', lw=2.0),
            zorder=7)
mid_B = (B + OBJ) / 2
ax.text(mid_B[0] + 0.15, mid_B[1] + 0.15, r'$d_B$',
        fontsize=12, color='crimson', fontweight='bold', zorder=8)

# --- Nodos ---
node_style = dict(s=160, zorder=9, edgecolors='white', linewidths=1.5)
ax.scatter(*A, color='royalblue', **node_style)
ax.scatter(*B, color='crimson',   **node_style)
ax.scatter(*C, color='seagreen',  **node_style)

ax.text(A[0] - 0.15, A[1] - 0.45, 'Nodo A', ha='center',
        fontsize=10, fontweight='bold', color='royalblue')
ax.text(B[0] + 0.15, B[1] - 0.45, 'Nodo B', ha='center',
        fontsize=10, fontweight='bold', color='crimson')
ax.text(C[0], C[1] + 0.35, 'Nodo C', ha='center',
        fontsize=10, fontweight='bold', color='seagreen')

# --- Objeto detectado ---
ax.scatter(*OBJ, color='black', s=100, zorder=10)
ax.text(OBJ[0] + 0.25, OBJ[1] - 0.35, 'Objeto\ndetectado',
        fontsize=9, ha='left', va='top', color='black')

# --- Título ---
ax.set_title('Esquema conceptual del sistema de vigilancia distribuido\n'
             'con tres nodos cooperativos',
             fontsize=13, fontweight='bold', pad=14)

plt.tight_layout()
plt.savefig('figura_sistema.png', dpi=180, bbox_inches='tight')
plt.show()
