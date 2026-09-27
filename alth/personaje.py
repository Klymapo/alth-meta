"""ALTH-META · cuerpo humano real (no bloques) para personajes, sobre el estándar de 95 mm
(docs/ALTH_META_Modelado.pdf, spec → cuerpo_base_95mm).

Distinto de `alth/cuerpo.py` (el maniquí gris de bloques para comparar escalas): aquí se
construyen las piezas reales del personaje —torso, pelvis, brazos, manos con dedos en bloque,
piernas, zapatos, cabeza con orejas y nariz— en **T-pose** (brazos rectos hacia los lados), para
que cada asset de personaje las vista encima (camisa, pantalón, pelo…).

Las uniones cuello/hombro/cadera están en ROJO en el PDF (sin fusión definitiva): se resuelven
solapando las piezas unos milímetros, igual que hace `alth.maniqui`, no con topología fusionada.

`plan()` es puro (sin Blender) y se prueba en tests/; `construir()` lo pasa a mallas reales con
alth.torno / alth.prisma / alth.caja.
"""
from __future__ import annotations

try:
    from . import cuerpo as base  # parte del paquete alth (uso normal, con bpy disponible)
except ImportError:
    import cuerpo as base  # import suelto para tests/ sin Blender (alth/ en sys.path)

# Cotas que alth/cuerpo.py no cubre (PDF pp. 4-5): dedos, oreja, nariz.
DEDOS = [  # (nombre, largo_mm, ancho_mm), del índice al meñique
    ("indice", 5.5, 1.9),
    ("medio", 6.0, 2.0),
    ("anular", 5.5, 1.9),
    ("menique", 4.7, 1.7),
]
PULGAR = {"largo": 5.1, "ancho": 2.1}
OREJA = {"W": 6.5, "H": 8.4, "D": 3.8}
NARIZ = {"W": 3.8, "H": 2.7, "D": 1.8}
MANDIBULA_D = 28.8  # cuerpo.CABEZA ya trae mandibula_W=36.2; el fondo es solo del PDF (p. 4)
SOLAPE = 1.5  # mm que una pieza se mete en la vecina (cuello, hombro, cadera, oreja, nariz)


def _ovalo_ancho_max(tabla):
    """Óvalo (X, Y) ajustado al anillo MÁS ANCHO de una tabla tipo cuerpo.TORSO/PIERNA.

    cuerpo.py promedia el fondo/ancho de todos los anillos (bueno para el maniquí de bloques,
    a ojo); aquí, como sí se verifica una cota de fondo (D) exacta, se ajusta al anillo que
    manda en el bounding box (el más ancho: pecho o cadera), para que esa cota quede exacta.
    """
    _, w, dd = max(tabla, key=lambda p: p[1])
    return (1.0, dd / w)


def _mano(x_muneca: float, z: float, s: int) -> dict:
    """Palma + dedos en bloque, en el extremo de la muñeca. `s`: +1 der, -1 izq."""
    palma_l, palma_w = base.PALMA["L"], base.PALMA["W"]
    x_palma = x_muneca + s * palma_l / 2
    x_punta = x_muneca + s * palma_l
    piezas = {
        "palma": {"tam": (palma_l, palma_w, palma_w * 0.62), "pos": (x_palma, 0.0, z)},
    }
    n = len(DEDOS)
    for i, (nombre, largo, ancho) in enumerate(DEDOS):
        # abanico vertical en la punta de la palma: el medio más arriba, el meñique más abajo
        dz = (n / 2 - 0.5 - i) * (ancho * 0.95)
        piezas[nombre] = {"tam": (largo, ancho, ancho * 0.85),
                           "pos": (x_punta + s * largo / 2 - s * SOLAPE, 0.0, z + dz)}
    piezas["pulgar"] = {  # más corto, hacia el frente (-Y) desde la base de la palma
        "tam": (PULGAR["ancho"], PULGAR["largo"], PULGAR["ancho"] * 0.9),
        "pos": (x_muneca + s * palma_w * 0.35, -(PULGAR["largo"] / 2 - SOLAPE), z - palma_w * 0.2),
    }
    return {"punta_x": x_punta, "piezas": piezas}


