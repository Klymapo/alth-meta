# Ejemplo de prueba: separar los dedos de una mano con bisect y split.
import bmesh
import bpy

def split_fingers(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, dist=0.0001, plane_co=(0.0, 0.0, 0.5), plane_no=(1.0, 0.0, 0.0))
    cut = [e for e in bm.edges if e.select]
    bmesh.ops.split_edges(bm, edges=cut)
    bm.to_mesh(obj.data)
