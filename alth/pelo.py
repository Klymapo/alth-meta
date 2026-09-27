"""ALTH-META · pelo grueso faceteado para personajes: un casco base (cobertura garantizada)

más mechones gruesos y curvados encima (silueta despeinada, sin huecos).

Distinto del pelo hecho con `alth.hoja()` (hojas planas, finas): aquí los mechones son
prismas anchos y curvos —una "cinta" gruesa que se afina y se comba hacia la punta— para una
lectura más voluminosa. El casco es el que garantiza el 100 % de cobertura (coronilla, lados,
nuca); los mechones son el detalle encima, no cargan solos con la cobertura.

`plan_casco()` y `plan_mechones()` son puros (sin Blender) y se prueban en tests/;
`construir_casco()` y `construir_mechones()` lo pasan a mallas reales con bmesh directo
(no hay una forma así en alth/__init__.py: ni `torno` —redondo simétrico— ni `hoja` —plana—).
"""
from __future__ import annotations

import math
import random


# ---------------------------------------------------------------- casco (cobertura garantizada)
def _factor_frente(azimut_grados: float, reduccion: float) -> float:
    """Cuánto se encoge el radio en esa dirección: 1.0 en los lados/espalda, hasta `1-reduccion`
    mirando derecho al frente (acimut 270°, -Y). Un casco redondo (alth.torno) es una revolución:
    lo que se agranda atrás se agranda igual de al frente en la misma altura. Este factor es lo
    que rompe esa simetría, para que el casco sí pueda bajar hasta la oreja sin taparle la cara.
    """
    frente = max(0.0, -math.sin(math.radians(azimut_grados)))
    return 1.0 - reduccion * frente ** 2


def plan_casco(cabeza: dict, escala: float = 1.3, sesgo_atras: float = 1.5, reduccion_frente: float = 0.62) -> dict:
    """Domo más grande que el cráneo (perfil por altura + reducción angular al frente, ver
    `_factor_frente`), para que cubra coronilla/lados/nuca sin montar sobre la cara.
    `cabeza`: pieza como la de personaje.plan() (pos, w_arriba, d_arriba, h).
    `escala`: 1.25-1.35 pide el propio CLAUDE.md-de-la-tarea; por debajo de 1.15 ya no cubre bien
    las orejas y por encima de 1.45 se ve como un casco de motociclista, no pelo.
    """
    radio = (cabeza["w_arriba"] / 2) * escala
    alto = cabeza["h"] * 0.58 * escala
    z_base = cabeza["pos"][2] + cabeza["h"] * 0.40  # cubre desde la ceja/sien hacia arriba
    perfil = [
        (radio * 0.78, 0.0),   # ya ancho desde abajo: que no quede una franja de sien pelada
        (radio * 0.95, alto * 0.22),
        (radio, alto * 0.5),
        (radio * 0.55, alto * 0.82),
        (0.02, alto),
    ]
    return {
        "perfil": perfil,
        "pos": (cabeza["pos"][0], cabeza["pos"][1] + sesgo_atras, z_base),
        "ovalo": (1.0, cabeza["d_arriba"] / cabeza["w_arriba"]),
        "radio_ecuador": radio,
        "alto": alto,
        "z_base": z_base,
        "reduccion_frente": reduccion_frente,
    }


def construir_casco(cabeza: dict, escala: float = 1.3, sesgo_atras: float = 1.5,
                     reduccion_frente: float = 0.62, segmentos: int = 14, color: str = "#C9B89F"):
    """Como alth.torno, pero con el radio de cada vértice encogido según `_factor_frente` (no hay
    revolución simétrica en alth/__init__.py que resuelva esto; se arma la malla directo)."""
    import bmesh
    from . import _asignar, _objeto

    d = plan_casco(cabeza, escala=escala, sesgo_atras=sesgo_atras, reduccion_frente=reduccion_frente)
    perfil, (ox, oy) = d["perfil"], d["ovalo"]
    rng = random.Random(4)
    bm = bmesh.new()
    anillos = []
    for r, z in perfil:
        anillo = []
        for s in range(segmentos):
            az = 360.0 * s / segmentos
            rr = r * _factor_frente(az, reduccion_frente) * (1 + rng.uniform(-0.05, 0.05))
            a = math.radians(az)
            anillo.append(bm.verts.new((rr * math.cos(a) * ox, rr * math.sin(a) * oy, z)))
        anillos.append(anillo)
    base = bm.verts.new((0.0, 0.0, perfil[0][1]))
    for s in range(segmentos):
        k = (s + 1) % segmentos
        bm.faces.new((base, anillos[0][k], anillos[0][s]))
    for a_ring, b_ring in zip(anillos, anillos[1:]):
        for s in range(segmentos):
            k = (s + 1) % segmentos
            bm.faces.new((a_ring[s], a_ring[k], b_ring[k], b_ring[s]))
    punta = bm.verts.new((0.0, 0.0, perfil[-1][1]))
    for s in range(segmentos):
        k = (s + 1) % segmentos
        bm.faces.new((anillos[-1][s], anillos[-1][k], punta))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto("Pelo_casco", bm)
    obj.location = d["pos"]
    return _asignar(obj, color)


