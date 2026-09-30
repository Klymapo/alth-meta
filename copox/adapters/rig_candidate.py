from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

import bpy  # noqa: E402
from mathutils import Vector, Euler  # noqa: E402

HAIR_TOKENS=("fleco","mechon","capa_","corona","oreja")


def _arm_points(meshes, arm_matrix):
    inv=arm_matrix.inverted()
    pts=[]
    for obj in meshes:
        for v in obj.data.vertices:
            pts.append(inv @ obj.matrix_world @ v.co)
    lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
    hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
    span=Vector((max(hi.x-lo.x,1e-9),max(hi.y-lo.y,1e-9),max(hi.z-lo.z,1e-9)))
    return lo,hi,span


def _P(lo,span,x,y,z):
    return Vector((lo.x+x*span.x,lo.y+y*span.y,lo.z+z*span.z))


def _add_bone(arm,name,head,tail,parent=None):
    b=arm.edit_bones.new(name); b.head=head; b.tail=tail
    if (b.tail-b.head).length<1e-6: b.tail.z+=1e-4
    if parent is not None: b.parent=parent; b.use_connect=False
    return b


def _choose_bone(name:str,n:Vector)->str:
    low=name.lower()
    if any(t in low for t in HAIR_TOKENS): return "head"
    if n.z>0.70: return "head"
    if n.z>0.62: return "neck"
    if 0.39<=n.z<=0.66 and n.x<0.34:
        if n.x<0.08: return "hand.L"
        if n.x<0.21: return "forearm.L"
        return "upper_arm.L"
    if 0.39<=n.z<=0.66 and n.x>0.66:
        if n.x>0.92: return "hand.R"
        if n.x>0.79: return "forearm.R"
        return "upper_arm.R"
    if n.z<0.42:
        side="L" if n.x<0.5 else "R"
        if n.z<0.07: return f"foot.{side}"
        if n.z<0.22: return f"shin.{side}"
        return f"thigh.{side}"
    if n.z<0.50: return "pelvis"
    if n.z<0.60: return "spine"
    return "chest"


