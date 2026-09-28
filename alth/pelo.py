"""ALTH-META · pelo grueso faceteado para personajes: UNA sola malla.

Segundo enfoque (el de casco + púas sueltas no convergió en el tiempo dado: cada púa era su
propio objeto, y hacerlas tocar la cabeza con precisión, sin flotar ni enterrarse, se volvió un
problema de por sí). Ahora todo —la corona y las cuñas— es una única malla (un único objeto):

1. Una "corona" ancha (como una caja, 1.3× el cráneo), más alta y corrida hacia atrás.
2. Su borde inferior NO es plano: sube hasta la ceja al frente y hasta la oreja a los lados,
   y solo baja de verdad hacia la nuca — así la cara queda libre sin tener que encoger el radio.
3. Del borde cuelgan 8-12 cuñas anchas y facetadas (base 8-12 mm, remate romo, nunca una punta
   fina), cayendo hacia abajo y afuera; dos de ellas, a los lados del frente, enmarcan la cara.
4. Aparte, 2-3 cuñas de "copete" nacen cerca de la PUNTA de la corona (no del borde) y apuntan
   sobre todo hacia arriba y un poco hacia adelante —no radialmente—, más largas que las del
   borde: son las que dan volumen ARRIBA y hacen que se lea "de punta" de frente, no como un
   collar parejo alrededor de la cabeza.

Al ser una sola malla, la verificación de "flotantes" (que compara OBJETOS entre sí) no aplica
adentro: solo hace falta que esta malla, como conjunto, toque la cabeza — y la corona la abraza
por construcción.

`plan_pelo()` es puro (sin Blender) y se prueba en tests/; `construir_pelo()` arma la malla real
con bmesh directo (no hay una forma así en alth/__init__.py).
"""
from __future__ import annotations

import math
import random


# ---------------------------------------------------------------- geometría pura
def _zona_z(azimut_grados: float, z_frente: float, z_lado: float, z_atras: float) -> float:
    """Altura del borde de la corona en ese azimut: alta (corta) al frente, media a los lados,
    baja (larga, cubre la nuca) atrás. 270° = frente (−Y), 90° = atrás (+Y), 0°/180° = lados."""
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


def plan_corona(cabeza: dict, escala: float = 1.3, sesgo_atras: float = 2.5,
                 margen_arriba: float = 3.0, segmentos: int = 12) -> dict:
    """La caja ancha de base: `cabeza` es la pieza de personaje.plan() (pos, w_arriba, d_arriba, h)."""
    return {
        "cx": cabeza["pos"][0], "cy": cabeza["pos"][1] + sesgo_atras,
        "hw": cabeza["w_arriba"] / 2 * escala, "hd": cabeza["d_arriba"] / 2 * escala,
        "z_top": cabeza["pos"][2] + cabeza["h"] + margen_arriba,
        "z_frente": cabeza["pos"][2] + cabeza["h"] * 0.90,  # casi no baja del nacimiento del pelo
        "z_lado": cabeza["pos"][2] + cabeza["h"] * 0.72,    # más alto que la oreja: la deja libre
        "z_atras": cabeza["pos"][2] + cabeza["h"] * 0.28,   # nuca: sí baja bastante
        "segmentos": segmentos,
    }


MARCO_AZIMUT = (248.0, 292.0)  # a los dos lados del frente (270°), a la altura de la sien
LADOS_AZIMUT = (0.0, 180.0)  # los lados puros: por ahí mira la cámara "lateral" (perfil)


def _factor_lateral(azimut_grados: float, ventana: float = 42.0, minimo: float = 0.05) -> float:
    """1.0 lejos de los lados puros (nuca, marco frontal); baja hasta `minimo` justo en el lado
    (0°/180°). Se usa para que las cuñas de esa franja caigan poco y queden cortas, y así el
    perfil de la cabeza (oreja, sien, mandíbula) se siga viendo de lateral en vez de taparse con
    una sola masa de pelo — el ancho de la cuña no se toca (eso rompería el mínimo de la tarea)."""
    d = min(abs(((azimut_grados - lado) + 180) % 360 - 180) for lado in LADOS_AZIMUT)
    return minimo + (1.0 - minimo) * min(1.0, d / ventana)


