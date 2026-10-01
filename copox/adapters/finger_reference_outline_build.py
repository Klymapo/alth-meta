from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector


def _read(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _inside(n: Vector, box: list[float]) -> bool:
    return box[0] <= n.x <= box[3] and box[1] <= n.y <= box[4] and box[2] <= n.z <= box[5]


def main() -> int:
    p = argparse.ArgumentParser(description="Volumiza contorno 2D de mano desde referencia; learning-only")
    p.add_argument("--input", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--depth-scale", type=float, default=0.72)
    args = p.parse_args()
    if not (0.40 <= args.depth_scale <= 1.05):
        raise ValueError("depth-scale fuera de rango")

    plan = _read(args.plan)
    if not plan.get("research_prototype") or plan.get("promotion_allowed"):
        raise RuntimeError("Plan no learning-only")
    points = [[float(a), float(b)] for a, b in plan.get("outline_points") or []]
    if len(points) < 8:
        raise RuntimeError("Contorno insuficiente")
    box = [float(v) for v in plan["hand_morph_box"]]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("GLB sin mallas")
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    mesh = obj.data
    before_faces = len(mesh.polygons)
    before_vertices = len(mesh.vertices)

    rotation = Matrix.Rotation(math.radians(-90.0), 4, "X")
    inv_rotation = rotation.inverted()
    canonical_matrix = rotation @ obj.matrix_world
    inv_obj = obj.matrix_world.inverted()
    cvs = [canonical_matrix @ v.co for v in mesh.vertices]
    lo = Vector((min(v.x for v in cvs), min(v.y for v in cvs), min(v.z for v in cvs)))
    hi = Vector((max(v.x for v in cvs), max(v.y for v in cvs), max(v.z for v in cvs)))
    span = Vector((max(hi.x-lo.x, 1e-12), max(hi.y-lo.y, 1e-12), max(hi.z-lo.z, 1e-12)))

    def norm(c: Vector) -> Vector:
        return Vector(((c.x-lo.x)/span.x, (c.y-lo.y)/span.y, (c.z-lo.z)/span.z))

    sample_y = [float(c.y) for c in cvs if _inside(norm(c), box)]
    if len(sample_y) >= 8:
        q0, q1 = np.quantile(np.asarray(sample_y), [0.12, 0.88])
        y_center = float((q0 + q1) * 0.5)
        half_depth = max(float((q1 - q0) * 0.5 * args.depth_scale), float(span.y) * 0.008)
    else:
        y_center = float(lo.y + ((box[1] + box[4]) * 0.5) * span.y)
        half_depth = max(float((box[4]-box[1]) * span.y * 0.25 * args.depth_scale), float(span.y) * 0.008)

    # Retirar sólo la mano izquierda experimental. No se toca muñeca/antebrazo fuera
    # del morph box existente. La abertura resultante se acepta sólo en esta prueba.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    delete_faces = []
    for f in bm.faces:
        c = canonical_matrix @ f.calc_center_median()
        if _inside(norm(c), box):
            delete_faces.append(f)
    deleted = len(delete_faces)
    if delete_faces:
        bmesh.ops.delete(bm, geom=delete_faces, context="FACES")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    n = len(points)
    local_verts: list[tuple[float, float, float]] = []
    # dos capas paralelas; el contorno conserva exactamente la distribución X/Z del plan
    for y in (y_center - half_depth, y_center + half_depth):
        for nx, nz in points:
            c = Vector((lo.x + nx*span.x, y, lo.z + nz*span.z))
            raw_world = inv_rotation @ c
            local = inv_obj @ raw_world
            local_verts.append((float(local.x), float(local.y), float(local.z)))

    faces: list[tuple[int, ...]] = []
    faces.append(tuple(range(n)))
    faces.append(tuple(reversed(range(n, 2*n))))
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n+j, n+i))

    patch_mesh = bpy.data.meshes.new("COPOX_ReferenceOutlineHand_mesh")
    patch_mesh.from_pydata(local_verts, [], faces)
    patch_mesh.update()
    patch_obj = bpy.data.objects.new("COPOX_ReferenceOutlineHand", patch_mesh)
    bpy.context.scene.collection.objects.link(patch_obj)
    patch_obj.matrix_world = obj.matrix_world.copy()
    if len(mesh.materials):
        patch_mesh.materials.append(mesh.materials[0])

    # Triangularizamos después de preservar el borde; esto evita depender de la
    # triangulación implícita de un ngon cóncavo al exportar GLB.
    bm2 = bmesh.new()
    bm2.from_mesh(patch_mesh)
    bmesh.ops.triangulate(bm2, faces=list(bm2.faces))
    bm2.to_mesh(patch_mesh)
    bm2.free()
    patch_mesh.update()
    for poly in patch_mesh.polygons:
        poly.use_smooth = True

    bpy.context.view_layer.update()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB")

    finite = all(math.isfinite(c) for v in patch_mesh.vertices for c in v.co)
    result = {
        "mode": "reference_hand_outline_extrusion_build_v1",
        "reference_driven": bool(plan.get("reference_driven")),
        "invented_finger_count": bool(plan.get("invented_finger_count")),
        "research_prototype": True,
        "outline_point_count": int(n),
        "deleted_baseline_faces": int(deleted),
        "baseline_vertices_before": int(before_vertices),
        "baseline_faces_before": int(before_faces),
        "baseline_faces_after_delete": int(len(mesh.polygons)),
        "patch_vertices": int(len(patch_mesh.vertices)),
        "patch_faces": int(len(patch_mesh.polygons)),
        "sampled_depth_vertices": int(len(sample_y)),
        "depth_scale": float(args.depth_scale),
        "closed_patch_volume": True,
        "mesh_integrity": bool(finite and len(patch_mesh.vertices) > 0 and len(patch_mesh.polygons) > 0),
        "bridge_to_wrist_validated": False,
        "scope_safe": False,
        "promotion_allowed": False,
        "learning": (
            "La forma 2D completa se trazó desde referencia y se volumizó como pieza cerrada. "
            "Si mejora la lectura frontal, la siguiente etapa debe retopologizar/crear loops de articulación y bridgear el borde proximal a la muñeca."
        ),
    }
    Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "outline_point_count": n,
        "deleted_baseline_faces": deleted,
        "patch_vertices": result["patch_vertices"],
        "patch_faces": result["patch_faces"],
        "mesh_integrity": result["mesh_integrity"],
    }, ensure_ascii=False))
    return 0 if result["mesh_integrity"] else 8


if __name__ == "__main__":
    raise SystemExit(main())
