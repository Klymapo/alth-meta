"""Joven rubio · primer personaje ALTH-META, arquetipo estándar 95 mm, T-pose.

    alth-python assets/joven_rubio/build.py            # iteración
    alth-python assets/joven_rubio/build.py final      # render final + GLB (solo tras aprobación)
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402
from alth import personaje  # noqa: E402
from mathutils import Quaternion, Vector  # noqa: E402

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
GROSOR = 0.35        # tela ajustada: chaleco, cintura
GROSOR_ROPA = 0.9    # tela amplia: mangas y pantalón (vuelta 5: "mangas anchas", "pantalón amplio")
torso_perfil = [(r + GROSOR, z) for r, z in piezas["torso"]["perfil"]]
chaleco = alth.torno("Joven_chaleco", torso_perfil, segmentos=12, color=CHALECO, alternar=False,
                      ruido_r=0, ruido_z=0, ovalo=piezas["torso"]["ovalo"], pos=piezas["torso"]["pos"])
objs.append(chaleco)

EMBEBE = 0.15  # cuánto se mete cada placa en la tela, para que la mitad visible quede pegada sin flotar
torso_y, torso_z0 = piezas["torso"]["pos"][1], piezas["torso"]["pos"][2]
ovalo_y = piezas["torso"]["ovalo"][1]


def radio_torso(z_mundo):
    """Radio (antes del óvalo) del chaleco a la altura z_mundo, interpolado entre anillos del perfil."""
    z_rel = z_mundo - torso_z0
    for (r0, z0), (r1, z1) in zip(torso_perfil, torso_perfil[1:]):
        if z0 <= z_rel <= z1:
            return r0 + (r1 - r0) * (z_rel - z0) / (z1 - z0)
    return torso_perfil[0][0] if z_rel < torso_perfil[0][1] else torso_perfil[-1][0]


def y_superficie(z_mundo, embebe=EMBEBE):
    return torso_y - radio_torso(z_mundo) * ovalo_y + embebe


z_pecho_top = torso_z0 + piezas["torso"]["perfil"][2][1]
z_pecho_bajo = torso_z0 + piezas["torso"]["perfil"][0][1] + 2.0
z_v_arriba = z_cuello - 2.2   # justo bajo el cuello de camisa
z_v_abajo = z_pecho_bajo + 1.0  # a la altura del primer botón: ahí "cierra" el chaleco

# cuello de camisa blanco visible en la abertura en V: franjas que se angostan hacia abajo
ANCHO_V = (9.5, 7.0, 4.8, 2.8)
for i, ancho in enumerate(ANCHO_V):
    t = i / (len(ANCHO_V) - 1)
    z_franja = z_v_arriba + (z_v_abajo - z_v_arriba) * t
    alto_franja = (z_v_arriba - z_v_abajo) / (len(ANCHO_V) - 1) + 0.6
    franja = alth.caja(f"Joven_camisa_v_{i}", (ancho, 0.3, alto_franja),
                        pos=(0.0, y_superficie(z_franja), z_franja), color=CAMISA, biselar=False, apoyada=False)
    objs.append(franja)

# solapas: dos paños del chaleco que se abren en la punta de la V
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

for i, z_boton in enumerate((z_v_abajo - 1.0, z_v_abajo - 2.5)):
    boton = alth.caja(f"Joven_boton_{i}", (1.3, 0.4, 1.3), pos=(0.0, y_superficie(z_boton), z_boton),
                       color=BOTON, apoyada=False)
    objs.append(boton)


# ---------------------------------------------------------------- mangas anchas (con doblez al codo)
for lado, s in (("izq", -1), ("der", 1)):
    b = piezas[f"brazo_{lado}"]
    r0, r1, largo = b["r0"] + GROSOR_ROPA, b["r1"] + GROSOR_ROPA, b["largo"]
    perfil = [(r0, 0.0), (r1, largo), (r1 * 1.5, largo + 1.3), (r1 * 1.5, largo + 2.3), (r1 * 0.85, largo + 2.9)]
    manga = alth.torno(f"Joven_manga_{lado}", perfil, segmentos=8, color=CAMISA, alternar=False,
                        ruido_r=0, ruido_z=0, pos=b["pos"])
    manga.rotation_euler = tuple(math.radians(v) for v in b["rot"])
    objs.append(manga)


# ---------------------------------------------------------------- pantalón amplio (con dobladillo al tobillo)
for lado, s in (("izq", -1), ("der", 1)):
    pierna = piezas[f"pierna_{lado}"]
    base_infl = [(r + GROSOR_ROPA, z) for r, z in pierna["perfil"]]
    r0 = base_infl[0][0]
    perfil = [(r0, -1.0), (r0 * 1.3, 1.1), (r0 * 1.3, 2.3), (r0 * 0.95, 2.8)] + base_infl[1:]
    pantalon = alth.torno(f"Joven_pantalon_{lado}", perfil, segmentos=10, color=PANTALON, alternar=False,
                           ruido_r=0, ruido_z=0, ovalo=pierna["ovalo"], pos=pierna["pos"])
    objs.append(pantalon)

# cintura: cubre la pelvis (piel visible entre el chaleco y el pantalón)
cadera = piezas["pelvis"]
cintura = alth.caja("Joven_pantalon_cadera",
                     tuple(v + 2 * GROSOR_ROPA for v in cadera["tam"][:2]) + (cadera["tam"][2],),
                     pos=cadera["pos"], color=PANTALON, apoyada=True)
objs.append(cintura)


# ---------------------------------------------------------------- pelo: mechones facetados (alth.hoja)
# La raíz de cada mechón se ubica justo bajo la superficie de la caja de la cabeza (intersección
# rayo-caja desde el centro, menos un pequeño margen): así la hoja siempre cruza la piel real y
# no queda ni enterrada (sin tocar) ni flotando afuera.
CENTRO_PELO = (0.0, cabeza["pos"][1], z_cabeza_top - cabeza["tam"][2] * 0.22)
MEDIOS_CABEZA = (cabeza["tam"][0] / 2, cabeza["tam"][1] / 2, z_cabeza_top - CENTRO_PELO[2])
MARGEN_PIEL = 1.2


def raiz_en_piel(direccion):
    t = min(MEDIOS_CABEZA[i] / abs(direccion[i]) for i in range(3) if direccion[i])
    return Vector(CENTRO_PELO) + direccion * max(t - MARGEN_PIEL, 0.5)


rng = random.Random(11)
for i in range(34):
    az = rng.uniform(0, 360)
    el = rng.uniform(-15, 85)
    az_r, el_r = math.radians(az), math.radians(el)
    dx = math.sin(az_r) * math.cos(el_r)
    dy = -math.cos(az_r) * math.cos(el_r)
    dz = math.sin(el_r)
    direccion = Vector((dx, dy, dz))
    pos = tuple(raiz_en_piel(direccion))
    quat = direccion.to_track_quat('X', 'Z') @ Quaternion((1.0, 0.0, 0.0), rng.uniform(0, 2 * math.pi))
    rot = tuple(math.degrees(a) for a in quat.to_euler())
    largo = rng.uniform(9.0, 15.0)
    ancho = rng.uniform(5.0, 9.0)
    mechon = alth.hoja(f"Joven_pelo_{i}", largo=largo, ancho=ancho, grosor=0.55, nervio=0.5,
                        curva=rng.uniform(0.5, 1.3), estaciones=2, color=RUBIO, pos=pos, rot=rot)
    objs.append(mechon)


alth.estudio()
maniqui = alth.junto_a_maniqui(objs)
rep = alth.revisar(objs, alth.RAIZ / "renders" / "joven_rubio" / MODO, modo=MODO,
                    titulo=f"joven_rubio · {MODO}", asset=alth.RAIZ / "assets" / "joven_rubio" / "spec.json",
                    extras=maniqui)
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "joven_rubio" / "joven_rubio.glb")
