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


def importar(glb):
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    nuevos = [o for o in bpy.data.objects if o not in antes]
    raices = [o for o in nuevos if o.parent is None]
    for r in raices:
        r.scale = (1, 1, 1)  # el GLB trae la raíz ×0.01 para Godot; aquí trabajamos en mm
    bpy.context.view_layer.update()
    mallas = [o for o in nuevos if o.type == "MESH"]
    mn, mx = alth._limites(mallas)
    if (mx - mn).length < 1.0:  # GLB sin raíz escalable: lo llevamos a mm a mano
        for r in raices:
            r.scale = (100, 100, 100)
        bpy.context.view_layer.update()
    return raices, mallas


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
    raices, mallas = importar(glb)
    mn, mx = mover(raices, mallas, x_min=cursor)
    cursor = mx.x + 4.0
    todos += mallas
    print(f"{glb.parent.name}: {mx.x - mn.x:.1f} × {mx.y - mn.y:.1f} × {mx.z - mn.z:.1f} mm")

en_mano = alth.RAIZ / "assets" / EN_MANO / f"{EN_MANO}.glb"
if en_mano.exists():
    raices, mallas = importar(en_mano)
    # junto a la mano derecha, con la base a la altura de la punta de la mano
    mover(raices, mallas, centro_x=mq.HOMBRO_X + 12.0, y_centro=-4.0, z_min=anclas["punta_mano"])
    todos += mallas

alth.estudio()
rep = alth.revisar(todos, alth.RAIZ / "renders" / "escala" / MODO, modo=MODO, extras=figura,
                   titulo=f"escala · maniquí {ARQ} ({anclas['altura']:.0f} mm) · {MODO}")
print(rep["hoja"])