def plan_cunias(corona: dict, cunias: int = 10, ancho_base=(8.0, 12.0), largo=(10.0, 17.0),
                 caida=(3.0, 8.0), largo_marco: float = 18.0, ancho_marco: float = 9.0,
                 caida_marco: float = 8.0, semilla: int = 1) -> list[dict]:
    """`cunias` (8-12) repartidas por la corona: 2 fijas de marco (enmarcan la cara, más largas y
    con más caída) y el resto en el arco largo que no es la cara (lados + nuca). Ninguna con base
    menor a `ancho_base[0]` (por la propia tarea, nunca < 6 mm). Puro: no toca Blender.

    Las del tramo de los lados puros (`LADOS_AZIMUT`) caen menos y llegan menos lejos
    (`_factor_lateral`) para dejar ver la oreja y el perfil de la cara de lateral; el ancho no se
    escala con ese factor, solo largo y caída.
    """
    if cunias < 3:
        raise ValueError("cunias necesita al menos 1 de cada lado del marco más una atrás")
    rng = random.Random(semilla)
    piezas = []
    for az in MARCO_AZIMUT:
        piezas.append(_cuna_spec(az, corona, largo_marco, ancho_marco, caida_marco, es_marco=True))

    n_otras = cunias - 2
    ini, fin = MARCO_AZIMUT[1], MARCO_AZIMUT[0] + 360.0  # el arco largo: lados + espalda
    for i in range(n_otras):
        t = (i + 0.5) / n_otras
        az = (ini + (fin - ini) * t + rng.uniform(-6.0, 6.0)) % 360.0
        factor = _factor_lateral(az)
        largo_val = rng.uniform(*largo) * (0.25 + 0.75 * factor)
        caida_val = rng.uniform(*caida) * factor
        ancho_val = max(6.0, rng.uniform(*ancho_base) * (0.5 + 0.5 * factor))
        piezas.append(_cuna_spec(az, corona, largo_val, ancho_val, caida_val, es_marco=False))
    return piezas


def _cuna_spec(az_grados: float, corona: dict, largo_val: float, ancho_val: float, caida_val: float,
               es_marco: bool) -> dict:
    x, y, z = _punto_corona(az_grados, corona)
    a = math.radians(az_grados)
    inclinacion = math.radians(18.0 if es_marco else 16.0)  # las de marco casi no bajan: enmarcan
    # hacia adelante/afuera sin cruzar sobre el ojo ni la mejilla al verlas de lateral
    lift_r, lift_z = math.cos(inclinacion), -math.sin(inclinacion)  # hacia afuera y hacia ABAJO
    direccion = (math.cos(a) * lift_r, math.sin(a) * lift_r, lift_z)
    return {"pos": (x, y, z), "direccion": direccion, "arriba": (0.0, 0.0, 1.0),
            "largo": largo_val, "ancho": ancho_val, "caida": caida_val,
            "azimut": az_grados, "es_marco": es_marco, "es_copete": False}


def plan_copete(corona: dict, cantidad: int = 3, ancho_base=(11.0, 16.0), largo=(15.0, 22.0),
                 caida=(1.0, 3.0), abanico: float = 26.0, semilla: int = 2) -> list[dict]:
    """Cuñas centrales que nacen cerca de la PUNTA de la corona (no del borde) y apuntan sobre
    todo hacia arriba (+Z) y un poco hacia adelante (−Y) — no radialmente, como las del borde —
    para que el peinado tenga volumen ARRIBA de la coronilla y se lea "de punta" de frente, no
    como un aro parejo alrededor de la cabeza. Más largas que las del borde (`plan_cunias`).

    `abanico` más ancho y orígenes repartidos en un radio mayor (no todas pegadas al centro) para
    que el conjunto se lea como un mechón alto que se abre, no como una sola púa aislada.
    """
    if cantidad < 1:
        return []
    rng = random.Random(semilla)
    piezas = []
    for i in range(cantidad):
        frac = (i - (cantidad - 1) / 2) / max(1, cantidad - 1)  # -0.5 .. 0.5 (0 si cantidad==1)
        lean = frac * abanico * 2  # abanico lateral entre ellas, para que no salgan pegadas
        radio_frac = rng.uniform(0.08, 0.42)  # cerca del techo, con más dispersión que el centro puro
        az = math.radians(270.0 + lean)  # 270° = frente
        x = corona["cx"] + corona["hw"] * radio_frac * math.cos(az)
        y = corona["cy"] + corona["hd"] * radio_frac * math.sin(az)
        z = corona["z_top"] - rng.uniform(0.3, 1.5)  # nace casi en la punta, no en el borde
        dx = math.sin(math.radians(lean)) * 0.30
        dy = -0.22 + rng.uniform(-0.05, 0.05)  # −Y: hacia adelante, menos que antes (menos "cuerno")
        dz = 0.85 + rng.uniform(-0.05, 0.05)   # +Z: sobre todo hacia arriba
        norma = math.sqrt(dx * dx + dy * dy + dz * dz)
        direccion = (dx / norma, dy / norma, dz / norma)
        piezas.append({"pos": (x, y, z), "direccion": direccion, "arriba": (0.0, 0.0, 1.0),
                        "largo": rng.uniform(*largo), "ancho": rng.uniform(*ancho_base),
                        "caida": rng.uniform(*caida), "azimut": math.degrees(az),
                        "es_marco": False, "es_copete": True})
    return piezas


