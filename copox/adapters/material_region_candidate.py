from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402


def _bbox_world(obj):
    pts=[obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
    hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
    return lo,hi


def main()->int:
    p=argparse.ArgumentParser(description='Candidato material regional, learning-only')
    p.add_argument('--input',required=True); p.add_argument('--params',required=True)
    p.add_argument('--output',required=True); p.add_argument('--report',required=True)
    args=p.parse_args()
    params=json.loads(Path(args.params).read_text(encoding='utf-8'))
    color=[float(x) for x in params['color_rgb']]
    if max(color)>1.0: color=[x/255.0 for x in color]
    if len(color)!=3: raise ValueError('color_rgb requiere tres valores')
    source_nodes=[str(x) for x in params.get('source_nodes',['Oreja_derecha_perfil','Oreja_izquierda_perfil'])]
    padding=float(params.get('padding_ratio',0.60))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if not meshes: raise RuntimeError('GLB sin mallas')
    body=max(meshes,key=lambda o:len(o.data.polygons))
    node_map={o.name:o for o in meshes}
    missing=[n for n in source_nodes if n not in node_map]
    if missing: raise RuntimeError(f'Nodos fuente ausentes: {missing}')

    regions=[]
    for name in source_nodes:
        lo,hi=_bbox_world(node_map[name]); pad=(hi-lo)*padding
        regions.append((lo-pad,hi+pad))

    before_coords=[v.co.copy() for v in body.data.vertices]
    before_bounds=[Vector(v) for v in body.bound_box]
    before_slots=len(body.data.materials)
    before_indices=[p.material_index for p in body.data.polygons]

    material=bpy.data.materials.new(name='COPOX_RegionMaterial')
    material.use_nodes=True
    bsdf=material.node_tree.nodes.get('Principled BSDF')
    if bsdf is None: raise RuntimeError('No se creó Principled BSDF')
    bsdf.inputs['Base Color'].default_value=(*color,1.0)
    bsdf.inputs['Roughness'].default_value=float(params.get('roughness',0.72))
    body.data.materials.append(material)
    new_index=len(body.data.materials)-1

    selected=[]
    for poly in body.data.polygons:
        center_world=body.matrix_world @ poly.center
        if any(all(lo[i] <= center_world[i] <= hi[i] for i in range(3)) for lo,hi in regions):
            poly.material_index=new_index; selected.append(poly.index)
    if not selected: raise RuntimeError('La región material no seleccionó polígonos de la malla principal')

    geometry_unchanged=all((v.co-old).length<=1e-12 for v,old in zip(body.data.vertices,before_coords))
    after_bounds=[Vector(v) for v in body.bound_box]
    bounds_delta=max((a-b).length for a,b in zip(before_bounds,after_bounds))
    changed_polygons=[i for i,p in enumerate(body.data.polygons) if p.material_index != before_indices[i]]
    scope_exact=bool(set(changed_polygons)==set(selected))

    out=Path(args.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB')
    report={
        'mode':'material_region_candidate_learning_only','body_object':body.name,'source_nodes':source_nodes,
        'selected_polygons':len(selected),'selected_polygon_indices':selected[:1000],
        'material_slots_before':before_slots,'material_slots_after':len(body.data.materials),
        'target_color_rgb_01':color,'geometry_unchanged':bool(geometry_unchanged),'bounds_delta':float(bounds_delta),
        'scope_exact':scope_exact,'promotion_allowed':False,
        'learning':{'reason':'El color objetivo procede del diagnóstico UV/material, no de una paleta inventada. Evaluar visualmente si recolorear la zona embebida elimina la falsa lectura pelo/oreja antes de persistir.'}
    }
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False)); return 0

if __name__=='__main__': raise SystemExit(main())
