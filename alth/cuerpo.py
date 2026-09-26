"""ALTH-META · cuerpo base: cotas del estándar y plan del maniquí de escala (docs/ALTH_META_Modelado.pdf).

No es el personaje: son bloques con las medidas VERDES del estándar, para poner cualquier asset a su lado
y juzgar la escala a ojo (¿la taza cabe en su mano?, ¿la repisa le llega al pecho?).

`plan(arquetipo)` es puro (sin Blender) y se prueba en tests/; `alth.maniqui()` lo construye.
"""
from __future__ import annotations

import math

# Cotas del estándar de 95 mm (PDF v0.8.4b), en mm. W = ancho (X), D = fondo (Y), H = alto (Z).
ZAPATO = {"L": 18.0, "W": 11.9, "H": 9.0, "puntera": 13.2, "talon": 4.8}
PIERNA = [  # (z relativo dentro de la pierna 0..1, W, D): tobillo → cadera
    (0.00, 7.9, 7.1), (0.25, 9.7, 8.1), (0.50, 9.1, 7.6), (0.75, 10.6, 8.5), (1.00, 11.0, 8.9)]
PIERNA_L = 24.0
CADERA_X = 8.15
PELVIS = {"W": 25.0, "D": 17.0, "H": 5.8}
TORSO = [  # (z relativo 0..1 desde el tope de la pelvis hasta el cuello, W, D)
    (0.00, 25.2, 16.8), (0.30, 25.0, 16.4), (0.78, 30.5, 17.8), (1.00, 27.0, 15.0)]
CABEZA = {"W": 40.0, "D": 29.8, "H": 34.5, "y_centro": 0.25, "mandibula_W": 36.2}
OJO = {"W": 8.4, "H": 9.7, "x": 6.15, "z_desde_arriba": 95.0 - 78.5}
HOMBRO_X = 15.5
BRAZO = [(10.2, 11.0), (8.8, 10.0)]  # (ancho al inicio, largo): brazo superior, antebrazo
MUNECA_W = 7.0
PALMA = {"L": 7.5, "W": 7.0, "D": 4.0}
APERTURA_BRAZOS = 12.0   # grados de pose en A (0 = pegados al cuerpo)

ARQUETIPOS = {  # deltas de la spec (mm): la cabeza nunca cambia
    "menuda": {"piernas": -4, "torso": -3},
    "media": {"piernas": -3, "torso": -2},
    "estandar": {},
    "alta": {"piernas": 3, "torso": 2, "ancho_pecho": 2},
}


def plan(arquetipo: str = "estandar") -> dict:
    """Piezas del maniquí con posiciones absolutas (pies en Z=0, frente hacia −Y)."""
    d = ARQUETIPOS[arquetipo]
    piernas = PIERNA_L + d.get("piernas", 0)
    pelvis_h = PELVIS["H"]
    torso_h = (60.5 - 33.0 - pelvis_h) + d.get("torso", 0)
    ancho_pecho = d.get("ancho_pecho", 0)

    z_tobillo = ZAPATO["H"]
    z_cadera = z_tobillo + piernas
    z_pelvis_top = z_cadera + pelvis_h
    z_cuello = z_pelvis_top + torso_h
    z_cabeza_top = z_cuello + CABEZA["H"]

    piezas = []
    for lado, s in (("izq", -1), ("der", 1)):
        x = s * CADERA_X
        piezas.append({"tipo": "caja", "nombre": f"zapato_{lado}",
                       "tam": (ZAPATO["W"], ZAPATO["L"], ZAPATO["H"]),
                       "pos": (x, (ZAPATO["talon"] - ZAPATO["puntera"]) / 2, 0.0)})
        piezas.append({"tipo": "torno", "nombre": f"pierna_{lado}", "pos": (x, 0.0, z_tobillo),
                       "perfil": [(w / 2, t * piernas) for t, w, _ in PIERNA],
                       "ovalo": (1.0, sum(dd / w for _, w, dd in PIERNA) / len(PIERNA))})
    piezas.append({"tipo": "caja", "nombre": "pelvis", "tam": (PELVIS["W"], PELVIS["D"], pelvis_h),
                   "pos": (0.0, 0.0, z_cadera)})
    piezas.append({"tipo": "torno", "nombre": "torso", "pos": (0.0, 0.0, z_pelvis_top),
                   "perfil": [(w / 2 + (ancho_pecho / 2 if t > 0.5 else 0), t * torso_h) for t, w, _ in TORSO],
                   "ovalo": (1.0, sum(dd / w for _, w, dd in TORSO) / len(TORSO))})
    piezas.append({"tipo": "caja", "nombre": "cabeza", "tam": (CABEZA["W"], CABEZA["D"], CABEZA["H"]),
                   "pos": (0.0, CABEZA["y_centro"], z_cuello), "chaflan": 2.5})
    y_cara = CABEZA["y_centro"] - CABEZA["D"] / 2
    for lado, s in (("izq", -1), ("der", 1)):
        piezas.append({"tipo": "caja", "nombre": f"ojo_{lado}", "tam": (OJO["W"], 0.4, OJO["H"]), "oscuro": True,
                       "pos": (s * OJO["x"], y_cara - 0.15, z_cabeza_top - OJO["z_desde_arriba"] - OJO["H"] / 2)})

    # Brazos en pose A: el hombro se apoya bajo la cabeza, cada tramo apunta hacia abajo y afuera.
    z_hombro = z_cuello - BRAZO[0][0] / 2 + 0.6
    a = math.radians(APERTURA_BRAZOS)
    for lado, s in (("izq", -1), ("der", 1)):
        x, z = s * HOMBRO_X, z_hombro
        dx, dz = s * math.sin(a), -math.cos(a)
        tramos = [("brazo", BRAZO[0][0], BRAZO[1][0], BRAZO[0][1]),
                  ("antebrazo", BRAZO[1][0], MUNECA_W, BRAZO[1][1])]
        for nombre, w0, w1, largo in tramos:
            piezas.append({"tipo": "prisma", "nombre": f"{nombre}_{lado}", "pos": (x, 0.0, z),
                           "r0": w0 / 2, "r1": w1 / 2, "largo": largo, "rot": (180, -s * APERTURA_BRAZOS, 0)})
            x, z = x + dx * largo, z + dz * largo
        piezas.append({"tipo": "prisma", "nombre": f"mano_{lado}", "pos": (x, 0.0, z),
                       "r0": PALMA["W"] / 2, "r1": PALMA["W"] / 2 * 0.9, "largo": PALMA["L"], "lados": 4,
                       "rot": (180, -s * APERTURA_BRAZOS, 0)})
        if s == 1:
            z_muneca, z_mano = z, z + dz * PALMA["L"]

    return {
        "arquetipo": arquetipo, "piezas": piezas,
        "anclas": {"tobillo": z_tobillo, "rodilla": z_tobillo + piernas / 2, "cadera": z_cadera,
                   "cintura": z_pelvis_top, "cuello": z_cuello, "hombro": z_hombro,
                   "muneca": round(z_muneca, 2), "punta_mano": round(z_mano, 2), "altura": z_cabeza_top},
    }
