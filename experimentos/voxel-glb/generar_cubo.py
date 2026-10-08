#!/usr/bin/env python3
"""Generador de cubos GLB 2.0 sin librerías externas."""
import argparse
import json
import math
import struct
from pathlib import Path

def parse_color(color):
    color=color.lstrip('#')
    if len(color) not in (6,8):
        raise ValueError('El color debe ser hexadecimal: #RRGGBB o #RRGGBBAA')
    try:
        values=[int(color[i:i+2],16)/255 for i in range(0,len(color),2)]
    except ValueError as e:
        raise ValueError('El color contiene caracteres no hexadecimales') from e
    if len(values)==3:
        values.append(1.0)
    return values

def glb_cubo(lado=1.0,color='#5089C6'):
    if not math.isfinite(lado) or lado<=0:
        raise ValueError('El lado debe ser positivo y finito')
    h=lado/2
    faces=[
        ([(-h,-h,h),(h,-h,h),(h,h,h),(-h,h,h)],(0,0,1)),
        ([(h,-h,-h),(-h,-h,-h),(-h,h,-h),(h,h,-h)],(0,0,-1)),
        ([(h,-h,h),(h,-h,-h),(h,h,-h),(h,h,h)],(1,0,0)),
        ([(-h,-h,-h),(-h,-h,h),(-h,h,h),(-h,h,-h)],(-1,0,0)),
        ([(-h,h,h),(h,h,h),(h,h,-h),(-h,h,-h)],(0,1,0)),
        ([(-h,-h,-h),(h,-h,-h),(h,-h,h),(-h,-h,h)],(0,-1,0))]
    vertices=[]; normals=[]; indices=[]
    for points,normal in faces:
        start=len(vertices)//3
        for pt in points:
            vertices.extend(pt);normals.extend(normal)
        indices.extend([start,start+1,start+2,start,start+2,start+3])
    def align(data):
        return data+b'\x00'*((-len(data))%4)
    positions=struct.pack('<%sf'%len(vertices),*vertices)
    normal_data=struct.pack('<%sf'%len(normals),*normals)
    index_data=struct.pack('<%sH'%len(indices),*indices)
    buffer=bytearray();views=[]
    for data,target in ((positions,34962),(normal_data,34962),(index_data,34963)):
        off=len(buffer);buffer.extend(align(data))
        views.append({'buffer':0,'byteOffset':off,'byteLength':len(data),'target':target})
    doc={
      'asset':{'version':'2.0','generator':'AlasTheo stdlib GLB'},
      'scene':0,'scenes':[{'nodes':[0]}],
      'nodes':[{'name':'Cubo','mesh':0}],
      'meshes':[{'name':'Cubo','primitives':[{
        'attributes':{'POSITION':0,'NORMAL':1},'indices':2,'material':0,'mode':4}]}],
      'materials':[{'name':'Material del cubo','pbrMetallicRoughness':{
        'baseColorFactor':parse_color(color),'metallicFactor':0,'roughnessFactor':0.85},
        'doubleSided':False}],
      'buffers':[{'byteLength':len(buffer)}],
      'bufferViews':views,
      'accessors':[
        {'bufferView':0,'componentType':5126,'count':24,'type':'VEC3',
         'min':[-h,-h,-h],'max':[h,h,h]},
        {'bufferView':1,'componentType':5126,'count':24,'type':'VEC3'},
        {'bufferView':2,'componentType':5123,'count':36,'type':'SCALAR',
         'min':[0],'max':[23]}]}
    j=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    j+=b' '*((-len(j))%4)
    binary=bytes(buffer)
    size=12+8+len(j)+8+len(binary)
    return struct.pack('<4sII',b'glTF',2,size)+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(binary),b'BIN\x00')+binary

def main():
    ap=argparse.ArgumentParser(description='Genera un cubo GLB válido')
    ap.add_argument('--lado',type=float,default=1.0)
    ap.add_argument('--color',default='#5089C6')
    ap.add_argument('--salida',default='cubo.glb')
    a=ap.parse_args()
    target=Path(a.salida);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(glb_cubo(a.lado,a.color))
    print(f'Generado: {target.resolve()} ({target.stat().st_size} bytes)')

if __name__=='__main__':
    main()
