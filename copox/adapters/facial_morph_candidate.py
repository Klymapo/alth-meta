from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

DEFAULT_REGIONS={
    "blink_left": [0.34,0.00,0.72,0.49,0.42,0.87],
    "blink_right":[0.51,0.00,0.72,0.66,0.42,0.87],
    "mouth_open": [0.40,0.00,0.58,0.60,0.42,0.74],
}


def _canonical_frame(obj):
    rotation=Matrix.Rotation(math.radians(-90.0),4,'X')
    to_can=rotation @ obj.matrix_world
    from_can=to_can.inverted()
    pts=[to_can @ v.co for v in obj.data.vertices]
    lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
    hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
    span=Vector((max(hi.x-lo.x,1e-9),max(hi.y-lo.y,1e-9),max(hi.z-lo.z,1e-9)))
    return to_can,from_can,lo,span


def _selected_indices(obj,box,to_can,lo,span):
    selected=[]
    for v in obj.data.vertices:
        p=to_can @ v.co
        n=Vector(((p.x-lo.x)/span.x,(p.y-lo.y)/span.y,(p.z-lo.z)/span.z))
        if box[0]<=n.x<=box[3] and box[1]<=n.y<=box[4] and box[2]<=n.z<=box[5]:
            selected.append(v.index)
    return selected


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
    to_can,from_can,lo,span=_canonical_frame(obj)
    if obj.data.shape_keys is None:
        obj.shape_key_add(name='Basis',from_mix=False)

    details={}
    for name,box in DEFAULT_REGIONS.items():
        indices=_selected_indices(obj,box,to_can,lo,span)
        if not indices: raise RuntimeError(f'{name} no seleccionó vértices en coordenadas canónicas')
        key=obj.shape_key_add(name=name,from_mix=False)
        canonical=[to_can @ rest[i] for i in indices]
        center_z=sum(p.z for p in canonical)/len(canonical)
        max_delta=0.0
        for i,src_can in zip(indices,canonical):
            target=src_can.copy()
            if name.startswith('blink'):
                target.z=center_z+(src_can.z-center_z)*0.72
            else:
                # abre la boca un poco hacia abajo y profundidad frontal, siempre en marco canónico.
                target.z=src_can.z-span.z*0.008
                target.y=src_can.y-span.y*0.004
            target_local=from_can @ target
            key.data[i].co=target_local
            max_delta=max(max_delta,(target_local-rest[i]).length)
        details[name]={
            'selected_vertices':len(indices),'max_delta':max_delta,'box_normalized':box,
            'selection_coordinates':'canonical_z_up'
        }

    rest_unchanged=all((v.co-old).length<=1e-12 for v,old in zip(obj.data.vertices,rest))
    out=Path(args.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',export_morph=True,export_morph_normal=True)
    report={
        'mode':'facial_morph_candidate_learning_only','object':obj.name,'controls':details,
        'rest_vertices_unchanged':bool(rest_unchanged),'control_count':len(details),
        'all_controls_move_vertices':all(v['selected_vertices']>0 and v['max_delta']>0 for v in details.values()),
        'promotion_allowed':False,
        'learning':{'visual_semantic_validated':False,'next':'Renderizar cada morph y ajustar cajas/amplitud contra ojos y boca de la referencia antes de aprobar controles finales.'}
    }
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False)); return 0

if __name__=='__main__': raise SystemExit(main())
