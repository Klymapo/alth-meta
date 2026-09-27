"""ALTH-META · pelo grueso facetado para personajes: UNA sola malla.

Diseño para peinado voluminoso facetado (tipo cortina / anime):
1. Corona envolvente y abovedada: volumen alto y ancho en coronilla y sienes, cubriendo la nuca
   y despejando orejas.
2. Cuñas frontales cortina gruesas, anchas y carnosas cayendo hacia adelante sobre la frente y sienes.
3. Cuñas de copete superiores que dan altura central y redondez continua sin puntas aisladas.
4. Caída lateral y trasera pegada al cráneo para mantener una silueta limpia.
"""
from __future__ import annotations

import math
import random


# ---------------------------------------------------------------- geometría pura
def _zona_z(azimut_grados: float, z_frente: float, z_lado: float, z_atras: float) -> float:
    """Altura del borde de la corona según azimut.
    270° = frente (−Y), 90° = atrás (+Y), 0° / 180° = lados (±X)."""
    s = math.sin(math.radians(azimut_grados))
    if s <= 0:
        return z_lado + (z_frente - z_lado) * (-s)
    return z_lado + (z_atras - z_lado) * s


def _punto_corona(azimut_grados: float, corona: dict, escala_radio: float = 1.0):
    a = math.radians(azimut_grados)
    x = corona["cx"] + corona["hw"] * escala_radio * math.cos(a)
    y = corona["cy"] + corona["hd"] * escala_radio * math.sin(a)
    z = _zona_z(azimut_grados, corona["z_frente"], corona["z_lado"], corona["z_atras"])
    return x, y, z


def plan_corona(cabeza: dict, escala: float = 1.36, sesgo_atras: float = 0.8,
                 margen_arriba: float = 8.5, segmentos: int = 14) -> dict:
    """Base abovedada alta y ancha que define el volumen general del cráneo y pelo superior."""
    return {
        "cx": cabeza["pos"][0], "cy": cabeza["pos"][1] + sesgo_atras,
        "hw": cabeza["w_arriba"] / 2 * escala, "hd": cabeza["d_arriba"] / 2 * escala,
        "z_top": cabeza["pos"][2] + cabeza["h"] + margen_arriba,
        "z_cenit": cabeza["pos"][2] + cabeza["h"] + margen_arriba + 6.0,
        "z_frente": cabeza["pos"][2] + cabeza["h"] * 0.82,  # despeja frente
        "z_lado": cabeza["pos"][2] + cabeza["h"] * 0.74,    # sobre las orejas
        "z_atras": cabeza["pos"][2] + cabeza["h"] * 0.22,   # nuca cubierta
        "segmentos": segmentos,
    }


def plan_cunias(corona: dict, cunias: int = 6, ancho_base=(14.0, 17.0), largo=(8.0, 11.0),
                 caida=(4.0, 5.5), semilla: int = 1) -> list[dict]:
    """Cuñas traseras de la nuca, compactas y pegadas hacia abajo sin abrirse a los lados."""
    rng = random.Random(semilla)
    piezas = []

    # Solo en el arco posterior (de 30° a 150°, nuca estricta)
    ini, fin = 30.0, 150.0
    for i in range(cunias):
        t = (i + 0.5) / cunias
        az = ini + (fin - ini) * t
        x, y, z = _punto_corona(az, corona)
        a = math.radians(az)
        # Caída casi vertical pegada al cráneo
        inclinacion = math.radians(82.0)
        lift_r, lift_z = math.cos(inclinacion), -math.sin(inclinacion)
        direccion = (math.cos(a) * lift_r, math.sin(a) * lift_r, lift_z)
        piezas.append({
            "pos": (x, y, z), "direccion": direccion, "arriba": (0.0, 0.0, 1.0),
            "largo": rng.uniform(*largo), "ancho": rng.uniform(*ancho_base),
            "caida": rng.uniform(*caida), "azimut": az, "es_marco": False, "es_copete": False
        })
    return piezas


