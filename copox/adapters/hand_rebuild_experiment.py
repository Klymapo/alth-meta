from __future__ import annotations

import argparse, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector

def read(p): return json.loads(Path(p).read_text(encoding="utf-8"))

def add_box(name, center, dims, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    o=bpy.context.object; o.name=name; o.dimensions=dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    return o

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True); p.add_argument("--config",required=True)
    p.add_argument("--output",required=True); p.add_argument("--report",required=True)
    p.add_argument("--slot",type=int,default=1)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]\n    a=p.parse_args(argv); cfg=read(a.config)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(a.input).resolve()))
    meshes=[o for o in bpy.context.scene.objects if o.type=="MESH"]
    body=max(meshes,key=lambda o:len(o.data.polygons))
    lo=Vector((min((body.matrix_world@Vector(v)).x for v in body.bound_box),min((body.matrix_world@Vector(v)).y for v in body.bound_box),min((body.matrix_world@Vector(v)).z for v in body.bound_box)))
    hi=Vector((max((body.matrix_world@Vector(v)).x for v in body.bound_box),max((body.matrix_world@Vector(v)).y for v in body.bound_box),max((body.matrix_world@Vector(v)).z for v in body.bound_box)))
    span=hi-lo
    boxes=cfg["morph_regions"]["hands"]["boxes"]
    material=body.data.materials[0] if body.data.materials else bpy.data.materials.new("TheoHand")
    created=[]
    # Hipótesis web-informed: palma simple + dedos como extrusiones prismáticas segmentadas.
    # Se mantiene como objetos separados en esta prueba: medimos silueta antes de intentar bridge a muñeca.
    segs=[2,3,3][max(0,min(a.slot-1,2))]
    for bi,b in enumerate(boxes):
        x0,y0,z0,x1,y1,z1=map(float,b); side=-1 if bi==0 else 1
        xa=lo.x+x0*span.x; xb=lo.x+x1*span.x
        ya=lo.y+y0*span.y; yb=lo.y+y1*span.y
        za=lo.z+z0*span.z; zb=lo.z+z1*span.z
        palm_w=abs(xb-xa)*0.48; palm_d=abs(yb-ya)*0.62; palm_h=abs(zb-za)*0.68
        distal=min(xa,xb) if side<0 else max(xa,xb)
        proximal=max(xa,xb) if side<0 else min(xa,xb)
        pcx=proximal + side*abs(xb-xa)*0.28
        pcy=(ya+yb)/2; pcz=(za+zb)/2
        palm=add_box(f"COPOX_Palm_{bi}",(pcx,pcy,pcz),(palm_w,palm_d,palm_h),material); created.append(palm.name)
        # Cuatro rayos principales, deliberadamente paramétricos; esta prueba valida técnica,
        # no afirma todavía medidas anatómicas finales.
        ratios=[0.82,1.0,0.94,0.76]
        zoffs=[-0.30,-0.10,0.11,0.30]
        finger_len=abs(xb-xa)*0.50
        for fi,(ratio,zo) in enumerate(zip(ratios,zoffs)):
            length=finger_len*ratio; thick=max(palm_h*0.15,abs(zb-za)*0.055)
            for si in range(segs):
                sl=length/segs
                cx=pcx + side*(palm_w/2 + sl*(si+0.5))
                cz=pcz + zo*palm_h
                o=add_box(f"COPOX_Finger_{bi}_{fi}_{si}",(cx,pcy,cz),(sl*1.03,palm_d*0.72,thick),material)
                bevel=o.modifiers.new("joint_softness","BEVEL"); bevel.width=min(thick,sl)*0.18; bevel.segments=2
                created.append(o.name)
        # pulgar: separado y ligeramente inferior; evita tratarlo como dedo paralelo.
        tl=abs(xb-xa)*0.31
        tx=pcx+side*(palm_w*0.28); tz=pcz-palm_h*0.43
        thumb=add_box(f"COPOX_Thumb_{bi}",(tx,pcy,tz),(tl,palm_d*0.75,palm_h*0.17),material)
        thumb.rotation_euler[1]=side*math.radians(24); created.append(thumb.name)
    out=Path(a.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out),export_format="GLB")
    report={"mode":"web_research_hand_rebuild_experiment","slot":a.slot,"promotion_allowed":False,
      "technique":["palm primitive","separate finger rays","2-3 joint segments","thumb independent"],
      "created_objects":created,"created_count":len(created),
      "note":"Prueba geométrica inspirada en extrusión/edge-loop modeling; aún no conecta la palma a la muñeca ni usa proporciones finales."}
    Path(a.report).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report))
    return 0
if __name__=="__main__": raise SystemExit(main())
