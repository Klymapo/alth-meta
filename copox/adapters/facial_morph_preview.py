from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402
import alth  # noqa: E402


def main()->int:
    p=argparse.ArgumentParser(description='Preview ALTH de un morph target facial')
    p.add_argument('--input',required=True); p.add_argument('--control',required=True)
    p.add_argument('--output-dir',required=True)
    args=p.parse_args()

    alth.nueva_escena()
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    imported=list(bpy.context.scene.objects)
    roots=[o for o in imported if o.parent is None]
    rotation=Matrix.Rotation(math.radians(-90.0),4,'X')
    for root in roots: root.matrix_world=rotation @ root.matrix_world
    bpy.context.view_layer.update()

    target_obj=None
    controls=[]
    for obj in imported:
        if obj.type!='MESH' or obj.data.shape_keys is None: continue
        names=[k.name for k in obj.data.shape_keys.key_blocks if k.name!='Basis']
        controls.extend(names)
        if args.control in names: target_obj=obj
    if target_obj is None:
        raise RuntimeError(f'Morph {args.control} no encontrado; disponibles={sorted(set(controls))}')
    for key in target_obj.data.shape_keys.key_blocks:
        if key.name!='Basis': key.value=1.0 if key.name==args.control else 0.0
    bpy.context.view_layer.update()

    objs=[o for o in imported if o.type=='MESH']
    alth.estudio()
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    report=alth.revisar(objs,out,modo='iteracion',titulo=f'COPOX · facial {args.control}',asset=None)
    report['facial_preview']={'control':args.control,'object':target_obj.name,'available_controls':sorted(set(controls)),'value':1.0}
    (out/'reporte.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0

if __name__=='__main__': raise SystemExit(main())
