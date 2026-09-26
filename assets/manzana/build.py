"""Manzana ALTH · objeto de mano (k=2.0), vuelta 6.

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
# v5: termina en 1.0 de alto (la v4 medía 7.69 mm, −4.5 %); radio máximo 0.965 porque el
# ruido de ±8 % lo infla (la v4 medía +3.7 % de ancho); base más angosta y redondeada.
PERFIL = [(0.22, 0.00), (0.52, 0.05), (0.80, 0.18), (0.95, 0.40),
          (0.965, 0.62), (0.88, 0.82), (0.64, 0.95), (0.36, 1.00)]
Z_BASE, Z_CUENCA = 0.04, 0.78

alth.nueva_escena()
cuerpo = alth.torno(
    "Manzana_cuerpo", [(r * R, z * H) for r, z in PERFIL], segmentos=10, color=ROJO,
    ruido_r=0.08, ruido_z=0.12, centro_abajo=Z_BASE * H, centro_arriba=Z_CUENCA * H, semilla=7)

z_tallo = Z_CUENCA * H - 0.3
tallo = alth.prisma("Manzana_tallo", 0.42, 0.30, 3.0, lados=5, color=MARRON,
                    pos=(0, 0, z_tallo), rot=(6, -14, 20))

# La hoja nace junto al tallo, sube y apunta hacia el frente-derecha para leerse como gota
# en las vistas de frente y 3/4.
# v5: más grande y girada sobre su eje (rot x) para mostrar la cara de frente y en 3/4;
# en la v4 su plano era casi horizontal y de frente se veía como una rayita.
# v6: 3.7 × 1.9 (≈ 2/5 del ancho, como la referencia); nace 2.2 mm arriba sobre el eje
# inclinado del tallo; rot z 30 deja la cara hacia frente (0.89) y hacia 3/4 (0.84),
# en la v5 (rot z −35) quedaba de canto en 3/4.
Z_HOJA = 2.2
eje_tallo = (-0.190, -0.181, 0.965)       # eje del prisma con rot=(6, -14, 20)
k_hoja = Z_HOJA / eje_tallo[2]
hoja = alth.hoja("Manzana_hoja", largo=3.7, ancho=1.9, grosor=0.2, nervio=0.3, curva=0.45,
                 color=VERDE, pos=(eje_tallo[0] * k_hoja, eje_tallo[1] * k_hoja, z_tallo + Z_HOJA),
                 rot=(55, -40, 30))

objs = [cuerpo, tallo, hoja]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "manzana" / MODO, modo=MODO, titulo=f"manzana v6 · {MODO}")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "manzana" / "manzana.glb")