def plan(arquetipo: str = "estandar", grosor_extremidades: float = 1.0) -> dict:
    """Piezas reales del cuerpo en T-pose (pies en Z=0, frente hacia −Y).

    `grosor_extremidades`: multiplicador del radio de brazos/antebrazos/piernas (1.0 = cotas
    del estándar tal cual); un personaje más fornido puede pedir, p. ej., 1.25.
    """
    b = base.plan(arquetipo)
    por_nombre = {p["nombre"]: p for p in b["piezas"]}
    z_hombro = por_nombre["brazo_der"]["pos"][2]
    y_cara = base.CABEZA["y_centro"] - base.CABEZA["D"] / 2
    z_cabeza_top = b["anclas"]["altura"]
    z_ojo = z_cabeza_top - base.OJO["z_desde_arriba"]

    piezas = {
        "torso": {"tipo": "torno", "perfil": por_nombre["torso"]["perfil"],
                  "ovalo": _ovalo_ancho_max(base.TORSO), "pos": por_nombre["torso"]["pos"]},
        "pelvis": {"tipo": "caja", "tam": por_nombre["pelvis"]["tam"], "pos": por_nombre["pelvis"]["pos"]},
        "cabeza": {"tipo": "cabeza", "pos": por_nombre["cabeza"]["pos"],
                   "w_arriba": base.CABEZA["W"], "d_arriba": base.CABEZA["D"],
                   "w_abajo": base.CABEZA["mandibula_W"], "d_abajo": MANDIBULA_D,
                   "h": base.CABEZA["H"], "chaflan": 2.2, "chaflan_segmentos": 3,
                   "tam": (base.CABEZA["W"], base.CABEZA["D"], base.CABEZA["H"])},
        "nariz": {"tipo": "caja", "centro": True, "tam": (NARIZ["W"], NARIZ["D"], NARIZ["H"]),
                  "pos": (0.0, y_cara + NARIZ["D"] / 2 - SOLAPE, z_ojo - 1.4)},
    }
    for lado, s in (("izq", -1), ("der", 1)):
        pierna_perfil = [(r * grosor_extremidades, z) for r, z in por_nombre[f"pierna_{lado}"]["perfil"]]
        piezas[f"pierna_{lado}"] = {"tipo": "torno", "perfil": pierna_perfil,
                                     "ovalo": _ovalo_ancho_max(base.PIERNA),
                                     "pos": por_nombre[f"pierna_{lado}"]["pos"]}
        piezas[f"zapato_{lado}"] = {"tipo": "caja", "tam": por_nombre[f"zapato_{lado}"]["tam"],
                                     "pos": por_nombre[f"zapato_{lado}"]["pos"]}
        piezas[f"oreja_{lado}"] = {"tipo": "caja", "centro": True, "tam": (OREJA["D"], OREJA["W"], OREJA["H"]),
                                    "pos": (s * (base.CABEZA["W"] / 2 - SOLAPE), base.CABEZA["y_centro"],
                                            z_ojo + OREJA["H"] * 0.05)}

        x0 = s * base.HOMBRO_X
        largo_sup, largo_ante = base.BRAZO[0][1], base.BRAZO[1][1]
        w_sup0, w_sup1 = base.BRAZO[0][0] * grosor_extremidades, base.BRAZO[1][0] * grosor_extremidades
        w_muneca = base.MUNECA_W * grosor_extremidades
        rot = (0, 90 * s, 0)  # el eje local +Z del prisma apunta a +X (der) o −X (izq)
        x1 = x0 + s * largo_sup
        x2 = x1 + s * largo_ante
        piezas[f"brazo_{lado}"] = {"tipo": "prisma", "pos": (x0, 0.0, z_hombro),
                                    "r0": w_sup0 / 2, "r1": w_sup1 / 2, "largo": largo_sup, "rot": rot}
        piezas[f"antebrazo_{lado}"] = {"tipo": "prisma", "pos": (x1, 0.0, z_hombro),
                                        "r0": w_sup1 / 2, "r1": w_muneca / 2, "largo": largo_ante, "rot": rot}
        mano = _mano(x2, z_hombro, s)
        for parte, datos in mano["piezas"].items():
            piezas[f"mano_{lado}_{parte}"] = {"tipo": "caja", "centro": True, **datos}
        piezas[f"_punta_mano_{lado}"] = mano["punta_x"]  # útil para pruebas, no se construye

    return {"arquetipo": arquetipo, "anclas": b["anclas"], "piezas": piezas}