def main()->int:
    p=argparse.ArgumentParser(description="Rig candidato determinista + pose de prueba")
    p.add_argument('--input',required=True); p.add_argument('--output',required=True); p.add_argument('--report',required=True)
    args=p.parse_args()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if not meshes: raise RuntimeError('GLB sin mallas')
    body=max(meshes,key=lambda o:len(o.data.polygons))

    arm_data=bpy.data.armatures.new('COPOX_Rig')
    arm_obj=bpy.data.objects.new('COPOX_Rig',arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)
    arm_obj.matrix_world=body.matrix_world.copy()
    lo,hi,span=_arm_points(meshes,arm_obj.matrix_world)

    bpy.context.view_layer.objects.active=arm_obj; arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    root=_add_bone(arm_data,'root',_P(lo,span,.5,.5,.04),_P(lo,span,.5,.5,.36))
    pelvis=_add_bone(arm_data,'pelvis',_P(lo,span,.5,.5,.30),_P(lo,span,.5,.5,.45),root)
    spine=_add_bone(arm_data,'spine',_P(lo,span,.5,.5,.43),_P(lo,span,.5,.5,.57),pelvis)
    chest=_add_bone(arm_data,'chest',_P(lo,span,.5,.5,.55),_P(lo,span,.5,.5,.66),spine)
    neck=_add_bone(arm_data,'neck',_P(lo,span,.5,.5,.64),_P(lo,span,.5,.5,.72),chest)
    head=_add_bone(arm_data,'head',_P(lo,span,.5,.5,.70),_P(lo,span,.5,.5,.91),neck)
    ula=_add_bone(arm_data,'upper_arm.L',_P(lo,span,.36,.5,.60),_P(lo,span,.21,.5,.56),chest)
    fla=_add_bone(arm_data,'forearm.L',_P(lo,span,.21,.5,.56),_P(lo,span,.08,.5,.52),ula)
    _add_bone(arm_data,'hand.L',_P(lo,span,.08,.5,.52),_P(lo,span,.025,.5,.52),fla)
    ura=_add_bone(arm_data,'upper_arm.R',_P(lo,span,.64,.5,.60),_P(lo,span,.79,.5,.56),chest)
    fra=_add_bone(arm_data,'forearm.R',_P(lo,span,.79,.5,.56),_P(lo,span,.92,.5,.52),ura)
    _add_bone(arm_data,'hand.R',_P(lo,span,.92,.5,.52),_P(lo,span,.975,.5,.52),fra)
    tla=_add_bone(arm_data,'thigh.L',_P(lo,span,.44,.5,.36),_P(lo,span,.44,.5,.20),pelvis)
    sla=_add_bone(arm_data,'shin.L',_P(lo,span,.44,.5,.20),_P(lo,span,.44,.5,.065),tla)
    _add_bone(arm_data,'foot.L',_P(lo,span,.44,.5,.065),_P(lo,span,.44,.72,.03),sla)
    tra=_add_bone(arm_data,'thigh.R',_P(lo,span,.56,.5,.36),_P(lo,span,.56,.5,.20),pelvis)
    sra=_add_bone(arm_data,'shin.R',_P(lo,span,.56,.5,.20),_P(lo,span,.56,.5,.065),tra)
    _add_bone(arm_data,'foot.R',_P(lo,span,.56,.5,.065),_P(lo,span,.56,.72,.03),sra)
    bpy.ops.object.mode_set(mode='OBJECT')

    bone_names={b.name for b in arm_data.bones}
    weighted=0; total=0; assignment_counts={name:0 for name in bone_names}
    rest_coords={}
    inv=arm_obj.matrix_world.inverted()
    for obj in meshes:
        for vg in list(obj.vertex_groups): obj.vertex_groups.remove(vg)
        groups={name:obj.vertex_groups.new(name=name) for name in bone_names}
        rest_coords[obj.name]=[v.co.copy() for v in obj.data.vertices]
        for v in obj.data.vertices:
            p_arm=inv @ obj.matrix_world @ v.co
            n=Vector(((p_arm.x-lo.x)/span.x,(p_arm.y-lo.y)/span.y,(p_arm.z-lo.z)/span.z))
            bone=_choose_bone(obj.name,n)
            groups[bone].add([v.index],1.0,'REPLACE')
            assignment_counts[bone]+=1; weighted+=1; total+=1
        mod=obj.modifiers.new(name='COPOX_Armature',type='ARMATURE'); mod.object=arm_obj

    # Pose simple de antebrazo izquierdo: debe deformar algo y permanecer finito.
    bpy.context.view_layer.objects.active=arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    pb=arm_obj.pose.bones['forearm.L']; pb.rotation_mode='XYZ'; pb.rotation_euler=Euler((0.0,math.radians(18.0),0.0),'XYZ')
    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get()
    moved_vertices=0; max_disp=0.0; finite=True
    for obj in meshes:
        eval_obj=obj.evaluated_get(deps); em=eval_obj.to_mesh()
        original=rest_coords[obj.name]
        for i,v in enumerate(em.vertices):
            if i>=len(original): break
            d=(v.co-original[i]).length
            if not math.isfinite(d): finite=False
            if d>1e-7: moved_vertices+=1
            max_disp=max(max_disp,d)
        eval_obj.to_mesh_clear()
    bpy.ops.object.mode_set(mode='OBJECT')
    pb.rotation_euler=Euler((0.0,0.0,0.0),'XYZ'); bpy.context.view_layer.update()

    out=Path(args.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',export_skins=True,export_animations=True)
    report={
        'mode':'rig_candidate_learning_only','bone_count':len(bone_names),'bone_names':sorted(bone_names),
        'vertex_count':total,'weighted_vertices':weighted,'weight_coverage':weighted/max(total,1),
        'assignment_counts':assignment_counts,'pose_test':{'bone':'forearm.L','angle_deg':18.0,'moved_vertices':moved_vertices,'max_displacement':max_disp,'finite':finite},
        'candidate_ready_for_audit':bool(weighted==total and moved_vertices>0 and finite),
        'promotion_allowed':False,
        'learning':{'finger_bones_present':False,'facial_bones_present':False,'note':'Este rig sólo valida el proceso de skin/deformación. Dedos y cara requieren procesos propios antes de rig final.'}
    }
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False)); return 0

if __name__=='__main__': raise SystemExit(main())
