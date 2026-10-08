#!/usr/bin/env python3
"""Renderiza 4 vistas leyendo posiciones, normales y materiales desde el GLB."""
import argparse
import json
import math
import struct
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unit(v):
    n=math.sqrt(dot(v,v));return tuple(x/n for x in v)
def font(size,bold=False):
    path="/usr/share/fonts/truetype/dejavu/DejaVuSans"+("-Bold" if bold else "")+".ttf"
    try: return ImageFont.truetype(path,size)
    except OSError: return ImageFont.load_default()

def read_glb_faces(path):
    data=Path(path).read_bytes()
    magic,ver,n=struct.unpack_from("<4sII",data)
    if (magic,ver,n)!=(b"glTF",2,len(data)): raise ValueError("GLB inválido")
    offset=12;chunks={}
    while offset<len(data):
        length,kind=struct.unpack_from("<I4s",data,offset);offset+=8
        chunks[kind]=data[offset:offset+length];offset+=length
    if offset!=len(data): raise ValueError("Chunk inválido")
    doc=json.loads(chunks[b"JSON"]);raw=chunks[b"BIN\x00"]
    def acc(i):
        info=doc["accessors"][i];v=doc["bufferViews"][info["bufferView"]]
        type_char={5126:"f",5123:"H",5125:"I"}[info["componentType"]]
        count={"SCALAR":1,"VEC3":3}[info["type"]]
        fmt="<"+type_char*count
        off=v.get("byteOffset",0)+info.get("byteOffset",0)
        stride=v.get("byteStride",struct.calcsize(fmt))
        return [struct.unpack_from(fmt,raw,off+k*stride) for k in range(info["count"])]
    result=[]
    for p in doc["meshes"][0]["primitives"]:
        positions=acc(p["attributes"]["POSITION"])
        normals=acc(p["attributes"]["NORMAL"])
        ix=[i[0] for i in acc(p["indices"])]
        rgb=tuple(round(x*255) for x in doc["materials"][p["material"]]["pbrMetallicRoughness"]["baseColorFactor"][:3])
        if len(ix)%6: raise ValueError("Se esperan quads triangulados")
        for k in range(0,len(ix),6):
            a,b,c,d,e,f=ix[k:k+6]
            if a!=d or c!=e: raise ValueError("Triangulación de quad inesperada")
            result.append(((positions[a],positions[b],positions[c],positions[f]),normals[a],rgb))
    return result

def render(faces,title,camera,path,width=680):
    S=width*2;im=Image.new("RGB",(S,S),(241,245,251));dr=ImageDraw.Draw(im)
    dr.rounded_rectangle((32,32,S-32,S-32),radius=28,fill="white",outline=(222,228,239),width=2)
    fwd=unit(camera);up_ref=(0,0,-1) if abs(fwd[1])>.97 else (0,1,0)
    right=unit(cross(up_ref,fwd));up=unit(cross(fwd,right))
    points=[p for face,_,_ in faces for p in face]
    lows=[min(p[i] for p in points) for i in range(3)]
    highs=[max(p[i] for p in points) for i in range(3)]
    center=tuple((lows[i]+highs[i])/2 for i in range(3))
    def plane(p):
        v=sub(p,center);return (dot(v,right),-dot(v,up))
    bounds=[plane(p) for p in points]
    wx=max(v[0] for v in bounds)-min(v[0] for v in bounds)
    wy=max(v[1] for v in bounds)-min(v[1] for v in bounds)
    zoom=min(S*.69/max(wx,1e-4),S*.62/max(wy,1e-4))
    def proj(p):
        a,b=plane(p);return (S/2+a*zoom,S*.52+b*zoom)
    light=unit((.5,.9,1));ordered=[]
    for quad,normal,rgb in faces:
        if dot(normal,fwd)<=1e-6: continue
        depth=sum(dot(sub(v,center),fwd) for v in quad)/4
        strength=.66+.31*max(0,dot(normal,light))
        color=tuple(min(255,round(v*strength+8)) for v in rgb)
        ordered.append((depth,quad,color))
    ordered.sort(key=lambda x:x[0])
    for _,quad,col in ordered:
        polygon=[proj(p) for p in quad]
        dr.polygon(polygon,fill=col)
        dr.line(polygon+[polygon[0]],fill=(37,54,79),width=6,joint="curve")
    dr.text((85,78),title.upper(),font=font(58,True),fill=(29,48,76))
    x=90
    for label,rgb in (("AZUL",(71,126,219)),("VERDE",(66,184,109)),("AMARILLO",(249,214,74))):
        dr.rounded_rectangle((x,S-123,x+27,S-96),radius=5,fill=rgb)
        dr.text((x+37,S-130),label,font=font(32,True),fill=(86,99,116));x+=190
    im.resize((width,width),Image.Resampling.LANCZOS).save(path,optimize=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("modelo")
    parser.add_argument("--salida",default="capturas")
    parser.add_argument("--tamano",type=int,default=680)
    args=parser.parse_args()
    out=Path(args.salida);out.mkdir(parents=True,exist_ok=True)
    faces=read_glb_faces(args.modelo)
    names=(("frente",(0,0,3)),("derecha",(3,0,0)),("superior",(0,3,0)),("isometrica",(3,2.8,4)))
    sheet=Image.new("RGB",(2*args.tamano,2*args.tamano),(241,245,251))
    for i,(name,camera) in enumerate(names):
        path=out/f"voxeles_{name}.png"
        render(faces,name,camera,path,args.tamano)
        sheet.paste(Image.open(path),((i%2)*args.tamano,(i//2)*args.tamano))
        print("Captura:",path)
    sheet.save(out/"voxeles_4_vistas.png",optimize=True)

if __name__=="__main__":
    main()
