"""Foto de familia: todos los assets aprobados junto al maniquí, para juzgar su escala.

    alth-python tools/escala.py                 # maniquí estándar, render de iteración
    alth-python tools/escala.py final alta      # render final, con el arquetipo alto

Importa cada assets/<nombre>/<nombre>.glb, lo pone en fila sobre el piso a la derecha del maniquí
y una copia de la taza a la altura de su mano. Salida: renders/escala/<modo>/hoja.png.
Si un objeto se siente chico o grande junto al personaje, esa corrección es la que recalibra k.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bpy  # noqa: E402
import alth  # noqa: E402
from alth import cuerpo as mq  # noqa: E402

args = sys.argv[1:]
MODO = next((a for a in args if a in alth.MODOS), "iteracion")
ARQ = next((a for a in args if a in mq.ARQUETIPOS), "estandar")
EN_MANO = "taza"


def importar(glb, esperado_mm=None):
    """Trae un GLB de vuelta a la escena en mm.

    El importador de Blender convierte los metros del GLB según la unidad de la escena (1 BU = 1 mm
    → ×1000). Por eso se importa con la escena temporalmente en metros y luego se quita el ×0.01 que
    la raíz trae para Godot: así la malla vuelve a sus mm originales.
    """
    us = bpy.context.scene.unit_settings
    previo = us.scale_length
    us.scale_length = 1.0
    antes = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=str(glb))
    finally:
        us.scale_length = previo
    nuevos = [o for o in bpy.data.objects if o not in antes]
    raices = [o for o in nuevos if o.parent is None]
    for r in raices:
        r.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    mallas = [o for o in nuevos if o.type == "MESH"]
    mn, mx = alth._limites(mallas)
    alto = mx.z - mn.z
    # Red de seguridad para errores de unidades (×10, ×1000…), no para diferencias de forma:
    # el alto total incluye hojas, tapas o asas, así que solo actúa si está 3× o más fuera.
    if esperado_mm and not (esperado_mm / 3 <= alto <= esperado_mm * 3):
        import math
        f = 10 ** round(math.log10(esperado_mm / alto))
        print(f"[escala] aviso: {glb.parent.name} medía {alto:.2f} mm de alto; lo ajusto ×{f:g} (error de unidades)")
        for r in raices:
            r.scale = tuple(v * f for v in r.scale)
        bpy.context.view_layer.update()
    return raices, mallas


def alto_esperado(nombre):
    """Alto (H) del cuerpo principal según las cotas del spec del asset, si existe."""
    import json
    try:
        spec = json.loads((alth.RAIZ / "assets" / nombre / "spec.json").read_text(encoding="utf-8"))
        return max(c["mm"] for c in spec.get("cotas", []) if c["eje"] == "H")
    except (OSError, ValueError, KeyError):
        return None


def mover(raices, mallas, x_min=None, centro_x=None, y_centro=0.0, z_min=0.0):
    mn, mx = alth._limites(mallas)
    dx = (x_min - mn.x) if x_min is not None else (centro_x - (mn.x + mx.x) / 2)
    dy = y_centro - (mn.y + mx.y) / 2
    dz = z_min - mn.z
    for r in raices:
        r.location = (r.location.x + dx, r.location.y + dy, r.location.z + dz)
    bpy.context.view_layer.update()
    return alth._limites(mallas)


alth.nueva_escena()
figura = alth.maniqui(ARQ)
anclas = mq.plan(ARQ)["anclas"]
glbs = sorted(p for p in (alth.RAIZ / "assets").glob("*/*.glb"))
cursor = 32.0  # a la derecha del maniquí
todos = []
for glb in glbs:
    raices, mallas = importar(glb, alto_esperado(glb.parent.name))
    mn, mx = mover(raices, mallas, x_min=cursor)
    cursor = mx.x + 4.0
    todos += mallas
    print(f"{glb.parent.name}: {mx.x - mn.x:.1f} × {mx.y - mn.y:.1f} × {mx.z - mn.z:.1f} mm")

en_mano = alth.RAIZ / "assets" / EN_MANO / f"{EN_MANO}.glb"
if en_mano.exists():
    raices, mallas = importar(en_mano, alto_esperado(EN_MANO))
    # junto a la mano derecha, con la base a la altura de la punta de la mano
    mover(raices, mallas, centro_x=mq.HOMBRO_X + 12.0, y_centro=-4.0, z_min=anclas["punta_mano"])
    todos += mallas

alth.estudio()
# Solo frente y 3/4: con todo en fila sobre X, la lateral y la espalda no aportan.
rep = alth.revisar(todos, alth.RAIZ / "renders" / "escala" / MODO, modo=MODO, extras=figura,
                   vistas=["frente", "tres_cuartos"],
                   titulo=f"escala · maniquí {ARQ} ({anclas['altura']:.0f} mm) · {MODO}")
print(rep["hoja"])
