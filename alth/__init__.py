"""ALTH-META · utilidades de Blender sin interfaz.

Se usa siempre con `alth-python` (Python con el módulo bpy):

    import alth
    alth.nueva_escena()
    cubo = alth.caja("cubo", (20, 20, 20), color="#A8453B")
    alth.estudio()
    alth.revisar([cubo], "renders/fase0", modo="iteracion")
    alth.exportar_glb([cubo], "exports/fase0/cubo.glb")

Convenciones (spec/alth_spec.json): 1 BU = 1 mm, pies en Z=0, frente hacia -Y.
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import bpy  # isort: skip  (bpy debe cargarse antes que bmesh y mathutils)
import bmesh  # isort: skip
from mathutils import Vector  # isort: skip

RAIZ = Path(__file__).resolve().parent.parent
SPEC = json.loads((RAIZ / "spec" / "alth_spec.json").read_text(encoding="utf-8"))
FONDO = SPEC["paleta"]["fondo_revision"]

VISTAS = {  # dirección desde el centro del objeto hacia la cámara
    "frente": Vector((0, -1, 0)),
    "lateral": Vector((1, 0, 0)),
    "espalda": Vector((0, 1, 0)),
    "tres_cuartos": Vector((0.62, -0.72, 0.32)).normalized(),
}

MODOS = {
    "iteracion": {"px": 400, "muestras": 16},
    "final": {"px": 1024, "muestras": 64},
}


# ---------------------------------------------------------------- color
def hex_a_lineal(hexa: str, alfa: float = 1.0):
    """#RRGGBB (sRGB) → RGBA lineal, que es lo que esperan los nodos de Blender."""
    h = hexa.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, alfa)


def kelvin_a_rgb(k: float):
    """Aproximación de temperatura de color (Tanner Helland), en lineal."""
    t = k / 100
    r = 255 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    hexa = "#%02X%02X%02X" % tuple(int(max(0, min(255, v))) for v in (r, g, b))
    return hex_a_lineal(hexa)[:3]