def plan_pelo(cabeza: dict, escala: float = 1.3, sesgo_atras: float = 2.5, margen_arriba: float = 3.0,
              segmentos_corona: int = 12, cunias: int = 10, ancho_base=(8.0, 12.0), largo=(10.0, 17.0),
              caida=(3.0, 8.0), copete: int = 3, semilla: int = 1) -> dict:
    """Plan completo (corona + cuñas del borde + cuñas de copete arriba), pura.
    `construir_pelo` la pasa a una malla real."""
    corona = plan_corona(cabeza, escala=escala, sesgo_atras=sesgo_atras, margen_arriba=margen_arriba,
                          segmentos=segmentos_corona)
    piezas = plan_cunias(corona, cunias=cunias, ancho_base=ancho_base, largo=largo, caida=caida,
                          semilla=semilla)
    piezas += plan_copete(corona, cantidad=copete, semilla=semilla + 1)
    return {"corona": corona, "cunias": piezas}


# ---------------------------------------------------------------- malla real (bmesh directo)
def _base_ortonormal(direccion, arriba_ref):
    from mathutils import Vector  # solo en construcción (bpy disponible)

    d = Vector(direccion).normalized()
    ref = Vector(arriba_ref)
    if abs(d.dot(ref)) > 0.97:  # casi paralelos: cambia la referencia para no degenerar
        ref = Vector((1.0, 0.0, 0.0))
    lado = d.cross(ref).normalized()
    arriba = lado.cross(d).normalized()
    return d, lado, arriba


def _agregar_corona(bm, corona, top_escala=0.85):
    seg = corona["segmentos"]
    abajo, arriba = [], []
    for s in range(seg):
        az = 360.0 * s / seg
        abajo.append(bm.verts.new(_punto_corona(az, corona)))
        xt, yt, _ = _punto_corona(az, corona, escala_radio=top_escala)
        arriba.append(bm.verts.new((xt, yt, corona["z_top"])))
    bm.faces.new(tuple(reversed(arriba)))
    for s in range(seg):
        k = (s + 1) % seg
        bm.faces.new((abajo[s], abajo[k], arriba[k], arriba[s]))
    # Sin tapa de abajo a propósito: el anillo varía mucho de altura (alto al frente, bajo en la
    # nuca) y una sola cara de 12 lados ahí se triangula cruzando el hueco de la cara, colgando
    # una lengüeta de pelo justo donde tiene que quedar libre. Esa cara nunca se ve (queda contra
    # el cráneo), así que se deja abierta.
    return abajo, arriba


def _agregar_cuna(bm, pos, direccion, largo, ancho, caida, grosor=None, arriba_ref=(0.0, 0.0, 1.0),
                   estaciones=3, achatado=0.42):
    """Cuña ancha y facetada: se afina hacia la punta pero SIN converger a un vértice (remate
    romo, tapa plana) — nada de piezas delgadas, nunca una punta en aguja."""
    from mathutils import Vector

    grosor = ancho * 0.55 if grosor is None else grosor
    origen = Vector(pos)
    d, lado, arriba = _base_ortonormal(direccion, arriba_ref)
    anillos = []
    for i in range(estaciones + 1):
        t = i / estaciones
        centro = origen + d * (largo * t) - arriba * (caida * t * t)
        f = 1 - (1 - achatado) * t  # se angosta hacia la punta pero nunca llega a 0
        w, g = (ancho / 2) * f, (grosor / 2) * f
        anillo = [bm.verts.new(tuple(centro + lado * (w * ex) + arriba * (g * ey)))
                  for ex, ey in ((1, 0), (0, 1), (-1, 0), (0, -1))]
        anillos.append(anillo)
    bm.faces.new(tuple(reversed(anillos[0])))
    for a_r, b_r in zip(anillos, anillos[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a_r[i], a_r[j], b_r[j], b_r[i]))
    bm.faces.new(anillos[-1])  # tapa roma de la punta


def construir_pelo(cabeza: dict, escala: float = 1.3, sesgo_atras: float = 2.5, margen_arriba: float = 3.0,
                    segmentos_corona: int = 12, cunias: int = 10, ancho_base=(8.0, 12.0), largo=(10.0, 17.0),
                    caida=(3.0, 8.0), copete: int = 3, semilla: int = 1, color: str = "#D2AE72",
                    nombre: str = "Pelo"):
    """Corona + cuñas (borde + copete) en UNA sola malla (un único objeto)."""
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
