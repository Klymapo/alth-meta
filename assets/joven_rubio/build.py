"""Joven rubio · primer personaje ALTH-META, arquetipo estándar 95 mm, T-pose.

    alth-python assets/joven_rubio/build.py            # iteración
    alth-python assets/joven_rubio/build.py final      # render final + GLB (solo tras aprobación)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy  # noqa: E402
import alth  # noqa: E402
from alth import personaje, ropa, pelo  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"

PIEL = "#FBC39C"
RUBIO = "#EFC989"
CAMISA = "#FBEFE1"
CHALECO = "#302E2D"
CORBATA = "#41598D"
PANTALON = "#4A5770"
ZAPATO = "#292929"
OJO_IRIS = "#4A3220"
BOTON = "#B7BABE"  # metal, para que contraste contra el chaleco negro
OJO_BLANCO = "#FBF8F4"

alth.nueva_escena()

GROSOR_EXTREMIDADES = 1.25  # brazos y piernas más gruesos (vuelta 5)

pl = personaje.plan("estandar", grosor_extremidades=GROSOR_EXTREMIDADES)
piezas = pl["piezas"]
cuerpo = personaje.construir("estandar", color_piel=PIEL, color_zapato=ZAPATO,
                              grosor_extremidades=GROSOR_EXTREMIDADES)
objs = list(cuerpo.values())

CB = alth.SPEC["cuerpo_base_95mm"]
cabeza = piezas["cabeza"]
z_cabeza_top = cabeza["pos"][2] + cabeza["tam"][2]
z_ojo = z_cabeza_top - (95.0 - CB["ojo_centro_xz"][1])
x_ojo = CB["ojo_centro_xz"][0]
ojo_w, ojo_h = CB["ojo_WH"]


def y_cara_en(z_mundo):
    """Y de la piel frontal a esa altura: la cabeza es un tronco de pirámide (mandíbula más
    angosta abajo), así que la cara no está a un Y fijo — interpola igual que la geometría real."""
    t = max(0.0, min(1.0, (z_mundo - cabeza["pos"][2]) / cabeza["h"]))
    d = cabeza["d_abajo"] + (cabeza["d_arriba"] - cabeza["d_abajo"]) * t
    return cabeza["pos"][1] - d / 2


# ---------------------------------------------------------------- cara: placas, no geometría
# Ronda de cierre: ojos más grandes y orgánicos con blanco visible (iris más centrado y angosto
# que el blanco, más un destello) en vez de leerse como una pantalla pequeña; cejas a la medida
# congelada del brief (9.2 x 1.9 x 0.85), antes fuera de tolerancia.
for lado, s in (("izq", -1), ("der", 1)):
    ox = s * x_ojo
    o = alth.caja(f"Joven_ojo_blanco_{lado}", (ojo_w, 1.1, ojo_h), pos=(ox, y_cara_en(z_ojo) - 0.1, z_ojo),
                  color=OJO_BLANCO, biselar=False, apoyada=False)
    objs.append(o)
    o = alth.caja(f"Joven_iris_{lado}", (3.9, 0.75, 6.5), pos=(ox + s * 0.35, y_cara_en(z_ojo) - 0.28, z_ojo - 0.15),
                  color=OJO_IRIS, biselar=False, apoyada=False)
    objs.append(o)
    o = alth.caja(f"Joven_ojo_brillo_{lado}", (1.1, 0.85, 1.1),
                  pos=(ox + s * 0.9, y_cara_en(z_ojo) - 0.34, z_ojo + 1.4),
                  color=OJO_BLANCO, biselar=False, apoyada=False)
    objs.append(o)
    z_ceja = z_ojo + ojo_h / 2 + 2.8
    o = alth.caja(f"Joven_ceja_{lado}", (9.2, 0.85, 1.9), pos=(ox, y_cara_en(z_ceja) - 0.1, z_ceja),
                  color=OJO_IRIS, biselar=False, apoyada=False)
    objs.append(o)

z_boca = z_ojo - 6.6
o = alth.caja("Joven_boca", (6.4, 0.5, 1.0), pos=(0.0, y_cara_en(z_boca) - 0.1, z_boca),
              color=OJO_IRIS, biselar=False, apoyada=False)
objs.append(o)


# ---------------------------------------------------------------- ropa: traje formal (alth/ropa.py)
ropa_objs = ropa.traje_formal(piezas, "Joven", camisa=CAMISA, chaleco=CHALECO, corbata=CORBATA,
                               boton=BOTON, pantalon=PANTALON)
# El brief pide dos botones visibles (traje_formal reparte tres); se quita el de en medio en vez
# de tocar alth/ropa.py, que es compartido con otros personajes.
boton_medio = next(o for o in ropa_objs if o.name == "Joven_boton_1")
ropa_objs.remove(boton_medio)
bpy.data.objects.remove(boton_medio, do_unlink=True)
objs += ropa_objs


# ---------------------------------------------------------------- pelo: corona + cuñas (alth/pelo.py)
# Ronda de cierre: más cuñas, más anchas y más largas que las de la vuelta 6, para que se lean
# como mechones anchos y superpuestos (referencia) en vez de púas delgadas y separadas.
objs.append(pelo.construir_pelo(cabeza, escala=1.45, margen_arriba=4.0, cunias=18,
                                 ancho_base=(11.0, 16.0), largo=(12.0, 19.0), caida=(4.0, 9.0),
                                 copete=4, color=RUBIO, nombre="Joven_pelo"))


alth.estudio()
maniqui = alth.junto_a_maniqui(objs)
rep = alth.revisar(objs, alth.RAIZ / "renders" / "joven_rubio" / MODO, modo=MODO,
                    titulo=f"joven_rubio · {MODO}", asset=alth.RAIZ / "assets" / "joven_rubio" / "spec.json",
                    extras=maniqui)
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "joven_rubio" / "joven_rubio.glb")
