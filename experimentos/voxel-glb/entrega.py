#!/usr/bin/env python3
"""Genera modelo, 4 capturas y manifiesto en una entrega."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser(description='Entrega GLB con capturas obligatorias')
    ap.add_argument('--lado',type=float,default=1)
    ap.add_argument('--color',default='#5089C6')
    ap.add_argument('--salida',default='salidas/entrega_001')
    a=ap.parse_args()
    out=Path(a.salida).resolve()
    out.mkdir(parents=True,exist_ok=True)
    model=out/'cubo.glb'
    subprocess.run([sys.executable,str(HERE/'generar_cubo.py'),'--lado',str(a.lado),'--color',a.color,'--salida',str(model)],check=True)
    subprocess.run([sys.executable,str(HERE/'render_glb.py'),str(model),'--salida',str(out/'capturas')],check=True)
    manifest={
        'fecha_utc':datetime.now(timezone.utc).isoformat(),
        'modelo':'cubo.glb',
        'sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
        'lado':a.lado,
        'color':a.color,
        'capturas':['capturas/cubo_frente.png','capturas/cubo_derecha.png',
                    'capturas/cubo_superior.png','capturas/cubo_isometrica.png',
                    'capturas/cubo_4_vistas.png']}
    (out/'manifiesto.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Entrega completa:',out)

if __name__=='__main__':
    main()
