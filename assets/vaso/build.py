"""Vaso de plástico ALTH · objeto de mano (k=2.0).

    alth-python assets/vaso/build.py            # iteración
    alth-python assets/vaso/build.py final      # render final + GLB (solo tras aprobación)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"
RB, RT, H = 6.71 / 2, 8.94 / 2, 13.42        # radio de base, radio de boca y alto (mm), de spec.json
LADOS = 12
AZUL, INTERIOR = "#4F6D9A", "#3B5475"
PARED = 0.35                                 # grosor de la pared
BORDE = 0.5                                  # alto del borde enrollado
Z_FONDO = 0.8                                # fondo interior

alth.nueva_escena()


def radio(z):
    """Radio de la pared exterior (cono truncado)."""
    return RB + (RT - RB) * z / H


# ---------------------------------------------------------------- cuerpo
# Pie biselado, anillo de refuerzo a 1.6–2.0 mm, pared cónica y borde enrollado que sobresale
# 0.18 mm; por dentro baja hasta el fondo. giro=0 deja vértices en ±X: W = 2 × RT.
Z_ANILLO = 1.6
perfil = [
    (RB * 0.92, 0.0), (radio(0.3), 0.3),
    (radio(Z_ANILLO), Z_ANILLO), (radio(Z_ANILLO) + 0.12, Z_ANILLO + 0.12),
    (radio(Z_ANILLO + 0.4) + 0.12, Z_ANILLO + 0.4), (radio(Z_ANILLO + 0.55), Z_ANILLO + 0.55),
    (radio(H - BORDE) - 0.05, H - BORDE), (RT, H - BORDE * 0.6), (RT - 0.08, H),
    (RT - PARED - 0.1, H), (radio(H - BORDE) - PARED - 0.05, H - BORDE),
    (radio(Z_FONDO) - PARED, Z_FONDO),
]
cuerpo = alth.torno(
    "Vaso_cuerpo", perfil, segmentos=LADOS, alternar=False, ruido_r=0, ruido_z=0, giro=0,
    centro_abajo=0.12, centro_arriba=Z_FONDO - 0.05,
    bandas=[(H - 0.01, AZUL), (99, INTERIOR)])

objs = [cuerpo]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "vaso" / MODO, modo=MODO, titulo=f"vaso v1 · {MODO}",
                   asset=alth.RAIZ / "assets" / "vaso" / "spec.json")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "vaso" / "vaso.glb")
