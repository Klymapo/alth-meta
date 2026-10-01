# Ejemplo de prueba: soldar vértices duplicados y reducir una malla escaneada.
import bmesh

def clean(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bm.to_mesh(obj.data)
    m = obj.modifiers.new("dec", type="DECIMATE")
    m.ratio = 0.25
