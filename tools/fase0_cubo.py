"""Fase 0 · Prueba de punta a punta del pipeline ALTH-META.

    alth-python tools/fase0_cubo.py            # render de iteración (rápido)
    alth-python tools/fase0_cubo.py --final    # render final

Crea un cubo de 20 mm con chaflán, lo ilumina con el estudio ALTH,
renderiza 4 vistas + hoja de contacto y exporta GLB para Godot.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import alth  # noqa: E402

t0 = time.time()
modo = "final" if "--final" in sys.argv else "iteracion"
alth.nueva_escena()
cubo = alth.caja("cubo", (20, 20, 20), color="#A8453B")
alth.estudio()
rep = alth.revisar([cubo], f"renders/fase0/{modo}", modo=modo, titulo=f"Fase 0 · cubo 20 mm · {modo}")
glb = alth.exportar_glb([cubo], "exports/fase0/cubo.glb")
rep["glb"] = glb
rep["segundos_script"] = round(time.time() - t0, 1)
print(json.dumps(rep, indent=2, ensure_ascii=False))