# ---------------------------------------------------------------- mechones (cantidad, largo, dirección, caída)
def plan_mechones(casco: dict, cabeza: dict, cantidad: int = 22, largo=(9.0, 16.0), ancho=(3.0, 6.0),
                   caida=(0.5, 5.0), semilla: int = 1) -> list[dict]:
    """`cantidad` mechones repartidos por la superficie del casco (coronilla, lados, nuca).
    `largo`/`ancho`/`caida` son rangos (mm) de donde se sortea cada mechón. No incluye los dos
    mechones largos de al frente (ver `mechones_marco_cara`): esos van aparte y con más caída.
    Puro: cada mechón queda como {pos, direccion (x,y,z unitario), arriba (x,y,z), largo, ancho, caida}.
    """
    rng = random.Random(semilla)
    cx, cy, cz0 = casco["pos"]
    ovalo_x, ovalo_y = casco["ovalo"]
    perfil = casco["perfil"]
    mechones = []
    for _ in range(cantidad):
        # la raíz se ubica EN la superficie real del casco (mismo perfil que lo revuelve alth.torno),
        # no en una esfera aproximada: si no, algunas quedan flotando muy por encima del casco.
        z_local = rng.uniform(casco["alto"] * 0.05, casco["alto"] * 0.92)  # no hasta la puntita
        az = rng.uniform(0, 360)
        r = _radio_perfil(perfil, z_local) * _factor_frente(az, casco.get("reduccion_frente", 0.0))
        az_r = math.radians(az)
        pos = (cx + r * math.cos(az_r) * ovalo_x, cy + r * math.sin(az_r) * ovalo_y, cz0 + z_local)
        # dirección de crecimiento: hacia afuera (según su propio azimut) y hacia arriba, con
        # una inclinación ("levantamiento") aleatoria — no la normal exacta de la superficie,
        # pero se ve bien y no necesita la pendiente del perfil.
        levantamiento = math.radians(rng.uniform(10, 70))
        lift_r, lift_z = math.cos(levantamiento), math.sin(levantamiento)
        direccion = (math.cos(az_r) * lift_r, math.sin(az_r) * lift_r, lift_z)
        mechones.append({
            "pos": pos, "direccion": direccion, "arriba": (0.0, 0.0, 1.0),
            "largo": rng.uniform(*largo), "ancho": rng.uniform(*ancho), "caida": rng.uniform(*caida),
        })
    return mechones


def _radio_perfil(perfil, z_local):
    """Radio del perfil del casco a esa altura local (0 = borde inferior), interpolado —
    igual que alth.torno lo revuelve, para que la raíz de un mechón quede EN la superficie."""
    for (r0, z0), (r1, z1) in zip(perfil, perfil[1:]):
        if z0 <= z_local <= z1:
            return r0 + (r1 - r0) * (z_local - z0) / (z1 - z0)
    return perfil[0][0] if z_local < perfil[0][1] else perfil[-1][0]


def mechones_marco_cara(cabeza: dict, largo: float = 17.0, ancho: float = 4.0, caida: float = 9.0) -> list[dict]:
    """Los dos mechones largos que enmarcan la cara, uno por sien, colgando hacia adelante y abajo."""
    y_cara = cabeza["pos"][1] - cabeza["d_arriba"] / 2
    z_sien = cabeza["pos"][2] + cabeza["h"] * 0.78
    piezas = []
    for s in (-1, 1):
        x = s * cabeza["w_arriba"] * 0.42
        crudo = (s * 0.35, -0.88, 0.32)  # hacia afuera, al frente y un poco hacia abajo
        norma = math.sqrt(sum(v * v for v in crudo))
        direccion = tuple(v / norma for v in crudo)
        piezas.append({"pos": (x, y_cara + 1.0, z_sien), "direccion": direccion, "arriba": (0.0, 0.0, 1.0),
                        "largo": largo, "ancho": ancho, "caida": caida})
    return piezas


def _base_ortonormal(direccion, arriba_ref):
    from mathutils import Vector  # solo en construcción (bpy disponible)

    d = Vector(direccion).normalized()
    ref = Vector(arriba_ref)
    if abs(d.dot(ref)) > 0.97:  # casi paralelos: cambia la referencia para no degenerar
        ref = Vector((1.0, 0.0, 0.0))
    lado = d.cross(ref).normalized()
    arriba = lado.cross(d).normalized()
    return d, lado, arriba


def mechon_grueso(nombre: str, pos, direccion, largo: float, ancho: float, caida: float = 0.0,
                   grosor: float = None, arriba_ref=(0.0, 0.0, 1.0), estaciones: int = 4, color: str = "#C9B89F"):
    """Mechón grueso y curvo: sección romboidal (facetada) que se afina hacia la punta y se
    comba `caida` mm hacia abajo (gravedad/estilo). Es un prisma ancho, no una hoja plana.
    """
    import bmesh
    from . import _asignar, _objeto

    grosor = ancho * 0.45 if grosor is None else grosor
    d, lado, arriba = _base_ortonormal(direccion, arriba_ref)
    bm = bmesh.new()
    anillos = []
    for i in range(estaciones + 1):
        t = i / estaciones
        centro = d * (largo * t) - arriba * (caida * t * t)
        w, g = (ancho / 2) * (1 - 0.72 * t), (grosor / 2) * (1 - 0.55 * t)
        anillo = [bm.verts.new(tuple(centro + lado * (w * ex) + arriba * (g * ey)))
                  for ex, ey in ((1, 0), (0, 1), (-1, 0), (0, -1))]
        anillos.append(anillo)
    bm.faces.new(tuple(reversed(anillos[0])))
    for a, b in zip(anillos, anillos[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    t = 1.0
    punta = bm.verts.new(tuple(d * (largo * t) - arriba * (caida * t * t)))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((anillos[-1][i], anillos[-1][j], punta))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto(nombre, bm)
    obj.location = pos
    return _asignar(obj, color)


def construir_mechones(especificaciones: list[dict], color: str = "#C9B89F", prefijo: str = "Pelo_mechon"):
    return [mechon_grueso(f"{prefijo}_{i}", m["pos"], m["direccion"], m["largo"], m["ancho"],
                           caida=m["caida"], arriba_ref=m["arriba"], color=color)
            for i, m in enumerate(especificaciones)]