def plan_copete(corona: dict, cantidad: int = 6, semilla: int = 3) -> list[dict]:
    """Masas volumétricas principales del peinado (referencia: copete cortina anime):
    - Grandes cuñas de flequillo cortina cayendo hacia adelante y los lados sobre la frente.
    - Cúspide y cresta superior voluminosa con transiciones facetadas anchas.
    - Relleno de sienes y coronilla que aporta la anchura superior necesaria.
    """
    piezas = []

    # 1. Flequillo cortina izquierdo (mirando de frente, en X negativa): masa ancha y carnosa
    x_izq = corona["cx"] - corona["hw"] * 0.35
    y_front = corona["cy"] - corona["hd"] * 0.50
    z_f = corona["z_top"] + 1.5
    d_izq = (-0.35, -0.72, -0.60)
    norm = math.sqrt(sum(v * v for v in d_izq))
    piezas.append({
        "pos": (x_izq, y_front, z_f),
        "direccion": tuple(v / norm for v in d_izq),
        "arriba": (0.1, -0.3, 0.95),
        "largo": 23.0, "ancho": 20.0, "caida": 2.5,
        "azimut": 255.0, "es_marco": False, "es_copete": True,
    })

    # Mechón secundario izquierdo (lateral sien izquierda)
    x_izq2 = corona["cx"] - corona["hw"] * 0.60
    d_izq2 = (-0.42, -0.58, -0.70)
    norm = math.sqrt(sum(v * v for v in d_izq2))
    piezas.append({
        "pos": (x_izq2, y_front + 3.0, z_f - 2.0),
        "direccion": tuple(v / norm for v in d_izq2),
        "arriba": (0.2, -0.2, 0.96),
        "largo": 19.0, "ancho": 16.0, "caida": 2.5,
        "azimut": 240.0, "es_marco": False, "es_copete": True,
    })

    # 2. Flequillo cortina derecho (en X positiva): dos cuñas anchas escalonadas
    x_der = corona["cx"] + corona["hw"] * 0.32
    d_der1 = (0.35, -0.72, -0.60)
    norm = math.sqrt(sum(v * v for v in d_der1))
    piezas.append({
        "pos": (x_der, y_front, z_f),
        "direccion": tuple(v / norm for v in d_der1),
        "arriba": (-0.1, -0.3, 0.95),
        "largo": 22.0, "ancho": 19.0, "caida": 2.5,
        "azimut": 285.0, "es_marco": False, "es_copete": True,
    })

    x_der2 = corona["cx"] + corona["hw"] * 0.60
    d_der2 = (0.45, -0.58, -0.68)
    norm = math.sqrt(sum(v * v for v in d_der2))
    piezas.append({
        "pos": (x_der2, y_front + 2.5, z_f - 2.0),
        "direccion": tuple(v / norm for v in d_der2),
        "arriba": (-0.2, -0.2, 0.96),
        "largo": 20.0, "ancho": 16.5, "caida": 2.5,
        "azimut": 298.0, "es_marco": False, "es_copete": True,
    })

    # 3. Mechón central superior alto (la cúspide del peinado cortina)
    x_c = corona["cx"] + 1.5
    y_c = corona["cy"] - corona["hd"] * 0.15
    z_c = corona["z_cenit"] - 0.5
    d_cen = (0.20, -0.35, 0.91)
    norm = math.sqrt(sum(v * v for v in d_cen))
    piezas.append({
        "pos": (x_c, y_c, z_c),
        "direccion": tuple(v / norm for v in d_cen),
        "arriba": (-0.9, 0.0, 0.44),
        "largo": 17.5, "ancho": 18.0, "caida": 1.5,
        "azimut": 270.0, "es_marco": False, "es_copete": True,
    })

    # 4. Mechón superior izquierdo de la coronilla
    x_ci = corona["cx"] - 3.5
    d_ceni = (-0.28, -0.35, 0.89)
    norm = math.sqrt(sum(v * v for v in d_ceni))
    piezas.append({
        "pos": (x_ci, y_c, z_c - 0.5),
        "direccion": tuple(v / norm for v in d_ceni),
        "arriba": (0.9, 0.0, 0.44),
        "largo": 16.5, "ancho": 17.0, "caida": 1.5,
        "azimut": 260.0, "es_marco": False, "es_copete": True,
    })

    # 5. Masas de volumen superior en sienes (ensanchan la silueta superior para llenar las bandas 1 y 2)
    for s in (-1, 1):
        x_t = corona["cx"] + s * (corona["hw"] * 0.62)
        y_t = corona["cy"] - corona["hd"] * 0.05
        z_t = corona["z_top"] + 2.0
        d_t = (s * 0.65, -0.28, 0.70)
        norm = math.sqrt(sum(v * v for v in d_t))
        piezas.append({
            "pos": (x_t, y_t, z_t),
            "direccion": tuple(v / norm for v in d_t),
            "arriba": (-s * 0.4, 0.0, 0.92),
            "largo": 15.0, "ancho": 18.0, "caida": 2.0,
            "azimut": 270.0 + s * 55.0, "es_marco": False, "es_copete": True,
        })

    return piezas


