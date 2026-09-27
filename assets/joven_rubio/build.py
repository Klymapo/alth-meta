"""Joven rubio · primer personaje ALTH-META, arquetipo estándar 95 mm, T-pose.

    alth-python assets/joven_rubio/build.py            # iteración
    alth-python assets/joven_rubio/build.py final      # render final + GLB (solo tras aprobación)
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402
from alth import personaje, ropa  # noqa: E402

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
o = alth.caja("Joven_boca", (6.0, 0.5, 0.9), pos=(0.4, y_cara_en(z_boca) - 0.1, z_boca),
              color=OJO_IRIS, biselar=False, apoyada=False)
o.rotation_euler = (0.0, 0.0, math.radians(-4.0))  # sonrisa ladeada como en la referencia
objs.append(o)


# ---------------------------------------------------------------- ropa: traje formal (alth/ropa.py)
objs += ropa.traje_formal(piezas, "Joven", camisa=CAMISA, chaleco=CHALECO, corbata=CORBATA,
                           boton=BOTON, pantalon=PANTALON)

# Nudo de la corbata: triángulo/trapecio prominente bajo el cuello de la camisa
z_cuello = piezas["torso"]["pos"][2] + piezas["torso"]["perfil"][-1][1]
z_nudo = z_cuello - 2.5
y_nudo = ropa.superficie_torso(piezas["torso"], z_nudo, embebe=0.25)
nudo = alth.caja("Joven_corbata_nudo", (3.4, 0.55, 2.6), pos=(0.0, y_nudo - 0.25, z_nudo),
                 color=CORBATA, biselar=True, apoyada=False)
objs.append(nudo)

# Puntas inferiores del chaleco (corte clásico con picos frontales)
z_base_chaleco = piezas["torso"]["pos"][2] + 0.8
for lado, s in (("izq", -1), ("der", 1)):
    y_pico = ropa.superficie_torso(piezas["torso"], z_base_chaleco, embebe=0.1)
    pico = alth.caja(f"Joven_chaleco_pico_{lado}", (4.5, 0.4, 3.2),
                     pos=(s * 4.2, y_pico, z_base_chaleco - 1.2),
                     color=CHALECO, biselar=False, apoyada=False)
    pico.rotation_euler = (0.0, 0.0, math.radians(-s * 25))
    objs.append(pico)

# Trabilla trasera del chaleco (cinturón de ajuste posterior visible en vista espalda)
z_trabilla = piezas["torso"]["pos"][2] + 3.0
y_espalda = piezas["torso"]["pos"][1] + 8.9 + 0.35
trabilla = alth.caja("Joven_chaleco_trabilla", (12.0, 0.4, 2.2),
                      pos=(0.0, y_espalda, z_trabilla),
                      color=CHALECO, biselar=False, apoyada=False)
objs.append(trabilla)
hebilla = alth.caja("Joven_chaleco_hebilla", (2.4, 0.5, 2.6),
                     pos=(0.0, y_espalda + 0.1, z_trabilla),
                     color=BOTON, biselar=False, apoyada=False)
objs.append(hebilla)


# ---------------------------------------------------------------- pelo: casquete + mechones facetados
def _agregar_mechon(bm, puntos, anchos, grosores, normales_arriba=None):
    """Genera un mechón facetado (prisma de 4 caras por sección) a lo largo de una curva de puntos.
    Si la última estación tiene ancho <= 0.2, remata en punta facetada cerrada."""
    import mathutils

    n = len(puntos)
    termina_en_punta = (anchos[-1] <= 0.2 or grosores[-1] <= 0.2)
    n_estaciones = n - 1 if termina_en_punta else n

    anillos = []
    for i in range(n_estaciones):
        pt = mathutils.Vector(puntos[i])
        if i < n - 1:
            tang = (mathutils.Vector(puntos[i + 1]) - pt).normalized()
        else:
            tang = (pt - mathutils.Vector(puntos[i - 1])).normalized()

        if normales_arriba and i < len(normales_arriba):
            up_ref = mathutils.Vector(normales_arriba[i]).normalized()
        else:
            up_ref = mathutils.Vector((0.0, 0.0, 1.0))
            if abs(tang.dot(up_ref)) > 0.95:
                up_ref = mathutils.Vector((0.0, 1.0, 0.0))

        lado = tang.cross(up_ref).normalized()
        arriba = lado.cross(tang).normalized()

        w = anchos[i] / 2.0
        g = grosores[i] / 2.0

        v0 = bm.verts.new(pt + lado * w)
        v1 = bm.verts.new(pt + arriba * g)
        v2 = bm.verts.new(pt - lado * w)
        v3 = bm.verts.new(pt - arriba * g)
        anillos.append([v0, v1, v2, v3])

    bm.faces.new(tuple(reversed(anillos[0])))
    for i in range(len(anillos) - 1):
        a, b = anillos[i], anillos[i + 1]
        for j in range(4):
            k = (j + 1) % 4
            bm.faces.new((a[j], b[j], b[k], a[k]))

    if termina_en_punta:
        v_punta = bm.verts.new(mathutils.Vector(puntos[-1]))
        ultimo = anillos[-1]
        for j in range(4):
            k = (j + 1) % 4
            bm.faces.new((ultimo[j], v_punta, ultimo[k]))
    else:
        bm.faces.new(tuple(anillos[-1]))


def construir_cabello_theo(cabeza_pieza, color=RUBIO, nombre="Joven_pelo"):
    """Pelo completo de Theo en una sola malla: casquete envolvente que da el volumen del cráneo
    y mechones gruesos facetados característicos de la referencia."""
    import bmesh

    bm = bmesh.new()

    # 1. Casquete elipsoidal facetado: corona envolvente
    seg = 12
    cx, cy = cabeza_pieza["pos"][0], cabeza_pieza["pos"][1] + 1.2
    anillos_spec = [
        # (z, rx, ry, cy_offset)
        (100.5, 11.0, 10.0, 0.0),   # polo superior elevado
        (97.5, 20.5, 18.0, 0.5),   # bóveda alta
        (91.5, 22.8, 19.5, 1.2),   # sienes / lateral alto
        (85.5, 22.8, 20.0, 1.6),   # encima de orejas
    ]
    anillos_verts = []
    for z_base, rx, ry, dy in anillos_spec:
        anillo = []
        for s in range(seg):
            az = 2.0 * math.pi * s / seg
            x = cx + rx * math.cos(az)
            y = cy + dy + ry * math.sin(az)
            anillo.append(bm.verts.new((x, y, z_base)))
        anillos_verts.append(anillo)

    # Anillo inferior con corte que despeja la cara y cubre la nuca
    anillo_inferior = []
    for s in range(seg):
        az = 2.0 * math.pi * s / seg
        sin_az = math.sin(az)  # -1 = frente (-Y), +1 = espalda (+Y)
        if sin_az <= 0:
            # frente: sube sobre la frente para dejar ojos y cejas despejados
            z = 85.5 + (89.5 - 85.5) * (-sin_az)
            rx, ry = 22.0, 17.5
        else:
            # espalda: baja cubriendo la nuca
            z = 85.5 + (68.0 - 85.5) * sin_az
            rx, ry = 22.2, 19.8
        x = cx + rx * math.cos(az)
        y = cy + 1.6 + ry * math.sin(az)
        anillo_inferior.append(bm.verts.new((x, y, z)))
    anillos_verts.append(anillo_inferior)

    # Tapa polo superior
    bm.faces.new(tuple(reversed(anillos_verts[0])))
    # Franjas entre anillos
    for a, b in zip(anillos_verts[:-1], anillos_verts[1:]):
        for s in range(seg):
            k = (s + 1) % seg
            bm.faces.new((a[s], a[k], b[k], b[s]))

    # 2. Crestas superiores / coronilla (volumen facetado alto como en la referencia de Theo)
    # Cresta alta central-derecha (apuntando hacia arriba-frente):
    _agregar_mechon(bm,
                    [(1.0, -1.0, 96.5), (2.0, -3.0, 100.5), (2.5, 0.0, 103.2), (3.0, 3.5, 100.0)],
                    [9.5, 10.0, 7.0, 0.0],
                    [6.0, 6.5, 4.5, 0.0])

    # Cresta alta izquierda (+X):
    _agregar_mechon(bm,
                    [(6.0, -1.0, 95.5), (11.0, -2.5, 99.8), (14.5, 0.5, 102.5), (15.5, 3.5, 99.0)],
                    [9.0, 9.5, 6.5, 0.0],
                    [6.0, 6.2, 4.5, 0.0])

    # Cresta alta derecha (-X):
    _agregar_mechon(bm,
                    [(-5.0, -1.5, 95.5), (-10.5, -3.0, 100.0), (-14.0, -0.5, 102.8), (-15.0, 2.5, 99.5)],
                    [9.0, 9.5, 6.5, 0.0],
                    [6.0, 6.2, 4.5, 0.0])

    # 3. Mechones frontales (flequillo abierto en raya característica de Theo)
    # Mechón frontal largo izquierdo (-X, baja arqueado hacia la mejilla izquierda):
    _agregar_mechon(bm,
                    [(-2.0, -11.0, 93.0), (-6.5, -15.0, 86.5), (-11.5, -15.8, 78.5),
                     (-14.0, -13.8, 71.5), (-15.0, -11.5, 66.0)],
                    [9.0, 10.0, 8.0, 5.0, 0.0],
                    [5.8, 6.2, 5.2, 3.2, 0.0])

    # Mechón frontal derecho (+X, abre hacia la derecha dejando la frente despejada):
    _agregar_mechon(bm,
                    [(2.5, -11.0, 92.5), (7.5, -15.0, 86.5), (12.0, -15.0, 79.0),
                     (14.5, -13.0, 72.5), (15.5, -11.0, 67.0)],
                    [8.5, 9.5, 8.0, 5.0, 0.0],
                    [5.5, 6.0, 5.0, 3.2, 0.0])

    # Mechón central pequeño en el nacimiento de la raya:
    _agregar_mechon(bm,
                    [(0.5, -11.5, 91.5), (0.8, -14.5, 87.0), (0.2, -14.2, 82.5)],
                    [5.2, 5.2, 0.0],
                    [3.6, 3.6, 0.0])

    # Mechón secundario izquierdo (capa media):
    _agregar_mechon(bm,
                    [(-5.0, -12.0, 90.0), (-9.5, -15.0, 83.5), (-12.0, -14.5, 76.5)],
                    [7.0, 7.0, 0.0],
                    [4.5, 4.5, 0.0])

    # 4. Mechones laterales / patillas
    _agregar_mechon(bm,
                    [(-16.0, -2.5, 88.0), (-20.5, -5.5, 81.0), (-21.5, -6.5, 74.0), (-20.5, -7.0, 68.0)],
                    [7.5, 8.0, 5.5, 0.0],
                    [5.0, 5.5, 4.0, 0.0])
    _agregar_mechon(bm,
                    [(16.0, -2.5, 88.0), (20.5, -5.5, 81.0), (21.5, -6.5, 74.0), (20.5, -7.0, 68.0)],
                    [7.5, 8.0, 5.5, 0.0],
                    [5.0, 5.5, 4.0, 0.0])

    # 5. Mechones de la espalda (en capas escalonadas facetadas según referencia)
    # Capa alta trasera:
    _agregar_mechon(bm,
                    [(0.0, 15.0, 94.0), (0.0, 20.5, 87.5), (0.0, 21.0, 80.5), (0.0, 19.0, 75.0)],
                    [9.5, 10.0, 7.5, 0.0],
                    [6.2, 6.8, 5.0, 0.0])
    _agregar_mechon(bm,
                    [(-8.0, 14.0, 93.0), (-13.0, 19.5, 86.5), (-13.5, 19.5, 80.0), (-12.5, 18.0, 74.5)],
                    [9.0, 9.5, 7.0, 0.0],
                    [5.8, 6.2, 4.8, 0.0])
    _agregar_mechon(bm,
                    [(8.0, 14.0, 93.0), (13.0, 19.5, 86.5), (13.5, 19.5, 80.0), (12.5, 18.0, 74.5)],
                    [9.0, 9.5, 7.0, 0.0],
                    [5.8, 6.2, 4.8, 0.0])

    # Capa baja trasera (nuca, puntas escalonadas hacia el cuello):
    _agregar_mechon(bm,
                    [(0.0, 16.0, 79.0), (0.0, 18.0, 71.5), (0.0, 15.8, 65.0)],
                    [9.0, 8.5, 0.0],
                    [5.8, 5.2, 0.0])
    _agregar_mechon(bm,
                    [(-7.5, 15.2, 78.0), (-8.8, 17.0, 70.5), (-7.8, 15.0, 65.0)],
                    [8.5, 8.0, 0.0],
                    [5.2, 4.8, 0.0])
    _agregar_mechon(bm,
                    [(7.5, 15.2, 78.0), (8.8, 17.0, 70.5), (7.8, 15.0, 65.0)],
                    [8.5, 8.0, 0.0],
                    [5.2, 4.8, 0.0])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = alth._objeto(nombre, bm)
    return alth._asignar(obj, color)


objs.append(construir_cabello_theo(cabeza, color=RUBIO, nombre="Joven_pelo"))


alth.estudio()
maniqui = alth.junto_a_maniqui(objs)
rep = alth.revisar(objs, alth.RAIZ / "renders" / "joven_rubio" / MODO, modo=MODO,
                    titulo=f"joven_rubio · {MODO}", asset=alth.RAIZ / "assets" / "joven_rubio" / "spec.json",
                    extras=maniqui)
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "joven_rubio" / "joven_rubio.glb")
