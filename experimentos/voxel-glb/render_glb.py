#!/usr/bin/env python3
"""Capturas de geometría triangulada leída desde GLB; únicamente Pillow."""
import argparse
import json
import math
import struct
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def unit(v):
    l=math.sqrt(sum(x*x for x in v))
    return tuple(x/l for x in v)

def dot(a,b):
    return sum(x*y for x,y in zip(a,b))

def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def sub(a,b):
    return tuple(x-y for x,y in zip(a,b))

def load_glb(path):
    data=Path(path).read_bytes()
    magic,version,total=struct.unpack_from('<4sII',data,0)
    if (magic,version,total)!=(b'glTF',2,len(data)):
        raise ValueError('Archivo GLB 2.0 inválido')
    off=12;chunks={}
    while off<total:
        n,typ=struct.unpack_from('<I4s',data,off)
        off+=8;chunks[typ]=data[off:off+n];off+=n
    doc=json.loads(chunks[b'JSON'])
    raw=chunks[b'BIN\x00']
    primitive=doc['meshes'][0]['primitives'][0]
    def accessor(i):
        acc=doc['accessors'][i];view=doc['bufferViews'][acc['bufferView']]
        code={5126:'f',5123:'H',5125:'I'}[acc['componentType']]
        width={'VEC3':3,'SCALAR':1}[acc['type']]
        fmt='<'+code*width
        step=view.get('byteStride',struct.calcsize(fmt))
        start=view.get('byteOffset',0)+acc.get('byteOffset',0)
        return [struct.unpack_from(fmt,raw,start+j*step) for j in range(acc['count'])]
    verts=accessor(primitive['attributes']['POSITION'])
    ix=[t[0] for t in accessor(primitive['indices'])]
    tris=[tuple(ix[i:i+3]) for i in range(0,len(ix),3)]
    factor=doc['materials'][primitive.get('material',0)]['pbrMetallicRoughness']['baseColorFactor']
    return verts,tris,tuple(round(255*x) for x in factor[:3])

def font(size,bold=False):
    base='/usr/share/fonts/truetype/dejavu/DejaVuSans'
    try:
        return ImageFont.truetype(base+('-Bold' if bold else '')+'.ttf',size)
    except OSError:
        return ImageFont.load_default()

def render(verts,tris,rgb,name,camera,dest,size=600):
    scale=2;s=size*scale
    canvas=Image.new('RGB',(s,s),(246,248,252))
    dr=ImageDraw.Draw(canvas)
    dr.rounded_rectangle((34,34,s-34,s-34),radius=28,fill=(255,255,255),outline=(220,225,235),width=2)
    forward=unit(camera)
    up_ref=(0,0,-1) if abs(forward[1])>0.97 else (0,1,0)
    right=unit(cross(up_ref,forward))
    up=unit(cross(forward,right))
    center=tuple(sum(v[j] for v in verts)/len(verts) for j in range(3))
    ext=max(max(v[j] for v in verts)-min(v[j] for v in verts) for j in range(3))
    factor=s*.40/max(ext,1e-8)
    def project(point):
        v=sub(point,center)
        return (s/2+dot(v,right)*factor,s/2-dot(v,up)*factor+22*scale)
    light=unit((.5,.85,1))
    visible=[]
    for tri in tris:
        a,b,c=(verts[i] for i in tri)
        normal=unit(cross(sub(b,a),sub(c,a)))
        if dot(normal,forward)<=1e-6:
            continue
        diffuse=.58+.38*max(0,dot(normal,light))
        fill=tuple(min(255,int(q*diffuse+22)) for q in rgb)
        depth=sum(dot(sub(v,center),forward) for v in (a,b,c))/3
        visible.append((depth,tri,fill))
    visible.sort(key=lambda entry:entry[0])
    for _,tri,fill in visible:
        dr.polygon([project(verts[i]) for i in tri],fill=fill)
    edges=Counter()
    for _,tri,_ in visible:
        for i,j in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):
            edges[tuple(sorted((i,j)))]+=1
    for (i,j),count in edges.items():
        if count==1:
            dr.line([project(verts[i]),project(verts[j])],fill=(42,63,95),width=4*scale)
    dr.text((80,78),name.upper(),font=font(27*scale,True),fill=(35,57,92))
    dr.text((80,s-120),f'{len(verts)} vertices · {len(tris)} triangulos · GLB 2.0',font=font(16*scale),fill=(89,105,128))
    canvas.resize((size,size),Image.Resampling.LANCZOS).save(dest,optimize=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('glb');ap.add_argument('--salida',default='capturas')
    ap.add_argument('--tamano',type=int,default=600)
    args=ap.parse_args()
    out=Path(args.salida);out.mkdir(parents=True,exist_ok=True)
    verts,tris,rgb=load_glb(args.glb)
    views={'frente':(0,0,3),'derecha':(3,0,0),'superior':(0,3,0),'isometrica':(3,2.5,4)}
    names=[]
    for name,cam in views.items():
        f=out/f'cubo_{name}.png'
        render(verts,tris,rgb,name,cam,f,args.tamano)
        names.append(f)
        print('Captura real:',f)
    sheet=Image.new('RGB',(args.tamano*2,args.tamano*2),(255,255,255))
    for i,f in enumerate(names):
        sheet.paste(Image.open(f),((i%2)*args.tamano,(i//2)*args.tamano))
    sheet.save(out/'cubo_4_vistas.png',optimize=True)
    print('Lámina de revisión:',out/'cubo_4_vistas.png')

if __name__=='__main__':
    main()
