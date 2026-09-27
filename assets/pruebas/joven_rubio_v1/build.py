"""Joven rubio · PRUEBA v1 (no es el modelo final): el cuerpo de assets/joven_rubio (vuelta 6)
con el pelo nuevo de alth.pelo (corona + cuñas) en vez de los mechones de alth.hoja().

Vive aparte en assets/pruebas/ a propósito: es un paso para decidir si el pelo nuevo se lleva a
assets/joven_rubio/build.py, no el asset aprobado. Ver spec.json de esta carpeta para el reporte
completo (cuerpo y pelo).

    alth-python assets/pruebas/joven_rubio_v1/build.py            # iteración
    alth-python assets/pruebas/joven_rubio_v1/build.py final      # render final (sin GLB: es prueba)
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import alth  # noqa: E402
from alth import pelo, personaje  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"
AQUI = Path(__file__).resolve().parent

PIEL = "#FBC39C"
CAMISA = "#FBEFE1"
CHALECO = "#302E2D"
CORBATA = "#41598D"
PANTALON = "#4A5770"
ZAPATO = "#292929"
OJO_IRIS = "#4A3220"
BOTON = "#B7BABE"
OJO_BLANCO = "#FBF8F4"
RUBIO_ARENA = alth.SPEC["paleta"]["medidos"]["rubio_arena"]

alth.nueva_escena()

GROSOR_EXTREMIDADES = 1.25

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
    t = max(0.0, min(1.0, (z_mundo - cabeza["pos"][2]) / cabeza["h"]))
    d = cabeza["d_abajo"] + (cabeza["d_arriba"] - cabeza["d_abajo"]) * t
    return cabeza["pos"][1] - d / 2


# ---------------------------------------------------------------- cara: placas, no geometría
for lado, s in (("izq", -1), ("der", 1)):
    ox = s * x_ojo
    o = alth.caja(f"Joven_ojo_blanco_{lado}", (ojo_w, 0.35, ojo_h), pos=(ox, y_cara_en(z_ojo) - 0.1, z_ojo),
                  color=OJO_BLANCO, biselar=False, apoyada=False)
    objs.append(o)
    o = alth.caja(f"Joven_iris_{lado}", (3.9, 0.35, 6.3), pos=(ox + s * 0.6, y_cara_en(z_ojo) - 0.25, z_ojo - 0.3),
                  color=OJO_IRIS, biselar=False, apoyada=False)
    objs.append(o)
    z_ceja = z_ojo + ojo_h / 2 + 2.8
    o = alth.caja(f"Joven_ceja_{lado}", (8.4, 0.5, 1.6), pos=(ox, y_cara_en(z_ceja) - 0.1, z_ceja),
                  color=OJO_IRIS, biselar=False, apoyada=False)
    objs.append(o)

z_boca = z_ojo - 6.6
o = alth.caja("Joven_boca", (6.0, 0.5, 0.9), pos=(0.0, y_cara_en(z_boca) - 0.1, z_boca),
              color=OJO_IRIS, biselar=False, apoyada=False)
objs.append(o)


# ---------------------------------------------------------------- collar (asoma bajo la barbilla)
z_cuello = piezas["torso"]["pos"][2] + piezas["torso"]["perfil"][-1][1]
collar = alth.torno("Joven_collar", [(13.6, 0.0), (14.2, 0.5), (12.6, 1.6)], segmentos=10, color=CAMISA,
                     alternar=False, ruido_r=0, ruido_z=0, pos=(0.0, 0.0, z_cuello - 1.5))
objs.append(collar)


# ---------------------------------------------------------------- torso: chaleco (una sola malla)
GROSOR = 0.35
GROSOR_ROPA = 0.9
torso_perfil = [(r + GROSOR, z) for r, z in piezas["torso"]["perfil"]]
chaleco = alth.torno("Joven_chaleco", torso_perfil, segmentos=12, color=CHALECO, alternar=False,
                      ruido_r=0, ruido_z=0, ovalo=piezas["torso"]["ovalo"], pos=piezas["torso"]["pos"])
objs.append(chaleco)

EMBEBE = 0.15
torso_y, torso_z0 = piezas["torso"]["pos"][1], piezas["torso"]["pos"][2]
ovalo_y = piezas["torso"]["ovalo"][1]


def radio_torso(z_mundo):
    z_rel = z_mundo - torso_z0
    for (r0, z0), (r1, z1) in zip(torso_perfil, torso_perfil[1:]):
        if z0 <= z_rel <= z1:
            return r0 + (r1 - r0) * (z_rel - z0) / (z1 - z0)
    return torso_perfil[0][0] if z_rel < torso_perfil[0][1] else torso_perfil[-1][0]


def y_superficie(z_mundo, embebe=EMBEBE):
    return torso_y - radio_torso(z_mundo) * ovalo_y + embebe


z_v_arriba = z_cuello - 2.2
z_v_abajo = torso_z0 + 0.8

ANCHO_V = (9.5, 8.2, 6.8, 5.2, 3.6, 2.4)
for i, ancho in enumerate(ANCHO_V):
    t = i / (len(ANCHO_V) - 1)
    z_franja = z_v_arriba + (z_v_abajo - z_v_arriba) * t
    alto_franja = (z_v_arriba - z_v_abajo) / (len(ANCHO_V) - 1) + 0.6
    franja = alth.caja(f"Joven_camisa_v_{i}", (ancho, 0.3, alto_franja),
                        pos=(0.0, y_superficie(z_franja), z_franja), color=CAMISA, biselar=False, apoyada=False)
    objs.append(franja)

for lado, s in (("izq", -1), ("der", 1)):
    solapa = alth.caja(f"Joven_solapa_{lado}", (4.2, 0.35, 6.5),
                        pos=(s * 4.6, y_superficie(z_v_arriba + 1.0) - 0.1, z_v_arriba + 1.0),
                        color=CHALECO, biselar=False, apoyada=False)
    solapa.rotation_euler = (0.0, 0.0, math.radians(-s * 22))
    objs.append(solapa)

z_corbata = (z_v_arriba + z_v_abajo) / 2
corbata = alth.caja("Joven_corbata", (2.6, 0.35, z_v_arriba - z_v_abajo + 1.5),
                     pos=(0.0, y_superficie(z_corbata, EMBEBE + 0.12), z_corbata),
                     color=CORBATA, biselar=False, apoyada=False)
objs.append(corbata)

for i, t in enumerate((0.45, 0.65, 0.85)):
    z_boton = z_v_arriba + (z_v_abajo - z_v_arriba) * t
    boton = alth.caja(f"Joven_boton_{i}", (1.3, 0.4, 1.3), pos=(0.0, y_superficie(z_boton), z_boton),
                       color=BOTON, apoyada=False)
    objs.append(boton)


# ---------------------------------------------------------------- mangas anchas (puño: anillo)
for lado, s in (("izq", -1), ("der", 1)):
    b = piezas[f"brazo_{lado}"]
    r0, r1, largo = b["r0"] + GROSOR_ROPA, b["r1"] + GROSOR_ROPA, b["largo"]
    manga = alth.torno(f"Joven_manga_{lado}", [(r0, 0.0), (r1, largo)], segmentos=8, color=CAMISA,
                        alternar=False, ruido_r=0, ruido_z=0, pos=b["pos"])
    manga.rotation_euler = tuple(math.radians(v) for v in b["rot"])
    objs.append(manga)

    x_puno = b["pos"][0] + s * (largo + 0.3)
    puno = alth.anillo(f"Joven_puno_{lado}", radio=r1 * 0.95, grosor=2.0, segmentos=10, lados=4,
                        color=CAMISA, pos=(x_puno, b["pos"][1], b["pos"][2]), rot=(0.0, 90.0, 0.0))
    objs.append(puno)


# ---------------------------------------------------------------- pantalón amplio (dobladillo: anillo)
for lado, s in (("izq", -1), ("der", 1)):
    pierna = piezas[f"pierna_{lado}"]
    base_infl = [(r + GROSOR_ROPA, z) for r, z in pierna["perfil"]]
    r0 = base_infl[0][0]
    perfil = [(r0 * 0.97, -1.5)] + base_infl
    pantalon = alth.torno(f"Joven_pantalon_{lado}", perfil, segmentos=10, color=PANTALON, alternar=False,
                           ruido_r=0, ruido_z=0, ovalo=pierna["ovalo"], pos=pierna["pos"])
    objs.append(pantalon)

    z_dobladillo = pierna["pos"][2] + 1.6
    dobladillo = alth.anillo(f"Joven_dobladillo_{lado}", radio=r0 * 1.05, grosor=2.4, segmentos=10, lados=4,
                              color=PANTALON, escala=(1.0, pierna["ovalo"][1], 1.0),
                              pos=(pierna["pos"][0], pierna["pos"][1], z_dobladillo))
    objs.append(dobladillo)

cadera = piezas["pelvis"]
cintura = alth.caja("Joven_pantalon_cadera",
                     tuple(v + 2 * GROSOR_ROPA for v in cadera["tam"][:2]) + (cadera["tam"][2],),
                     pos=cadera["pos"], color=PANTALON, apoyada=True)
objs.append(cintura)


# ---------------------------------------------------------------- pelo: alth.pelo (corona + cuñas)
# Reemplaza los mechones de alth.hoja() de assets/joven_rubio por el prototipo de alth/pelo.py
# (ver tools/prueba_pelo.py): una sola malla, corona + cuñas de borde + cuñas de copete arriba.
pelo_obj = pelo.construir_pelo(cabeza, escala=1.3, cunias=10, copete=3, color=RUBIO_ARENA,
                                nombre="Joven_pelo_v1")
objs.append(pelo_obj)


alth.estudio()
maniqui = alth.junto_a_maniqui(objs)
carpeta_render = alth.RAIZ / "renders" / "pruebas" / "joven_rubio_v1" / MODO
rep = alth.revisar(objs, carpeta_render, modo=MODO,
                    titulo=f"joven_rubio · PRUEBA v1 (pelo nuevo) · {MODO}",
                    asset=AQUI / "spec.json", extras=maniqui)
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["segundos_total"])
if MODO == "final":
    import shutil
    shutil.copy(carpeta_render / "hoja.png", AQUI / "hoja_v1.png")
