"""Audit immutable exterior after GLB transport, independent of Blender's in-memory claim."""
from collections import Counter
import numpy as np
import trimesh

def exterior_transport(parent, candidate, plan):
    lo,hi=np.asarray(plan["canonical_bounds"],float)
    span=hi-lo; box=np.asarray(plan["scope_box"],float)
    # GLB attributes are float32: two ulps across bounds, recorded as tolerance.
    tolerance=float(np.linalg.norm(span)*2**-22)
    def rows(path):
        scene=trimesh.load(path,force="scene",process=False)
        protected=Counter(); complete=Counter()
        for node in scene.graph.nodes_geometry:
            matrix,name=scene.graph.get(node); geom=scene.geometry[name]
            if not hasattr(geom,"vertices"): continue
            points=(matrix@np.column_stack([geom.vertices,np.ones(len(geom.vertices))]).T).T[:,:3]
            coords=np.rint(points/tolerance).astype(np.int64)
            norm=(points-lo)/span
            uv=getattr(geom.visual,"uv",None)
            for face in geom.faces:
                corners=tuple(sorted((tuple(coords[i]),tuple(np.rint(uv[i]/2**-22).astype(np.int64)) if uv is not None else ()) for i in face))
                complete[corners]+=1
                if not np.all((norm[face]>=box[:3])&(norm[face]<=box[3:])):
                    protected[corners]+=1
        return protected,complete
    original,_=rows(parent); _,after=rows(candidate)
    missing=original-after
    return {"checked":True,"protected_triangles":sum(original.values()),
            "missing_protected_triangles":sum(missing.values()),"scope_safe":not missing,
            "coordinate_quantization_m":tolerance,"uv_quantization":2**-22,
            "method":"world_triangle_corner_position_and_UV_multiset_after_GLB_transport"}
