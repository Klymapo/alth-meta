"""Manzana ALTH · objeto de mano (k=2.0), vuelta 4.

    alth-python assets/manzana/build.py            # iteración
    alth-python assets/manzana/build.py final      # render final + GLB (solo tras aprobación)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"
R, H = 8.94 / 2, 8.05                     # radio y alto del cuerpo (mm), de spec.json
ROJO, MARRON, VERDE = "#A8453B", "#69472D", "#7E9B7A"

# Perfil (radio, altura) relativo a R y H, de abajo hacia arriba.
# Lo más ancho a ~2/3 de la altura; la corona baja redonda hasta un anillo cerrado (0.36 R)
# y de ahí la tapa se hunde a Z_CUENCA: eso forma el hundido del tallo sin escalón.
PERFIL = [(0.34, 0.00), (0.66, 0.06), (0.88, 0.22), (0.99, 0.44),
          (1.00, 0.66), (0.90, 0.83), (0.66, 0.94), (0.36, 0.955)]
Z_BASE, Z_CUENCA = 0.03, 0.74

alth.nueva_escena()
cuerpo = alth.torno(
    "Manzana_cuerpo", [(r * R, z * H) for r, z in PERFIL], segmentos=10, color=ROJO,
    ruido_r=0.08, ruido_z=0.12, centro_abajo=Z_BASE * H, centro_arriba=Z_CUENCA * H, semilla=7)

z_tallo = Z_CUENCA * H - 0.3
tallo = alth.prisma("Manzana_tallo", 0.42, 0.30, 3.0, lados=5, color=MARRON,
                    pos=(0, 0, z_tallo), rot=(6, -14, 20))

# La hoja nace junto al tallo, sube y apunta hacia el frente-derecha para leerse como gota
# en las vistas de frente y 3/4.
hoja = alth.hoja("Manzana_hoja", largo=4.0, ancho=1.9, grosor=0.18, nervio=0.25, curva=0.5,
                 color=VERDE, pos=(0.25, -0.1, z_tallo + 0.9), rot=(15, -30, -40))

objs = [cuerpo, tallo, hoja]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "manzana" / MODO, modo=MODO, titulo=f"manzana v4 · {MODO}")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "manzana" / "manzana.glb")
