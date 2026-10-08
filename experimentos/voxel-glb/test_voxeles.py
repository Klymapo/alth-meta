"""Pruebas para las capas y las caras expuestas, incluidas las multicolor."""
import json
import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from generar_voxeles import default_voxels,read_layout,exposed_faces,glb_from_voxels
from render_voxeles import read_glb_faces

class VoxelTests(unittest.TestCase):
    def test_layout(self):
        voxels=default_voxels()
        self.assertEqual(Counter(voxels.values()),{"azul":9,"verde":4,"amarillo":1})
        self.assertEqual(Counter(p[1] for p in voxels),{0:9,1:4,2:1})
        self.assertEqual(voxels[(1,2,1)],"amarillo")
    def test_hidden_faces(self):
        voxels=default_voxels()
        faces=list(exposed_faces(voxels))
        self.assertEqual(len(faces),42)
        self.assertEqual(Counter(f[0] for f in faces),{"azul":26,"verde":11,"amarillo":5})
        for _,pos,n,_ in faces:
            self.assertNotIn(tuple(pos[i]+n[i] for i in range(3)),voxels)
        _,stats=glb_from_voxels(voxels)
        self.assertEqual(stats["caras_internas_omitidas"],42)
        self.assertEqual(stats["triangulos"],84)
        self.assertEqual(stats["vertices"],168)
    def test_glb_content(self):
        data,_=glb_from_voxels(default_voxels())
        self.assertEqual(struct.unpack_from("<4sII",data),(b"glTF",2,len(data)))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.glb";p.write_bytes(data)
            faces=read_glb_faces(p)
        self.assertEqual(len(faces),42)
        self.assertEqual(Counter(rgb for _,_,rgb in faces),
                         {(71,126,219):26,(66,184,109):11,(249,214,74):5})
    def test_adjacent_different_colors(self):
        voxels={(0,0,0):"azul",(1,0,0):"verde"}
        self.assertEqual(len(list(exposed_faces(voxels))),10)
        _,stats=glb_from_voxels(voxels)
        self.assertEqual(stats["caras_internas_omitidas"],2)
    def test_custom_layout(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"p.json"
            p.write_text(json.dumps({"voxeles":[{"x":-1,"y":3,"z":2,"color":"verde"}]}))
            self.assertEqual(read_layout(p),{(-1,3,2):"verde"})

if __name__=="__main__":
    unittest.main()
