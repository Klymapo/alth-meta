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


def material(nombre: str, color: str, rugosidad=None, metalico=0.0):
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
    bsdf.inputs["Roughness"].default_value = m["rugosidad"] if rugosidad is None else rugosidad
    bsdf.inputs["Metallic"].default_value = metalico
    for clave in ("Specular IOR Level", "Specular"):
        if clave in bsdf.inputs:
            bsdf.inputs[clave].default_value = m["especular"]
            break
    mat.diffuse_color = hex_a_lineal(color)
    return mat


def _objeto(nombre, bm):
    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False  # sombreado plano: las facetas se ven
    obj = bpy.data.objects.new(nombre, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def chaflan(obj, ancho=None, segmentos=None):
    g = SPEC["geometria"]
    mod = obj.modifiers.new("Chaflan", "BEVEL")
    mod.width = g["chaflan_mm"] if ancho is None else ancho
    mod.segments = g["chaflan_segmentos"] if segmentos is None else segmentos
    mod.limit_method = "ANGLE"
    return mod


def caja(nombre, tam, pos=(0, 0, 0), color="#A8453B", biselar=True, apoyada=True):
    """Caja de W×D×H mm. Con apoyada=True la base queda sobre pos.z."""
    w, d, h = tam
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
    obj = _objeto(nombre, bm)
    obj.location = (pos[0], pos[1], pos[2] + (h / 2 if apoyada else 0))
    obj.data.materials.append(material(f"M_{nombre}", color))
    if biselar:
        chaflan(obj)
    return obj


# ---------------------------------------------------------------- luz y cámaras
def estudio(fuerza_sol=3.0, fuerza_relleno=0.7):
    """Luz ALTH: sol cálido arriba-izquierda-frente, relleno frío del mundo, piso con sombra."""
    esc = bpy.context.scene
    luz = SPEC["luz"]["principal"]
    sol = bpy.data.lights.new("Sol_ALTH", type="SUN")
    sol.energy = fuerza_sol
    sol.angle = math.radians(20)  # sombras suaves, como en las referencias
    sol.color = kelvin_a_rgb(luz["kelvin"])
    ob = bpy.data.objects.new("Sol_ALTH", sol)
    ob.rotation_euler = (math.radians(50), math.radians(-28), math.radians(-35))
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
    piso = _objeto("Piso_ALTH", bm)
    piso.is_shadow_catcher = True  # solo deja la sombra de contacto
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