# ---------------------------------------------------------------- escena
def nueva_escena():
    """Escena vacía en milímetros con Cycles en CPU."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _capas["n"] = 0
    esc = bpy.context.scene
    us = esc.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"
    esc.render.engine = "CYCLES"
    esc.cycles.device = "CPU"
    esc.cycles.use_denoising = True
    try:
        esc.cycles.denoiser = "OPENIMAGEDENOISE"
    except (AttributeError, TypeError):
        pass
    esc.render.film_transparent = True  # el fondo se compone después, con el color exacto
    esc.render.image_settings.file_format = "PNG"
    esc.render.image_settings.color_mode = "RGBA"
    try:
        esc.view_settings.view_transform = "Standard"  # respeta los hex de la paleta
    except TypeError:
        pass
    return esc


def _nodos(idb):
    """Activa nodos en material o mundo (en Blender 5 ya vienen activos)."""
    try:
        idb.use_nodes = True
    except AttributeError:
        pass
    return idb.node_tree


COLORES_USADOS = {}  # nombre de material → hex, para la verificación de paleta


def material(nombre: str, color: str, rugosidad=None, metalico=0.0, faceta=False):
    m = SPEC["material"]
    COLORES_USADOS[nombre] = color.upper()
    mat = bpy.data.materials.get(nombre) or bpy.data.materials.new(nombre)
    arbol = _nodos(mat)
    bsdf = next((n for n in arbol.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = arbol.nodes.new("ShaderNodeBsdfPrincipled")
        salida = next((n for n in arbol.nodes if n.type == "OUTPUT_MATERIAL"), None) \
            or arbol.nodes.new("ShaderNodeOutputMaterial")
        arbol.links.new(bsdf.outputs["BSDF"], salida.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = hex_a_lineal(color)
    if faceta:
        _conectar_faceta(arbol, bsdf, color)
    bsdf.inputs["Roughness"].default_value = m["rugosidad"] if rugosidad is None else rugosidad
    bsdf.inputs["Metallic"].default_value = metalico
    for clave in ("Specular IOR Level", "Specular"):
        if clave in bsdf.inputs:
            bsdf.inputs[clave].default_value = m["especular"]
            break
    mat.diffuse_color = hex_a_lineal(color)
    return mat


FACETA_ATTR = "alth_faceta"


def _objeto(nombre, bm, variacion=None, semilla=None):
    """Malla con sombreado plano y una variación de valor por cara (spec: ±3 %)."""
    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False  # sombreado plano: las facetas se ven
    var = SPEC["geometria"].get("variacion_cara", 0.03) if variacion is None else variacion
    if var > 0:
        rnd = random.Random(semilla if semilla is not None else nombre)
        attr = me.color_attributes.new(FACETA_ATTR, "FLOAT_COLOR", "CORNER")
        for p in me.polygons:
            v = 1 + rnd.uniform(-var, var)
            for li in p.loop_indices:
                attr.data[li].color = (v, v, v, 1.0)
    obj = bpy.data.objects.new(nombre, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def chaflan(obj, ancho=None, segmentos=None, angulo=40):
    """Chaflán proporcional al tamaño (spec → geometria.chaflan_por_tamano).

    Sin `ancho`, lo decide la dimensión mayor del objeto; devuelve None si no aplica.
    `angulo`: solo bisela aristas más agudas que eso, para no llenar de triángulos las formas curvas.
    """
    g = SPEC["geometria"]
    if ancho is None:
        bpy.context.view_layer.update()
        mayor = max(obj.dimensions)
        ancho = next((r["mm"] for r in g["chaflan_por_tamano"] if mayor >= r["desde_mm"]), 0)
    if ancho <= 0:
        return None
    mod = obj.modifiers.new("Chaflan", "BEVEL")
    mod.width = ancho
    mod.segments = g["chaflan_segmentos"] if segmentos is None else segmentos
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angulo)
    return mod


def _conectar_faceta(arbol, bsdf, color):
    """Color base × atributo por cara. Solo se usa en mallas que tienen el atributo:
    si falta, el nodo Attribute devuelve negro."""
    try:
        attr = arbol.nodes.new("ShaderNodeAttribute")
        attr.attribute_name = FACETA_ATTR
        mix = arbol.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        fac = next(i for i in mix.inputs if i.type == "VALUE")
        a = next(i for i in mix.inputs if i.name == "A" and i.type == "RGBA")
        b = next(i for i in mix.inputs if i.name == "B" and i.type == "RGBA")
        out = next(o for o in mix.outputs if o.type == "RGBA")
        fac.default_value = 1.0
        a.default_value = hex_a_lineal(color)
        arbol.links.new(attr.outputs["Color"], b)
        arbol.links.new(out, bsdf.inputs["Base Color"])
    except Exception as e:  # noqa: BLE001 — la variación es cosmética; no debe tumbar el render
        print(f"[alth] aviso: sin variación por cara ({e})")


def _asignar(obj, color, nombre_mat=None, **kw_mat):
    kw_mat.setdefault("faceta", FACETA_ATTR in obj.data.color_attributes)
    obj.data.materials.append(material(nombre_mat or f"M_{obj.name}", color, **kw_mat))
    return obj


# ---------------------------------------------------------------- formas
def torno(nombre, perfil, segmentos=10, color="#A8453B", alternar=True,
          ruido_r=0.06, ruido_z=0.1, centro_abajo=None, centro_arriba=None,
          ovalo=(1.0, 1.0), semilla=7, pos=(0, 0, 0), giro=0, bandas=None):
    """Sólido de revolución facetado: frutas, latas, vasos, tazas, jarrones, cabezas de bastón…

    perfil: lista de (radio_mm, z_mm) de abajo hacia arriba.
    alternar: gira medio segmento cada anillo → facetas triangulares (look low-poly).
    ruido_r / ruido_z: irregularidad (fracción del radio / mm) en los anillos intermedios.
    centro_abajo / centro_arriba: z del vértice que cierra cada tapa. Por debajo del último
      anillo hace una cuenca (hundido del tallo); None cierra al nivel del anillo.
    ovalo: escala (x, y) para secciones no circulares.
    giro: grados que se rota la sección (0 por defecto, para no alterar assets aprobados).
      "frente" deja una CARA (no una arista) mirando a −Y: úsalo con etiquetas y calcomanías.
    bandas: colores por altura, en vez de `color`: lista de (z_max_mm, color) o
      (z_max_mm, color, "metal"), de abajo hacia arriba; cada cara toma la banda de su centro.
    """
    if giro == "frente":
        giro = 270 - 180 / segmentos  # la cara 0 queda centrada en 270° (−Y), con N par o impar
    rnd = random.Random(semilla)
    caras = []
    bm = bmesh.new()
    anillos = []
    n = len(perfil)
    for i, (r, z) in enumerate(perfil):
        des = (i % 2) * math.pi / segmentos if alternar else 0
        medio = 0 < i < n - 1
        anillo = []
        for s in range(segmentos):
            a = 2 * math.pi * s / segmentos + des + math.radians(giro)
            j = 1 + (rnd.uniform(-ruido_r, ruido_r) if medio else 0)
            zz = z + (rnd.uniform(-ruido_z, ruido_z) if medio else 0)
            anillo.append(bm.verts.new((r * j * math.cos(a) * ovalo[0], r * j * math.sin(a) * ovalo[1], zz)))
        anillos.append(anillo)
    abajo = bm.verts.new((0, 0, perfil[0][1] if centro_abajo is None else centro_abajo))
    arriba = bm.verts.new((0, 0, perfil[-1][1] if centro_arriba is None else centro_arriba))
    def cara(*vs):
        caras.append((bm.faces.new(vs), sum(v.co.z for v in vs) / len(vs)))

    for s in range(segmentos):
        k = (s + 1) % segmentos
        cara(abajo, anillos[0][k], anillos[0][s])
        cara(arriba, anillos[-1][s], anillos[-1][k])
    for i in range(n - 1):
        a, b = anillos[i], anillos[i + 1]
        for s in range(segmentos):
            k = (s + 1) % segmentos
            if not alternar:
                cara(a[s], a[k], b[k], b[s])
            elif i % 2 == 0:
                cara(a[s], a[k], b[s])
                cara(a[k], b[k], b[s])
            else:
                cara(a[s], b[k], b[s])
                cara(a[s], a[k], b[k])
    if bandas:
        for f, zc in caras:
            f.material_index = next((i for i, bd in enumerate(bandas) if zc <= bd[0] + 1e-6), len(bandas) - 1)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto(nombre, bm, semilla=semilla)
    obj.location = pos
    if not bandas:
        return _asignar(obj, color)
    for i, bd in enumerate(bandas):
        kw = {"metalico": SPEC["material"]["metal_suave"]["metalico"],
              "rugosidad": SPEC["material"]["metal_suave"]["rugosidad"]} if len(bd) > 2 and bd[2] == "metal" else {}
        _asignar(obj, bd[1], nombre_mat=f"M_{nombre}_{i}", **kw)
    return obj


def prisma(nombre, radio_base, radio_punta, largo, lados=5, color="#69472D", pos=(0, 0, 0), rot=(0, 0, 0)):
    """Prisma cónico a lo largo de +Z: tallos, patas, mangos, velas, dedos simples."""
    perfil = [(radio_base, 0.0), (radio_punta, largo)]
    obj = torno(nombre, perfil, segmentos=lados, color=color, alternar=False, ruido_r=0, ruido_z=0, giro=0)
    obj.location = pos
    obj.rotation_euler = tuple(math.radians(v) for v in rot)
    return obj


def anillo(nombre, radio, grosor, segmentos=8, lados=3, color="#B7BABE", metal=False,
           escala=(1.0, 1.0, 1.0), pos=(0, 0, 0), rot=(0, 0, 0)):
    """Toroide low-poly acostado en el plano XY: argollas, lengüetas de lata, asas, pulseras, llaveros.

    radio: al centro del tubo (mm). grosor: diámetro del tubo. lados: 3 = sección triangular.
    """
    bm = bmesh.new()
    t = grosor / 2
    vs = []
    for s in range(segmentos):
        a = 2 * math.pi * s / segmentos
        fila = []
        for l in range(lados):
            b = 2 * math.pi * l / lados + math.pi / 2
            rr = radio + t * math.cos(b)
            fila.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), t * math.sin(b))))
        vs.append(fila)
    for s in range(segmentos):
        k = (s + 1) % segmentos
        for l in range(lados):
            m = (l + 1) % lados
            bm.faces.new((vs[s][l], vs[k][l], vs[k][m], vs[s][m]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto(nombre, bm)
    obj.location = pos
    obj.rotation_euler = tuple(math.radians(v) for v in rot)
    obj.scale = escala
    kw = {"metalico": SPEC["material"]["metal_suave"]["metalico"],
          "rugosidad": SPEC["material"]["metal_suave"]["rugosidad"]} if metal else {}
    return _asignar(obj, color, **kw)


# ---------------------------------------------------------------- calcomanías
# Dibujos planos (etiquetas, logotipos, parches) pegados a una cara de un torno facetado.
# Todas salen con el MISMO grosor hacia afuera (0.02 mm) y un poco hundidas, así que no
# asoman de canto en las vistas laterales ni se pierden dentro del cuerpo.
# Coordenadas de cara: u = horizontal sobre la cara (+u hacia la derecha vista de frente), z = altura.
CALCO_GROSOR = 0.02    # separación de la primera calcomanía respecto a la cara (mm)
CALCO_CAPA = 0.006     # cada calcomanía siguiente queda esto más afuera: la última dibujada queda encima
_capas = {"n": 0}


def marco_cara(radio, lados, indice=0, giro="frente"):
    """Sistema de coordenadas de una cara de `torno(..., segmentos=lados, alternar=False)`.

    indice 0 es la cara que queda al frente con giro="frente"; +1 la de la derecha, −1 la de la izquierda.
    `radio` es el del tramo donde va la calcomanía (el radio del torno, no el de los bordes).
    """
    g = 270 - 180 / lados if giro == "frente" else giro
    c = math.radians(g + 360 * (indice + 0.5) / lados)
    ap = radio * math.cos(math.pi / lados)
    return {"centro": (ap * math.cos(c), ap * math.sin(c)), "n": (math.cos(c), math.sin(c)),
            "t": (-math.sin(c), math.cos(c)), "semiancho": radio * math.sin(math.pi / lados),
            "angulo": math.degrees(c)}


def contorno_ovalo(cu, cz, ru, rz, lados=9, giro=0):
    g = math.radians(giro)
    return [(cu + ru * math.cos(2 * math.pi * i / lados + g), cz + rz * math.sin(2 * math.pi * i / lados + g))
            for i in range(lados)]


def contorno_gota(base, angulo, largo, ancho, estaciones=4):
    """Hoja plana: nace en `base` (u, z) y apunta a `angulo` grados (0 = derecha, 90 = arriba)."""
    a = math.radians(angulo)
    d, p = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    ts = [i / (estaciones + 1) for i in range(1, estaciones + 1)]
    w = [ancho / 2 * math.sin(math.pi * t ** 0.62) for t in ts]
    pt = lambda t, s: (base[0] + d[0] * t * largo + p[0] * s, base[1] + d[1] * t * largo + p[1] * s)
    return [base] + [pt(t, x) for t, x in zip(ts, w)] + [pt(1, 0)] + [pt(t, -x) for t, x in reversed(list(zip(ts, w)))]


def contorno_tira(puntos, ancho):
    """Cinta plana de `ancho` mm que sigue una polilínea [(u, z), …]: ramas, tallos, rayas, letras simples."""
    izq, der = [], []
    n = len(puntos)
    for i, (u, z) in enumerate(puntos):
        a = puntos[max(i - 1, 0)]
        b = puntos[min(i + 1, n - 1)]
        du, dz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(du, dz) or 1.0
        nu, nz = -dz / L * ancho / 2, du / L * ancho / 2
        izq.append((u + nu, z + nz))
        der.append((u - nu, z - nz))
    return izq + der[::-1]


def _recortar_franja(poli, umin, umax):
    """Recorta un polígono [(u, z)] a la franja umin ≤ u ≤ umax (Sutherland–Hodgman)."""
    def corte(pts, dentro, cruce):
        out = []
        for i, p in enumerate(pts):
            q = pts[(i + 1) % len(pts)]
            if dentro(p):
                out.append(p)
                if not dentro(q):
                    out.append(cruce(p, q))
            elif dentro(q):
                out.append(cruce(p, q))
        return out

    def en_u(p, q, u):
        t = (u - p[0]) / (q[0] - p[0])
        return (u, p[1] + t * (q[1] - p[1]))

    pts = corte(poli, lambda p: p[0] >= umin, lambda p, q: en_u(p, q, umin)) if poli else []
    pts = corte(pts, lambda p: p[0] <= umax, lambda p, q: en_u(p, q, umax)) if pts else []
    limpio = []
    for p in pts:
        if not limpio or math.hypot(p[0] - limpio[-1][0], p[1] - limpio[-1][1]) > 1e-6:
            limpio.append(p)
    if len(limpio) > 1 and math.hypot(limpio[0][0] - limpio[-1][0], limpio[0][1] - limpio[-1][1]) <= 1e-6:
        limpio.pop()
    return limpio if len(limpio) >= 3 else []


def _area(poli):
    return sum(poli[i][0] * poli[(i + 1) % len(poli)][1] - poli[(i + 1) % len(poli)][0] * poli[i][1]
               for i in range(len(poli))) / 2


def calcomania(nombre, contorno, radio, lados, indice=0, giro="frente", color="#495432", capa=None):
    """Calcomanía que ENVUELVE un torno facetado, como una etiqueta impresa.

    Dibuja `contorno` [(u, z), …] en la etiqueta desenrollada: u = 0 es el centro de la cara
    `indice` y cada cara mide 2·semiancho. Se corta sola en las aristas y cada pedazo se pega plano
    a su cara. Es una superficie de una sola cara (sin grosor): de canto no se ve.
    En las aristas los pedazos comparten el punto donde se cruzan sus planos, así no queda rendija.
    capa: None = automática por orden de llamada (la última queda encima); o un entero.
    """
    if capa is None:
        capa = _capas["n"]
        _capas["n"] += 1
    g = CALCO_GROSOR + CALCO_CAPA * capa
    if _area(contorno) < 0:
        contorno = contorno[::-1]          # antihorario en (u, z) → la cara mira hacia afuera
    s = radio * math.sin(math.pi / lados)
    cos_mitad = math.cos(math.pi / lados)
    us = [u for u, _ in contorno]
    k0, k1 = math.floor((min(us) + s) / (2 * s)), math.floor((max(us) + s) / (2 * s))
    bm = bmesh.new()
    for k in range(k0, k1 + 1):
        pedazo = _recortar_franja(contorno, (2 * k - 1) * s, (2 * k + 1) * s)
        if not pedazo:
            continue
        m = marco_cara(radio, lados, indice + k, giro)
        cx, cy = m["centro"]
        (nx, ny), (tx, ty) = m["n"], m["t"]
        vs = []
        for u, z in pedazo:
            ul = u - 2 * k * s
            if abs(abs(ul) - s) < 1e-6:
                # sobre la arista: punto común de los dos planos desplazados (inglete)
                ex, ey = cx + tx * ul, cy + ty * ul
                r = math.hypot(ex, ey)
                f = (r + g / cos_mitad) / r
                vs.append(bm.verts.new((ex * f, ey * f, z)))
            else:
                vs.append(bm.verts.new((cx + tx * ul + nx * g, cy + ty * ul + ny * g, z)))
        bm.faces.new(vs)
    obj = _objeto(nombre, bm)
    return _asignar(obj, color)


def placa(nombre, contorno, marco, color="#495432", capa=None):
    """Calcomanía sobre UNA cara (`marco_cara`). Para dibujos que cruzan aristas usa `calcomania`."""
    if capa is None:
        capa = _capas["n"]
        _capas["n"] += 1
    g = CALCO_GROSOR + CALCO_CAPA * capa
    if _area(contorno) < 0:
        contorno = contorno[::-1]
    fuera = max(abs(u) for u, _ in contorno) - marco["semiancho"]
    if fuera > 1e-3:
        print(f"[alth] aviso: {nombre} se sale {fuera:.2f} mm de su cara; usa calcomania()")
    cx, cy = marco["centro"]
    (nx, ny), (tx, ty) = marco["n"], marco["t"]
    bm = bmesh.new()
    bm.faces.new([bm.verts.new((cx + tx * u + nx * g, cy + ty * u + ny * g, z)) for u, z in contorno])
    obj = _objeto(nombre, bm)
    return _asignar(obj, color)


def hoja(nombre, largo=4.0, ancho=1.9, grosor=0.18, nervio=0.25, curva=0.5,
         estaciones=4, color="#7E9B7A", pos=(0, 0, 0), rot=(0, 0, 0)):
    """Hoja en forma de gota a lo largo de +X: base angosta, lo más ancho al 35 %, punta afilada.

    nervio: cuánto sube el nervio central (mm). curva: cuánto se arquea hacia abajo la punta (mm).
    rot: grados (x, y, z). La base de la hoja queda en `pos`.
    """
    bm = bmesh.new()
    ts = [i / (estaciones + 1) for i in range(1, estaciones + 1)]

    def ancho_en(t):  # perfil de gota: 0 en la base y la punta, máximo cerca del 35 %
        return ancho / 2 * math.sin(math.pi * t ** 0.62)

    def z_en(t):
        return -curva * t * t

    base = bm.verts.new((0, 0, 0))
    punta = bm.verts.new((largo, 0, z_en(1)))
    izq = [bm.verts.new((t * largo, ancho_en(t), z_en(t))) for t in ts]
    der = [bm.verts.new((t * largo, -ancho_en(t), z_en(t))) for t in ts]
    eje = [bm.verts.new((t * largo, 0, z_en(t) + nervio * (1 - t))) for t in ts]
    izq_b = [bm.verts.new((v.co.x, v.co.y, v.co.z - grosor)) for v in izq]
    der_b = [bm.verts.new((v.co.x, v.co.y, v.co.z - grosor)) for v in der]
    eje_b = [bm.verts.new((v.co.x, 0, z_en(t) - grosor)) for v, t in zip(eje, ts)]
    def cara(*vs):
        bm.faces.new(vs)

    # cara superior (con nervio) e inferior
    for lados, ejes in ((izq, eje), (der, eje), (izq_b, eje_b), (der_b, eje_b)):
        cara(base, lados[0], ejes[0])
        for i in range(estaciones - 1):
            cara(lados[i], lados[i + 1], ejes[i + 1], ejes[i])
        cara(lados[-1], punta, ejes[-1])
    # borde
    for lados, lados_b in ((izq, izq_b), (der, der_b)):
        cara(base, lados_b[0], lados[0])
        for i in range(estaciones - 1):
            cara(lados[i], lados_b[i], lados_b[i + 1], lados[i + 1])
        cara(lados[-1], lados_b[-1], punta)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto(nombre, bm)
    obj.location = pos
    obj.rotation_euler = tuple(math.radians(v) for v in rot)
    return _asignar(obj, color)


def caja(nombre, tam, pos=(0, 0, 0), color="#A8453B", biselar=True, apoyada=True):
    """Caja de W×D×H mm. Con apoyada=True la base queda sobre pos.z."""
    w, d, h = tam
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
    obj = _objeto(nombre, bm)
    obj.location = (pos[0], pos[1], pos[2] + (h / 2 if apoyada else 0))
    _asignar(obj, color)
    if biselar:
        chaflan(obj)
    return obj


# ---------------------------------------------------------------- luz y cámaras
def estudio(fuerza_sol=3.5, fuerza_relleno=0.85, direccion=None):
    """Luz ALTH: sol cálido arriba-izquierda-frente, relleno frío del mundo, piso con sombra."""
    esc = bpy.context.scene
    luz = SPEC["luz"]["principal"]
    sol = bpy.data.lights.new("Sol_ALTH", type="SUN")
    sol.energy = fuerza_sol
    sol.angle = math.radians(20)  # sombras suaves, como en las referencias
    sol.color = kelvin_a_rgb(luz["kelvin"])
    ob = bpy.data.objects.new("Sol_ALTH", sol)
    # Hacia dónde viaja la luz: desde arriba-izquierda-frente. Arriba pesa más que el frente,
    # para que lo que mira hacia arriba (coronas, cabello, hombros) quede un poco más claro.
    d = Vector(direccion or luz.get("direccion", (0.40, 0.50, -0.77))).normalized()
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    esc.collection.objects.link(ob)

    mundo = bpy.data.worlds.new("Mundo_ALTH")
    esc.world = mundo
    arbol = _nodos(mundo)
    fondo = next((n for n in arbol.nodes if n.type == "BACKGROUND"), None)
    if fondo is None:
        fondo = arbol.nodes.new("ShaderNodeBackground")
        salida = next((n for n in arbol.nodes if n.type == "OUTPUT_WORLD"), None) \
            or arbol.nodes.new("ShaderNodeOutputWorld")
        arbol.links.new(fondo.outputs["Background"], salida.inputs["Surface"])
    fondo.inputs["Color"].default_value = hex_a_lineal("#C8D5E7")
    fondo.inputs["Strength"].default_value = fuerza_relleno

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=2000)
    piso = _objeto("Piso_ALTH", bm, variacion=0)
    piso.is_shadow_catcher = True  # solo deja la sombra de contacto
    # Sin material, Blender pone un gris claro que rebota demasiado sol hacia el frente y los
    # costados: la tapa y el frente salían iguales. Un gris medio deja un rebote suave.
    _asignar(piso, "#A0A0A0", faceta=False)
    try:
        piso.visible_glossy = False
    except AttributeError:
        pass
    return sol


def _limites(objs):
    # Sin esto, matrix_world queda viejo tras mover objetos y el primer
    # encuadre sale corrido (el cubo de la fase 0 salía 10 mm arriba en "frente").
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def camara_orto(nombre, objs, direccion, margen=1.3):
    mn, mx = _limites(objs)
    centro, tam = (mn + mx) / 2, (mx - mn)
    radio = max(tam.length, 1.0)
    cam = bpy.data.cameras.new(nombre)
    cam.type = "ORTHO"
    cam.ortho_scale = radio * margen
    cam.clip_start, cam.clip_end = 0.1, radio * 40
    ob = bpy.data.objects.new(nombre, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = centro + direccion * radio * 10
    ob.rotation_euler = (centro - ob.location).to_track_quat("-Z", "Y").to_euler()
    return ob


# ---------------------------------------------------------------- maniquí de escala
def maniqui(arquetipo="estandar", pos=(0, 0, 0), color="#B7BABE"):
    """Maniquí de bloques con las cotas del cuerpo base (alth/cuerpo.py). Devuelve sus objetos.

    Úsalo como `extras` en `revisar` para ver un asset junto a un personaje y juzgar su escala.
    """
    from . import cuerpo as mq
    pl = mq.plan(arquetipo)
    ox, oy, oz = pos
    objs = []
    for p in pl["piezas"]:
        nombre = f"Maniqui_{arquetipo}_{p['nombre']}"
        x, y, z = p["pos"]
        x, y, z = x + ox, y + oy, z + oz
        col = "#3A2F2A" if p.get("oscuro") else color
        if p["tipo"] == "caja":
            o = caja(nombre, p["tam"], pos=(x, y, z), color=col, biselar=False)
            if p.get("chaflan"):
                chaflan(o, ancho=p["chaflan"], segmentos=2)
        elif p["tipo"] == "torno":
            o = torno(nombre, p["perfil"], segmentos=10, color=col, alternar=False, ruido_r=0, ruido_z=0,
                      ovalo=p["ovalo"], pos=(x, y, z))
        else:
            o = prisma(nombre, p["r0"], p["r1"], p["largo"], lados=p.get("lados", 6), color=col,
                       pos=(x, y, z), rot=p["rot"])
        objs.append(o)
    return objs


def junto_a_maniqui(objs, arquetipo="estandar", separacion=6.0, lado="izq"):
    """Coloca un maniquí al lado de `objs` (sin moverlos), con `separacion` mm entre ambos."""
    mn, mx = _limites(objs)
    ancho_maniqui = 50.0  # hombros (±15.5) + brazos en pose A + medio brazo: ±25 mm
    x = (mn.x - separacion - ancho_maniqui / 2) if lado == "izq" else (mx.x + separacion + ancho_maniqui / 2)
    return maniqui(arquetipo, pos=(x, (mn.y + mx.y) / 2, 0))


# ---------------------------------------------------------------- render y revisión
def _componer(png, destino_fondo=FONDO):
    """Pone el render transparente sobre el color de fondo exacto."""
    from PIL import Image
    img = Image.open(png).convert("RGBA")
    base = Image.new("RGBA", img.size, destino_fondo)
    base.alpha_composite(img)
    base.convert("RGB").save(png)


def hoja_contacto(pngs: dict, destino, titulo=""):
    from PIL import Image, ImageDraw
    imgs = {k: Image.open(v) for k, v in pngs.items()}
    px = next(iter(imgs.values())).width
    barra = 28
    hoja = Image.new("RGB", (px * 2, px * 2 + barra), FONDO)
    d = ImageDraw.Draw(hoja)
    d.text((10, 8), titulo, fill="#23242B")
    for i, (k, im) in enumerate(imgs.items()):
        x, y = (i % 2) * px, barra + (i // 2) * px
        hoja.paste(im.convert("RGB"), (x, y))
        d.text((x + 8, y + 6), k, fill="#595B66")
    hoja.save(destino)
    return destino


def medidas(objs):
    """Medidas reales en mm (caja envolvente en mundo) para comparar con la spec."""
    out = {}
    for o in objs:
        if o.type != "MESH":
            continue
        mn, mx = _limites([o])
        d = mx - mn
        tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
        out[o.name] = {"W": round(d.x, 2), "D": round(d.y, 2), "H": round(d.z, 2),
                       "z_min": round(mn.z, 2), "tris_sin_modificadores": tris}
    return out


def verificar(objs, asset):
    """Chequeos objetivos del asset (ver alth/verificacion.py). `asset`: ruta a spec.json o dict."""
    from . import verificacion as v
    datos = v.recolectar(objs, COLORES_USADOS)
    return v.evaluar(datos, SPEC, v.cargar_asset(asset))


def revisar(objs, carpeta, modo="iteracion", vistas=None, titulo="", asset=None, extras=()):
    """Renderiza las vistas, compone el fondo y arma la hoja de contacto.

    Con `asset` (ruta a assets/<nombre>/spec.json) también corre la verificación automática
    y la imprime. `extras` (p. ej. un maniquí de escala) entran en el encuadre y el render, pero no en
    las medidas ni en la verificación. Devuelve un dict con rutas, tiempos, medidas y verificación;
    también lo guarda como reporte.json.
    """
    esc = bpy.context.scene
    cfg = MODOS[modo]
    esc.cycles.samples = cfg["muestras"]
    esc.render.resolution_x = esc.render.resolution_y = cfg["px"]
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    pngs, tiempos = {}, {}
    for nombre in (vistas or list(VISTAS)):
        cam = camara_orto(f"Cam_{nombre}", list(objs) + list(extras), VISTAS[nombre])
        esc.camera = cam
        ruta = carpeta / f"{nombre}.png"
        esc.render.filepath = str(ruta)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        tiempos[nombre] = round(time.time() - t0, 1)
        _componer(ruta)
        pngs[nombre] = ruta
    hoja = hoja_contacto(pngs, carpeta / "hoja.png", titulo or carpeta.name)
    reporte = {
        "blender": bpy.app.version_string, "modo": modo, "px": cfg["px"],
        "muestras": cfg["muestras"], "segundos_por_vista": tiempos,
        "segundos_total": round(sum(tiempos.values()), 1),
        "hoja": str(hoja), "vistas": {k: str(v) for k, v in pngs.items()},
        "medidas_mm": medidas(objs),
    }
    if asset is not None:
        from . import verificacion as v
        try:
            reporte["verificacion"] = verificar(objs, asset)
            print(v.resumen(reporte["verificacion"]))
        except Exception as e:  # noqa: BLE001 — un fallo del verificador no debe tirar el render
            reporte["verificacion"] = {"ok": False, "checks": [], "error": repr(e)}
            print(f"[alth] la verificación falló: {e!r}")
    (carpeta / "reporte.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    return reporte


# ---------------------------------------------------------------- exportar
def exportar_glb(objs, ruta, escala=None, blend=True):
    """Exporta a GLB para Godot con la raíz escalada (spec: ×0.01 → 1 mm = 1 cm)."""
    escala = SPEC["unidades"]["export_godot"]["escala_raiz"] if escala is None else escala
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(ruta.with_suffix(".blend")))
    raiz = bpy.data.objects.new("ALTH_raiz", None)
    bpy.context.scene.collection.objects.link(raiz)
    for o in objs:
        mw = o.matrix_world.copy()
        o.parent = raiz
        o.matrix_world = mw
    raiz.scale = (escala,) * 3
    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:
        o.select_set(o in objs or o is raiz)
    bpy.context.view_layer.objects.active = raiz
    bpy.ops.export_scene.gltf(filepath=str(ruta), export_format="GLB",
                              use_selection=True, export_apply=True)
    return str(ruta)
