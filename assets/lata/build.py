"""Lata de aceitunas ALTH · objeto de mano (k=2.0).

    alth-python assets/lata/build.py            # iteración
    alth-python assets/lata/build.py final      # render final + GLB (solo tras aprobación)
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"
R, H = 8.16 / 2, 11.74                       # radio y alto (mm), de spec.json
RB = R * 1.04                                # los bordes de metal sobresalen un poco
LADOS = 12
METAL, VERDE, CREMA = "#B7BABE", "#7E8B5A", "#EADCC4"   # crema_etiqueta (paleta_notas, ref. objeto-02)
OLIVA, TALLO, HOJA = "#495432", "#69472D", "#5E7759"

alth.nueva_escena()

# ---------------------------------------------------------------- cuerpo
# v2: giro="frente" deja una CARA plana al frente (270°) con sus vecinas a 240° y 300°;
# el dibujo se reparte en esas caras, cada pieza pegada a la suya.
# Rebordes de 0.8 mm (antes 0.55) y tapa hundida: labio interior y fondo 0.4 mm abajo.
BORDE = 0.8
Z_TAPA = H - BORDE
R_LABIO = R * 0.9
Z_HUNDIDO = H - 0.4
cuerpo = alth.torno(
    "Lata_cuerpo",
    [(RB, 0.0), (RB, BORDE), (R, BORDE), (R, 3.0), (R, 8.9), (R, Z_TAPA), (RB, Z_TAPA), (RB, H),
     (R_LABIO, H), (R_LABIO * 0.96, Z_HUNDIDO)],
    segmentos=LADOS, alternar=False, ruido_r=0, ruido_z=0, giro="frente",
    centro_abajo=0.15, centro_arriba=Z_HUNDIDO,          # fondo cóncavo y tapa hundida
    bandas=[(BORDE, METAL, "metal"), (3.0, VERDE), (8.9, CREMA), (Z_TAPA - 0.01, VERDE), (99, METAL, "metal")])

# ---------------------------------------------------------------- lengüeta
# v2: argolla doble en forma de 8 (≈ 4.3 mm, media tapa) sobre el fondo hundido; remache de 4 lados.
# v3: argollas separadas hasta apenas tocarse (antes se enciman y se leía una sola); la chica de 4 lados.
lengueta = [
    alth.anillo("Lata_lengueta", 1.25, 0.4, segmentos=8, color=METAL, metal=True,
                escala=(0.8, 1.0, 1.0), pos=(0, 1.1, Z_HUNDIDO + 0.2)),
    alth.anillo("Lata_lengueta_b", 0.72, 0.36, segmentos=4, color=METAL, metal=True,
                pos=(0, -1.27, Z_HUNDIDO + 0.18)),
    alth.anillo("Lata_remache", 0.45, 0.3, segmentos=4, color=METAL, metal=True,
                pos=(0, -1.27, Z_HUNDIDO + 0.15)),
]

# ---------------------------------------------------------------- dibujo (calcomanías)
# v5: todo el dibujo son calcomanías que envuelven el cuerpo (alth.calcomania): se cortan en cada
# arista y se pegan planas a su cara, 0.02 mm hacia afuera. En la v4 eran piezas sueltas por cara
# que asomaban de canto en la lateral o, a ras, casi desaparecían.
# u = 0 es el centro de la cara frontal (giro="frente"); +u va hacia la derecha.
dibujo = [
    alth.calcomania("Lata_aceituna_A", alth.contorno_ovalo(-0.6, 5.0, 1.15, 1.45, 9), R, LADOS, color=OLIVA),
    alth.calcomania("Lata_aceituna_B", alth.contorno_ovalo(1.9, 5.9, 1.05, 1.4, 9), R, LADOS, color=OLIVA),
    alth.calcomania("Lata_rama", alth.contorno_tira([(-0.4, 6.3), (0.4, 7.3), (1.4, 8.0), (2.6, 8.3)], 0.28),
                    R, LADOS, color=TALLO),
    alth.calcomania("Lata_ramita", alth.contorno_tira([(1.9, 7.2), (1.6, 7.85)], 0.22), R, LADOS, color=TALLO),
    alth.calcomania("Lata_hoja", alth.contorno_gota((0.5, 7.5), 155, 2.8, 1.4), R, LADOS, color=HOJA),
]

objs = [cuerpo, *lengueta, *dibujo]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "lata" / MODO, modo=MODO, titulo=f"lata v5 · {MODO}",
                   asset=alth.RAIZ / "assets" / "lata" / "spec.json")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "lata" / "lata.glb")
