"""Prueba de alth/pelo.py: casco + mechones gruesos, solo sobre la cabeza del joven rubio.

Herramienta aparte del ciclo de joven_rubio (no toca assets/joven_rubio/, no cuenta para su
presupuesto de vueltas). Sirve para ajustar escala/cantidad/largo/caída antes de llevarlo al
personaje completo.

    alth-python tools/prueba_pelo.py

Salida: renders/pelo_prueba/hoja.png (frente, lateral, espalda, 3/4).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bpy  # noqa: E402
import alth  # noqa: E402
from alth import pelo, personaje  # noqa: E402

PIEL = "#FBC39C"
RUBIO_ARENA = "#C9B89F"  # crema_suave (paleta existente): el más cercano a "rubio arena menos
                          # saturado" que pidió la tarea; ver propuesta de color en el reporte.

alth.nueva_escena()

pl = personaje.plan("estandar")
cabeza_pieza = pl["piezas"]["cabeza"]
cuerpo = personaje.construir("estandar", color_piel=PIEL)
CONSERVAR = {"cabeza", "oreja_izq", "oreja_der", "nariz"}
for nombre, o in cuerpo.items():
    if nombre not in CONSERVAR:
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(me)
cabeza_obj = cuerpo["cabeza"]
objs = [cabeza_obj, cuerpo["oreja_izq"], cuerpo["oreja_der"], cuerpo["nariz"]]

casco = pelo.construir_casco(cabeza_pieza, escala=1.3, color=RUBIO_ARENA)
objs.append(casco)

casco_plan = pelo.plan_casco(cabeza_pieza, escala=1.3)
mechones = pelo.plan_mechones(casco_plan, cabeza_pieza, cantidad=22, largo=(9.0, 16.0),
                               ancho=(3.5, 6.5), caida=(0.5, 5.0), semilla=3)
objs += pelo.construir_mechones(mechones, color=RUBIO_ARENA)

marco = pelo.mechones_marco_cara(cabeza_pieza, largo=17.0, ancho=4.2, caida=9.0)
objs += pelo.construir_mechones(marco, color=RUBIO_ARENA, prefijo="Pelo_marco")

alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "pelo_prueba", modo="iteracion",
                    titulo="prueba de pelo (alth/pelo.py) · sobre joven_rubio")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
