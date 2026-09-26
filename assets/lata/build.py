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
METAL, VERDE, CREMA = "#B7BABE", "#7E8B5A", "#F1E6D7"
OLIVA, TALLO, HOJA = "#495432", "#69472D", "#5E7759"

alth.nueva_escena()

# ---------------------------------------------------------------- cuerpo
# Con giro=0 queda una ARISTA al frente (270°) y dos caras de 2.1 mm a sus lados (255° y 285°).
# El dibujo se reparte en esas dos caras para que nada quede flotando en una esquina.
Z_TAPA = H - 0.55
cuerpo = alth.torno(
    "Lata_cuerpo",
    [(RB, 0.0), (RB, 0.55), (R, 0.55), (R, 3.0), (R, 8.9), (R, Z_TAPA), (RB, Z_TAPA), (RB, H)],
    segmentos=LADOS, alternar=False, ruido_r=0, ruido_z=0, giro=0,
    centro_abajo=0.15, centro_arriba=H - 0.3,          # fondo cóncavo y tapa hundida
    bandas=[(0.55, METAL, "metal"), (3.0, VERDE), (8.9, CREMA), (Z_TAPA - 0.01, VERDE), (99, METAL, "metal")])

# ---------------------------------------------------------------- lengüeta
lengueta = [
    alth.anillo("Lata_lengueta", 1.0, 0.3, segmentos=6, color=METAL, metal=True, pos=(0.3, 0.7, H - 0.12)),
    alth.anillo("Lata_remache", 0.5, 0.26, segmentos=6, color=METAL, metal=True, pos=(-0.15, -0.75, H - 0.14)),
]

# ---------------------------------------------------------------- dibujo sobre las caras
APOTEMA = R * math.cos(math.radians(180 / LADOS))


def cara(c_grados, u=0.0, fuera=0.0):
    """Punto de la cara centrada en c_grados, desplazado u mm a lo ancho y `fuera` mm hacia afuera.
    Devuelve (x, y) y el giro en Z que alinea una pieza con esa cara."""
    c = math.radians(c_grados)
    n = (math.cos(c), math.sin(c))
    t = (-math.sin(c), math.cos(c))
    x = n[0] * (APOTEMA + fuera) + t[0] * u
    y = n[1] * (APOTEMA + fuera) + t[1] * u
    return x, y, c_grados - 270


IZQ, DER = 255, 285   # caras a la izquierda y derecha de la arista frontal
dibujo = []

for nombre, c, z, r in (("A", IZQ, 4.9, 0.95), ("B", DER, 5.9, 0.9)):
    x, y, rz = cara(c, fuera=-0.02)
    disco = alth.torno(f"Lata_aceituna_{nombre}", [(r, 0.0), (r, 0.14)], segmentos=7,
                       alternar=False, ruido_r=0, ruido_z=0, color=OLIVA)
    disco.location = (x, y, z)
    disco.rotation_euler = (math.radians(90), 0, math.radians(rz))  # el disco mira hacia afuera
    dibujo.append(disco)

# Tallos: de cada aceituna hasta la arista frontal, donde se juntan (z = 8.2).
# En la cara izquierda "hacia la arista" es +u; en la derecha es −u.
for nombre, c, z0, du, dz in (("A", IZQ, 5.7, 1.056, 8.2 - 5.7), ("B", DER, 6.65, -1.056, 8.2 - 6.65)):
    x, y, rz = cara(c, fuera=0.1)
    largo = math.hypot(du, dz)
    inclinacion = math.degrees(math.atan2(du, dz))
    dibujo.append(alth.prisma(f"Lata_tallo_{nombre}", 0.11, 0.09, largo, lados=4, color=TALLO,
                              pos=(x, y, z0), rot=(0, inclinacion, rz)))

# Hoja: nace en la unión de los tallos y sube hacia la izquierda sobre la cara izquierda.
x, y, rz = cara(IZQ, u=1.056, fuera=0.06)
dibujo.append(alth.hoja("Lata_hoja", largo=2.4, ancho=1.0, grosor=0.08, nervio=0.08, curva=0.0,
                        estaciones=3, color=HOJA, pos=(x, y, 8.2), rot=(90, -150, rz)))

objs = [cuerpo, *lengueta, *dibujo]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "lata" / MODO, modo=MODO, titulo=f"lata v1 · {MODO}")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "lata" / "lata.glb")
