"""Taza de café ALTH · objeto de mano (k=2.0).

    alth-python assets/taza/build.py            # iteración
    alth-python assets/taza/build.py final      # render final + GLB (solo tras aprobación)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"
R, H = 8.94 / 2, 10.62                       # radio de boca y alto (mm), de spec.json
LADOS = 12
CREMA, FRANJA, CAFE = "#F1E6D7", "#CD8959", "#4A3220"
PARED = 0.4                                  # grosor del borde
Z_CAFE = H - 1.0                             # nivel del café
F0, F1 = 6.8, 8.2                            # franja

alth.nueva_escena()

# ---------------------------------------------------------------- cuerpo
# Pared apenas cónica (0.92 R abajo → R arriba), pie biselado y hueco interior que baja hasta
# un poco debajo del café. giro=0 deja vértices en ±X: W de vértice a vértice = 2R.
def radio(z):
    return R * (0.92 + 0.08 * z / H)

cuerpo = alth.torno(
    "Taza_cuerpo",
    [(radio(0) * 0.9, 0.0), (radio(0.4), 0.4), (radio(F0), F0), (radio(F1), F1), (R, H),
     (R - PARED, H), (radio(Z_CAFE - 0.3) - PARED - 0.05, Z_CAFE - 0.3)],
    segmentos=LADOS, alternar=False, ruido_r=0, ruido_z=0, giro=0,
    centro_abajo=0.15, centro_arriba=Z_CAFE - 0.3,
    bandas=[(F0 - 0.01, CREMA), (F1 + 0.01, FRANJA), (99, CREMA)])

# ---------------------------------------------------------------- café
r_cafe = radio(Z_CAFE) - PARED
cafe = alth.torno("Taza_cafe", [(r_cafe, Z_CAFE - 0.15), (r_cafe, Z_CAFE)], segmentos=LADOS,
                  alternar=False, ruido_r=0, ruido_z=0, giro=0, color=CAFE)

# ---------------------------------------------------------------- asa
# Anillo en el plano XZ (rot X 90°), sección cuadrada, estirado en Z; la mitad interior se hunde en la pared.
# v2: tubo más grueso (0.85 → 1.1 mm) y ojo más chico, para que se lea soft y no como alambre.
asa = alth.anillo("Taza_asa", 1.95, 1.1, segmentos=10, lados=4, color=CREMA,
                  escala=(0.85, 1.2, 1.0), pos=(R + 0.75, 0, H * 0.53), rot=(90, 0, 0))

objs = [cuerpo, cafe, asa]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "taza" / MODO, modo=MODO, titulo=f"taza v2 · {MODO}",
                   asset=alth.RAIZ / "assets" / "taza" / "spec.json")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "taza" / "taza.glb")
