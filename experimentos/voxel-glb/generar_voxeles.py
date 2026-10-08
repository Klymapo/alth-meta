#!/usr/bin/env python3
"""Voxel GLB 2.0: posiciones enteras y ocultación de caras entre materiales."""
import argparse
import json
import struct
from collections import Counter
from pathlib import Path

COLORS = {"azul":"#477EDB", "verde":"#42B86D", "amarillo":"#F9D64A"}
# Esquinas CCW desde el exterior; delta indica el vecino.
FACES = (
 ((1,0,0), ((1,0,0),(1,1,0),(1,1,1),(1,0,1))),
 ((-1,0,0),((0,0,1),(0,1,1),(0,1,0),(0,0,0))),
 ((0,1,0), ((0,1,1),(1,1,1),(1,1,0),(0,1,0))),
 ((0,-1,0),((0,0,0),(1,0,0),(1,0,1),(0,0,1))),
 ((0,0,1), ((0,0,1),(1,0,1),(1,1,1),(0,1,1))),
 ((0,0,-1),((0,1,0),(1,1,0),(1,0,0),(0,0,0)))
)

def default_voxels():
    """9 azules Y0, 4 verdes Y1, 1 amarillo Y2.
    Un 2x2 no se centra exactamente en un 3x3 de cuadrícula entera:
    verde se coloca en x,z=1,2 para compartir caras completas."""
    voxels={(x,0,z):"azul" for x in range(3) for z in range(3)}
    voxels.update({(x,1,z):"verde" for x in (1,2) for z in (1,2)})
    voxels[(1,2,1)]="amarillo"
    return voxels

def read_layout(path):
    """JSON: {"voxeles":[{"x":0,"y":0,"z":0,"color":"azul"}, ...]}"""
    doc=json.loads(Path(path).read_text(encoding="utf-8"))
    voxels={}
    for v in doc["voxeles"]:
        p=tuple(v[k] for k in ("x","y","z"))
        if any(type(t) is not int for t in p):
            raise ValueError("Las posiciones deben ser coordenadas enteras")
        if p in voxels:
            raise ValueError(f"Voxel repetido: {p}")
        if v["color"] not in COLORS:
            raise ValueError(f"Color desconocido: {v['color']}")
        voxels[p]=v["color"]
    if not voxels:
        raise ValueError("El layout está vacío")
    return voxels

def exposed_faces(voxels):
    if not voxels:
        raise ValueError("El layout está vacío")
    for pos,color in sorted(voxels.items()):
        x,y,z=pos
        for normal,corners in FACES:
            dx,dy,dz=normal
            # Culling transversal: también oculta contactos azul-verde o verde-amarillo.
            if (x+dx,y+dy,z+dz) in voxels:
                continue
            yield color,pos,normal,tuple((x+vx,y+vy,z+vz) for vx,vy,vz in corners)

def glb_from_voxels(voxels):
    faces=list(exposed_faces(voxels))
    raw=bytearray();views=[];acc=[];primitives=[];materials=[]
    def pack_view(data,target):
        off=len(raw);raw.extend(data);raw.extend(b"\x00"*((-len(raw))%4))
        idx=len(views)
        views.append({"buffer":0,"byteOffset":off,"byteLength":len(data),"target":target})
        return idx
    for color in COLORS:
        group=[f for f in faces if f[0]==color]
        if not group: continue
        positions=[];normals=[];indices=[]
        for _,_,n,corners in group:
            begin=len(positions)//3
            for point in corners:
                positions.extend(point);normals.extend(n)
            indices.extend((begin,begin+1,begin+2,begin,begin+2,begin+3))
        code="H" if len(positions)//3<=65535 else "I"
        component=5123 if code=="H" else 5125
        pb=pack_view(struct.pack("<"+"f"*len(positions),*positions),34962)
        nb=pack_view(struct.pack("<"+"f"*len(normals),*normals),34962)
        ib=pack_view(struct.pack("<"+code*len(indices),*indices),34963)
        vertices=[positions[i:i+3] for i in range(0,len(positions),3)]
        start=len(acc)
        acc.extend((
          {"bufferView":pb,"componentType":5126,"count":len(vertices),"type":"VEC3",
           "min":[min(v[i] for v in vertices) for i in range(3)],
           "max":[max(v[i] for v in vertices) for i in range(3)]},
          {"bufferView":nb,"componentType":5126,"count":len(vertices),"type":"VEC3"},
          {"bufferView":ib,"componentType":component,"count":len(indices),
           "type":"SCALAR","min":[0],"max":[max(indices)]}
        ))
        mat=len(materials)
        hexa=COLORS[color]
        rgba=[int(hexa[k:k+2],16)/255 for k in (1,3,5)]+[1.0]
        materials.append({"name":color.title(),"pbrMetallicRoughness":{
          "baseColorFactor":rgba,"metallicFactor":0,"roughnessFactor":0.85},
          "doubleSided":False})
        primitives.append({"attributes":{"POSITION":start,"NORMAL":start+1},
          "indices":start+2,"material":mat,"mode":4})
    doc={"asset":{"version":"2.0","generator":"AlasTheo voxel lab"},
         "scene":0,"scenes":[{"nodes":[0]}],
         "nodes":[{"name":"EstructuraVoxel","mesh":0}],
         "meshes":[{"name":"EstructuraVoxel","primitives":primitives}],
         "materials":materials,"buffers":[{"byteLength":len(raw)}],
         "bufferViews":views,"accessors":acc}
    j=json.dumps(doc,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    j+=b" "*((-len(j))%4)
    binary=bytes(raw)
    n=12+8+len(j)+8+len(binary)
    glb=(struct.pack("<4sII",b"glTF",2,n)
      +struct.pack("<I4s",len(j),b"JSON")+j
      +struct.pack("<I4s",len(binary),b"BIN\x00")+binary)
    pairs=sum((x+dx,y+dy,z+dz) in voxels for x,y,z in voxels
              for dx,dy,dz in ((1,0,0),(0,1,0),(0,0,1)))
    stats={"total_voxeles":len(voxels),"por_color":dict(Counter(voxels.values())),
           "caras_externas":len(faces),"caras_internas_omitidas":pairs*2,
           "parejas_adyacentes":pairs,
           "caras_por_color":dict(Counter(f[0] for f in faces)),
           "triangulos":len(faces)*2,"vertices":len(faces)*4}
    return glb,stats

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--layout",help="Ruta a JSON de posiciones y colores")
    parser.add_argument("--salida",default="estructura_voxel.glb")
    a=parser.parse_args()
    voxels=read_layout(a.layout) if a.layout else default_voxels()
    binary,stats=glb_from_voxels(voxels)
    out=Path(a.salida);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(binary)
    print(out, json.dumps(stats,ensure_ascii=False))

if __name__=="__main__":
    main()
