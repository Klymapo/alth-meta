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
lengueta = [
    alth.anillo("Lata_lengueta", 1.25, 0.4, segmentos=8, color=METAL, metal=True,
                escala=(0.8, 1.0, 1.0), pos=(0, 0.85, Z_HUNDIDO + 0.2)),
    alth.anillo("Lata_lengueta_b", 0.7, 0.36, segmentos=5, color=METAL, metal=True,
                pos=(0, -1.1, Z_HUNDIDO + 0.18)),
    alth.anillo("Lata_remache", 0.45, 0.3, segmentos=4, color=METAL, metal=True,
                pos=(0, -1.1, Z_HUNDIDO + 0.15)),
]

# ---------------------------------------------------------------- dibujo sobre las caras
APOTEMA = R * math.cos(math.radians(180 / LADOS))
MEDIA_CARA = R * math.sin(math.radians(180 / LADOS))   # 1.056 mm: de centro de cara a arista


def cara(c_grados, u=0.0, fuera=0.0):
    """Punto de la cara centrada en c_grados, desplazado u mm a lo ancho y `fuera` mm hacia afuera.
    Devuelve (x, y) y el giro en Z que alinea una pieza con esa cara. +u va hacia ángulos mayores."""
    c = math.radians(c_grados)
    n = (math.cos(c), math.sin(c))
    t = (-math.sin(c), math.cos(c))
    x = n[0] * (APOTEMA + fuera) + t[0] * u
    y = n[1] * (APOTEMA + fuera) + t[1] * u
    return x, y, c_grados - 270


def rama(nombre, c, u0, z0, u1, z1, grueso=0.13):
    """Tallo recto sobre la cara c, de (u0, z0) a (u1, z1)."""
    x, y, rz = cara(c, u0, fuera=0.08)
    du, dz = u1 - u0, z1 - z0
    return alth.prisma(nombre, grueso, grueso * 0.8, math.hypot(du, dz), lados=4, color=TALLO,
                       pos=(x, y, z0), rot=(0, math.degrees(math.atan2(du, dz)), rz))


FRENTE, DER = 270, 300
dibujo = []

# v2: aceitunas ovaladas de 9 lados (≈ 2.4 × 2.9 mm, antes discos de 1.9 mm), una por cara.
# Se hunden 0.08 mm para que el borde que pasa de la arista no quede flotando.
for nombre, c, u, z, r in (("A", FRENTE, -0.1, 4.6, 1.45), ("B", DER, 0.0, 5.9, 1.35)):
    x, y, rz = cara(c, u, fuera=-0.08)
    disco = alth.torno(f"Lata_aceituna_{nombre}", [(r, 0.0), (r, 0.22)], segmentos=9, ovalo=(0.82, 1.0),
                       alternar=False, ruido_r=0, ruido_z=0, color=OLIVA)
    disco.location = (x, y, z)
    disco.rotation_euler = (math.radians(90), 0, math.radians(rz))  # el disco mira hacia afuera
    dibujo.append(disco)

# v2: una rama que baja desde arriba a la derecha, cruza la arista y termina en la aceituna A;
# una ramita corta a la aceituna B (antes dos tallos que se juntaban: parecían cerezas).
dibujo += [
    rama("Lata_rama_a", DER, 0.6, 8.6, -MEDIA_CARA, 7.3),
    rama("Lata_rama_b", FRENTE, MEDIA_CARA, 7.3, -0.1, 6.0),
    rama("Lata_ramita", DER, -0.5, 7.75, 0.0, 7.2, grueso=0.11),
]

# Hoja: nace en la rama del frente y sube hacia la izquierda (como en la referencia).
x, y, rz = cara(FRENTE, u=0.9, fuera=0.06)
dibujo.append(alth.hoja("Lata_hoja", largo=2.4, ancho=1.1, grosor=0.08, nervio=0.08, curva=0.0,
                        estaciones=3, color=HOJA, pos=(x, y, 7.1), rot=(90, -150, rz)))

objs = [cuerpo, *lengueta, *dibujo]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "lata" / MODO, modo=MODO, titulo=f"lata v2 · {MODO}")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "lata" / "lata.glb")
