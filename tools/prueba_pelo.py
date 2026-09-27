"""Prueba de alth/pelo.py (segundo enfoque: corona + cuñas en UNA malla), solo sobre la cabeza
del joven rubio. Herramienta aparte del ciclo de joven_rubio (no toca assets/joven_rubio/, no
cuenta para su presupuesto de vueltas).

    alth-python tools/prueba_pelo.py

Salida: renders/pelo_prueba/hoja.png (frente, lateral, espalda, 3/4).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bpy  # noqa: E402
import alth  # noqa: E402
from alth import pelo, personaje  # noqa: E402

alth.nueva_escena()
PIEL = "#FBC39C"
RUBIO_ARENA = alth.SPEC["paleta"]["medidos"]["rubio_arena"]  # ya registrado en la paleta

pl = personaje.plan("estandar")
cabeza_pieza = pl["piezas"]["cabeza"]
cuerpo = personaje.construir("estandar", color_piel=PIEL)
CONSERVAR = {"cabeza", "oreja_izq", "oreja_der", "nariz"}
for nombre, o in cuerpo.items():
    if nombre not in CONSERVAR:
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(me)
objs = [cuerpo["cabeza"], cuerpo["oreja_izq"], cuerpo["oreja_der"], cuerpo["nariz"]]

pelo_obj = pelo.construir_pelo(cabeza_pieza, escala=1.3, cunias=10, color=RUBIO_ARENA)
objs.append(pelo_obj)

alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "pelo_prueba", modo="iteracion",
                    titulo="prueba de pelo v2 (corona + cuñas) · sobre joven_rubio")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
