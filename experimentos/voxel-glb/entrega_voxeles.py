#!/usr/bin/env python3
"""Genera la entrega 002: GLB multicolor + cinco PNG + hash de verificación."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from generar_voxeles import COLORS,default_voxels,read_layout,glb_from_voxels

BASE=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--layout",help="JSON con coordenadas específicas")
    p.add_argument("--salida",default="salidas/entrega_002")
    args=p.parse_args()
    voxels=read_layout(args.layout) if args.layout else default_voxels()
    binary,stats=glb_from_voxels(voxels)
    out=Path(args.salida).resolve();out.mkdir(parents=True,exist_ok=True)
    model=out/"estructura_voxel.glb";model.write_bytes(binary)
    subprocess.run([sys.executable,str(BASE/"render_voxeles.py"),str(model),
       "--salida",str(out/"capturas")],check=True)
    captures=[f"capturas/voxeles_{v}.png" for v in
      ("frente","derecha","superior","isometrica","4_vistas")]
    if not all((out/p).is_file() and (out/p).stat().st_size>0 for p in captures):
        raise RuntimeError("No hay cuatro capturas y lámina; entrega rechazada")
    manifest={
      "fecha_utc":datetime.now(timezone.utc).isoformat(),
      "modelo":model.name,
      "sha256":hashlib.sha256(binary).hexdigest(),
      "layout":args.layout or "predeterminado 9+4+1",
      "coordenadas":[{"x":x,"y":y,"z":z,"color":c}
                      for (x,y,z),c in sorted(voxels.items())],
      "materiales":COLORS,
      "estadisticas":stats,
      "capturas":captures,
      "nota":"Verdes x,z=1,2 sobre base x,z=0..2: celdas enteras contiguas (2x2 no se centra exactamente en 3x3)."
    }
    (out/"manifiesto.json").write_text(
      json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("ENTREGA 002:",out, json.dumps(stats,ensure_ascii=False))

if __name__=="__main__":
    main()