def plan_pelo(cabeza: dict, escala: float = 1.36, sesgo_atras: float = 0.8, margen_arriba: float = 8.5,
              segmentos_corona: int = 14, cunias: int = 6, ancho_base=(14.0, 17.0), largo=(8.0, 11.0),
              caida=(4.0, 5.5), copete: int = 7, semilla: int = 1) -> dict:
    corona = plan_corona(cabeza, escala=escala, sesgo_atras=sesgo_atras, margen_arriba=margen_arriba,
                          segmentos=segmentos_corona)
    piezas = plan_cunias(corona, cunias=cunias, ancho_base=ancho_base, largo=largo, caida=caida,
                          semilla=semilla)
    piezas += plan_copete(corona, cantidad=copete, semilla=semilla + 1)
    return {"corona": corona, "cunias": piezas}


# ---------------------------------------------------------------- malla real
def _base_ortonormal(direccion, arriba_ref):
    from mathutils import Vector

    d = Vector(direccion).normalized()
    ref = Vector(arriba_ref).normalized()
    if abs(d.dot(ref)) > 0.95:
        ref = Vector((1.0, 0.0, 0.0))
    lado = d.cross(ref).normalized()
    arriba = lado.cross(d).normalized()
    return d, lado, arriba


def _agregar_corona(bm, corona, top_escala=0.92):
    """Cúpula facetada: anillo inferior, anillo superior y centro abovedado."""
    seg = corona["segmentos"]
    abajo, arriba = [], []
    for s in range(seg):
        az = 360.0 * s / seg
        abajo.append(bm.verts.new(_punto_corona(az, corona)))
        xt, yt, _ = _punto_corona(az, corona, escala_radio=top_escala)
        arriba.append(bm.verts.new((xt, yt, corona["z_top"])))

    # Pared lateral facetada
    for s in range(seg):
        k = (s + 1) % seg
        bm.faces.new((abajo[s], abajo[k], arriba[k], arriba[s]))

    # Remate superior abovedado
    z_cenit = corona.get("z_cenit", corona["z_top"] + 6.0)
    cenit = bm.verts.new((corona["cx"], corona["cy"], z_cenit))
    for s in range(seg):
        k = (s + 1) % seg
        bm.faces.new((arriba[s], arriba[k], cenit))

    return abajo, arriba


def _agregar_cuna(bm, pos, direccion, largo, ancho, caida, grosor=None, arriba_ref=(0.0, 0.0, 1.0),
                   estaciones=3, achatado=0.62):
    """Cuña gruesa y romo-facetada: volumen prismático carnoso con remate plano."""
    from mathutils import Vector

    grosor = ancho * 0.75 if grosor is None else grosor
    origen = Vector(pos)
    d, lado, arriba = _base_ortonormal(direccion, arriba_ref)
    anillos = []
    for i in range(estaciones + 1):
        t = i / estaciones
        centro = origen + d * (largo * t) - arriba * (caida * t * t)
        f = 1.0 - (1.0 - achatado) * t
        w, g = (ancho / 2) * f, (grosor / 2) * f
        anillo = [bm.verts.new(tuple(centro + lado * (w * ex) + arriba * (g * ey)))
                  for ex, ey in ((1, 0), (0, 1), (-1, 0), (0, -1))]
        anillos.append(anillo)

    bm.faces.new(tuple(reversed(anillos[0])))
    for a_r, b_r in zip(anillos, anillos[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a_r[i], a_r[j], b_r[j], b_r[i]))
    bm.faces.new(anillos[-1])


def construir_pelo(cabeza: dict, escala: float = 1.36, sesgo_atras: float = 0.8, margen_arriba: float = 8.5,
                    segmentos_corona: int = 14, cunias: int = 6, ancho_base=(14.0, 17.0), largo=(8.0, 11.0),
                    caida=(4.0, 5.5), copete: int = 7, semilla: int = 1, color: str = "#D2AE72",
                    nombre: str = "Pelo"):
    """Corona abovedada + cuñas masivas en UNA sola malla."""
    import bmesh
    from . import _asignar, _objeto

    plan = plan_pelo(cabeza, escala=escala, sesgo_atras=sesgo_atras, margen_arriba=margen_arriba,
                      segmentos_corona=segmentos_corona, cunias=cunias, ancho_base=ancho_base,
                      largo=largo, caida=caida, copete=copete, semilla=semilla)
    bm = bmesh.new()
    _agregar_corona(bm, plan["corona"])
    for c in plan["cunias"]:
        _agregar_cuna(bm, c["pos"], c["direccion"], c["largo"], c["ancho"], c["caida"], arriba_ref=c["arriba"])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto(nombre, bm)
    return _asignar(obj, color)
