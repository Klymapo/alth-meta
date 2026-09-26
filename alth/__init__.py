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


def material(nombre: str, color: str, rugosidad=None, metalico=0.0, faceta=False):
    m = SPEC["material"]
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
          ovalo=(1.0, 1.0), semilla=7, pos=(0, 0, 0)):
    """Sólido de revolución facetado: frutas, latas, vasos, tazas, jarrones, cabezas de bastón…

    perfil: lista de (radio_mm, z_mm) de abajo hacia arriba.
    alternar: gira medio segmento cada anillo → facetas triangulares (look low-poly).
    ruido_r / ruido_z: irregularidad (fracción del radio / mm) en los anillos intermedios.
    centro_abajo / centro_arriba: z del vértice que cierra cada tapa. Por debajo del último
      anillo hace una cuenca (hundido del tallo); None cierra al nivel del anillo.
    ovalo: escala (x, y) para secciones no circulares.
    """
    rnd = random.Random(semilla)
    bm = bmesh.new()
    anillos = []
    n = len(perfil)
    for i, (r, z) in enumerate(perfil):
        des = (i % 2) * math.pi / segmentos if alternar else 0
        medio = 0 < i < n - 1
        anillo = []
        for s in range(segmentos):
            a = 2 * math.pi * s / segmentos + des
            j = 1 + (rnd.uniform(-ruido_r, ruido_r) if medio else 0)
            zz = z + (rnd.uniform(-ruido_z, ruido_z) if medio else 0)
            anillo.append(bm.verts.new((r * j * math.cos(a) * ovalo[0], r * j * math.sin(a) * ovalo[1], zz)))
        anillos.append(anillo)
    abajo = bm.verts.new((0, 0, perfil[0][1] if centro_abajo is None else centro_abajo))
    arriba = bm.verts.new((0, 0, perfil[-1][1] if centro_arriba is None else centro_arriba))
    for s in range(segmentos):
        k = (s + 1) % segmentos
        bm.faces.new((abajo, anillos[0][k], anillos[0][s]))
        bm.faces.new((arriba, anillos[-1][s], anillos[-1][k]))
    for i in range(n - 1):
        a, b = anillos[i], anillos[i + 1]
        for s in range(segmentos):
            k = (s + 1) % segmentos
            if not alternar:
                bm.faces.new((a[s], a[k], b[k], b[s]))
            elif i % 2 == 0:
                bm.faces.new((a[s], a[k], b[s]))
                bm.faces.new((a[k], b[k], b[s]))
            else:
                bm.faces.new((a[s], b[k], b[s]))
                bm.faces.new((a[s], a[k], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _objeto(nombre, bm, semilla=semilla)
    obj.location = pos
    return _asignar(obj, color)


def prisma(nombre, radio_base, radio_punta, largo, lados=5, color="#69472D", pos=(0, 0, 0), rot=(0, 0, 0)):
    """Prisma cónico a lo largo de +Z: tallos, patas, mangos, velas, dedos simples."""
    perfil = [(radio_base, 0.0), (radio_punta, largo)]
    obj = torno(nombre, perfil, segmentos=lados, color=color, alternar=False, ruido_r=0, ruido_z=0)
    obj.location = pos
    obj.rotation_euler = tuple(math.radians(v) for v in rot)
    return obj


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


def revisar(objs, carpeta, modo="iteracion", vistas=None, titulo=""):
    """Renderiza las vistas, compone el fondo y arma la hoja de contacto.

    Devuelve un dict con rutas, tiempos y medidas; también lo guarda como reporte.json.
    """
    esc = bpy.context.scene
    cfg = MODOS[modo]
    esc.cycles.samples = cfg["muestras"]
    esc.render.resolution_x = esc.render.resolution_y = cfg["px"]
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    pngs, tiempos = {}, {}
    for nombre in (vistas or list(VISTAS)):
        cam = camara_orto(f"Cam_{nombre}", objs, VISTAS[nombre])
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