def _cabeza_objeto(nombre, w_arriba, d_arriba, w_abajo, d_abajo, h, pos, color):
    """Cabeza como tronco de pirámide: cráneo ancho arriba, mandíbula más angosta abajo.
    No hay una forma de alth/__init__.py para esto (ni torno —redondo— ni caja —recta—),
    así que arma la malla directo, con el mismo patrón interno (_objeto/_asignar) de esas formas."""
    import bmesh
    from . import _asignar, _objeto

    bm = bmesh.new()
    esquinas = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    abajo = [bm.verts.new((sx * w_abajo / 2, sy * d_abajo / 2, 0.0)) for sx, sy in esquinas]
    arriba = [bm.verts.new((sx * w_arriba / 2, sy * d_arriba / 2, h)) for sx, sy in esquinas]
    bm.faces.new(tuple(reversed(abajo)))
    bm.faces.new(arriba)
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((abajo[i], abajo[j], arriba[j], arriba[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto(nombre, bm)
    obj.location = pos
    return _asignar(obj, color)


def construir(arquetipo: str = "estandar", pos=(0.0, 0.0, 0.0), color_piel="#FBC39C", color_zapato="#292929",
              grosor_extremidades: float = 1.0):
    """Construye el cuerpo con alth.torno/prisma/caja. Devuelve {nombre: objeto}."""
    from . import caja, chaflan, prisma, torno  # atributos del paquete alth (definidos en __init__.py)

    pl = plan(arquetipo, grosor_extremidades=grosor_extremidades)
    ox, oy, oz = pos
    objs = {}
    for nombre, p in pl["piezas"].items():
        if nombre.startswith("_"):
            continue
        x, y, z = p["pos"]
        x, y, z = x + ox, y + oy, z + oz
        color = color_zapato if nombre.startswith("zapato_") else color_piel
        if p["tipo"] == "cabeza":
            o = _cabeza_objeto(f"Cuerpo_{nombre}", p["w_arriba"], p["d_arriba"], p["w_abajo"], p["d_abajo"],
                                p["h"], (x, y, z), color)
            chaflan(o, ancho=p["chaflan"], segmentos=p.get("chaflan_segmentos", 2))
        elif p["tipo"] == "caja":
            o = caja(f"Cuerpo_{nombre}", p["tam"], pos=(x, y, z), color=color,
                      apoyada=not p.get("centro", False), biselar="chaflan" not in p)
            if "chaflan" in p:
                chaflan(o, ancho=p["chaflan"], segmentos=2)
        elif p["tipo"] == "torno":
            o = torno(f"Cuerpo_{nombre}", p["perfil"], segmentos=12, color=color, alternar=False,
                       ruido_r=0, ruido_z=0, ovalo=p["ovalo"], pos=(x, y, z))
        else:  # prisma
            o = prisma(f"Cuerpo_{nombre}", p["r0"], p["r1"], p["largo"], lados=6, color=color,
                       pos=(x, y, z), rot=p["rot"])
        objs[nombre] = o
    return objs
