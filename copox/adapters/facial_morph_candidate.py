from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

DEFAULT_REGIONS={
    "blink_left": [0.34,0.00,0.72,0.49,0.42,0.87],
    "blink_right":[0.51,0.00,0.72,0.66,0.42,0.87],
    "mouth_open": [0.40,0.00,0.58,0.60,0.42,0.74],
}


def _selected_indices(obj, box):
    corners=[Vector(v) for v in obj.bound_box]
    lo=Vector((min(v.x for v in corners),min(v.y for v in corners),min(v.z for v in corners)))
    hi=Vector((max(v.x for v in corners),max(v.y for v in corners),max(v.z for v in corners)))
    span=Vector((max(hi.x-lo.x,1e-9),max(hi.y-lo.y,1e-9),max(hi.z-lo.z,1e-9)))
    selected=[]
    for v in obj.data.vertices:
        n=Vector(((v.co.x-lo.x)/span.x,(v.co.y-lo.y)/span.y,(v.co.z-lo.z)/span.z))
        if box[0]<=n.x<=box[3] and box[1]<=n.y<=box[4] and box[2]<=n.z<=box[5]:
            selected.append(v.index)
    return selected,span


def main()->int:
    p=argparse.ArgumentParser(description='Morph targets faciales learning-only')
    p.add_argument('--input',required=True); p.add_argument('--output',required=True); p.add_argument('--report',required=True)
    args=p.parse_args()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if not meshes: raise RuntimeError('GLB sin mallas')
    obj=max(meshes,key=lambda o:len(o.data.vertices))
    rest=[v.co.copy() for v in obj.data.vertices]
    if obj.data.shape_keys is not None:
        # Alpha no debería traer morphs; si los trae, preservarlos y añadir nuevos con nombres COPOX.
        basis=obj.data.shape_keys.key_blocks[0]
    else:
        basis=obj.shape_key_add(name='Basis',from_mix=False)

    details={}
    for name,box in DEFAULT_REGIONS.items():
        indices,span=_selected_indices(obj,box)
        if not indices: raise RuntimeError(f'{name} no seleccionó vértices')
        key=obj.shape_key_add(name=name,from_mix=False)
        center_z=sum(rest[i].z for i in indices)/len(indices)
        max_delta=0.0
        for i in indices:
            src=rest[i]
            dst=key.data[i].co
            if name.startswith('blink'):
                # comprime verticalmente hacia el centro de la zona; amplitud pequeña y reversible
                target_z=center_z+(src.z-center_z)*0.72
                dst.z=target_z
            else:
                # boca: abre levemente hacia abajo y hacia el frente local
                dst.z=src.z-span.z*0.008
                dst.y=src.y-span.y*0.004
            max_delta=max(max_delta,(dst-src).length)
        details[name]={"selected_vertices":len(indices),"max_delta":max_delta,"box_normalized":box}

    rest_unchanged=all((v.co-old).length<=1e-12 for v,old in zip(obj.data.vertices,rest))
    out=Path(args.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',export_morph=True,export_morph_normal=True)
    report={
        "mode":"facial_morph_candidate_learning_only","object":obj.name,"controls":details,
        "rest_vertices_unchanged":bool(rest_unchanged),"control_count":len(details),
        "all_controls_move_vertices":all(v['selected_vertices']>0 and v['max_delta']>0 for v in details.values()),
        "promotion_allowed":False,
        "learning":{"visual_semantic_validated":False,"next":"Renderizar cada morph y ajustar cajas/amplitud contra ojos y boca de la referencia antes de aprobar controles finales."}
    }
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False)); return 0

if __name__=='__main__': raise SystemExit(main())
