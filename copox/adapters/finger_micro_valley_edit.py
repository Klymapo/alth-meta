from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_ray_tri

from copox.production.research_gate import require_research

ALPHA_SHA = "ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def normalized(point, lo, span):
    return Vector(tuple((point[i] - lo[i]) / span[i] for i in range(3)))


def inside(point, box):
    return all(box[i] <= point[i] <= box[i + 3] for i in range(3))


def key(co):
    return tuple(round(float(x), 8) for x in co)


def outside_fingerprint(mesh, matrix, lo, span, box):
    # Geometry, per-corner UV, materials and shading outside the scope.
    uv = mesh.uv_layers.active
    rows = Counter()
    for poly in mesh.polygons:
        if any(inside(normalized(matrix @ mesh.vertices[i].co, lo, span), box) for i in poly.vertices):
            continue
        corners = []
        for loop_index in poly.loop_indices:
            loop = mesh.loops[loop_index]
            corners.append((key(mesh.vertices[loop.vertex_index].co), key(uv.data[loop_index].uv) if uv else ()))
        rows[(tuple(sorted(corners)), poly.material_index, poly.use_smooth)] += 1
    return rows


def normals_snapshot(mesh, matrix, lo, span, box):
    result = {}
    for poly in mesh.polygons:
        if any(inside(normalized(matrix @ mesh.vertices[i].co, lo, span), box) for i in poly.vertices):
            continue
        face_key = tuple(sorted(key(mesh.vertices[i].co) for i in poly.vertices))
        for li in poly.loop_indices:
            result[(face_key, key(mesh.vertices[mesh.loops[li].vertex_index].co))] = tuple(mesh.corner_normals[li].vector)
    return result


def restore_normals(mesh, snapshot):
    normals = [(0.0, 0.0, 0.0)] * len(mesh.loops)
    count = 0
    for poly in mesh.polygons:
        face_key = tuple(sorted(key(mesh.vertices[i].co) for i in poly.vertices))
        for li in poly.loop_indices:
            k = (face_key, key(mesh.vertices[mesh.loops[li].vertex_index].co))
            if k in snapshot:
                normals[li] = snapshot[k]
                count += 1
    mesh.normals_split_custom_set(normals)
    return count


def prism(name, profile, ya, yb, inverse_rotation):
    mesh = bpy.data.meshes.new(name)
    n = len(profile)
    points = [inverse_rotation @ Vector((x, y, z)) for y in (ya, yb) for x, z in profile]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    mesh.from_pydata(points, [], faces)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def cycles(edges):
    # Export duplicated face corners can only be interpreted after local exact weld.
    adjacency = {}
    for edge in edges:
        a, b = (key(v.co) for v in edge.verts)
        if a == b:
            continue
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    unseen = set(adjacency)
    closed, opened = [], []
    while unseen:
        stack = [next(iter(unseen))]
        group = set()
        while stack:
            point = stack.pop()
            if point in group:
                continue
            group.add(point)
            stack.extend(adjacency[point] - group)
        unseen -= group
        row = {"vertices": len(group), "points_local": [list(p) for p in sorted(group)]}
        (closed if len(group) >= 3 and all(len(adjacency[p]) == 2 for p in group) else opened).append(row)
    return closed, opened


def local_intersections(mesh, matrix, lo, span, box):
    mesh.calc_loop_triangles()
    triangles = [t for t in mesh.loop_triangles if any(inside(normalized(matrix @ mesh.vertices[i].co, lo, span), box) for i in t.vertices)]
    if len(triangles) > 20000:
        return {"checked": False, "reason": "local_triangle_budget_exceeded", "intersections": None}
    points = []
    indices = []
    for tri in triangles:
        indices.append(tuple(range(len(points), len(points) + 3)))
        points.extend(mesh.vertices[i].co.copy() for i in tri.vertices)
    if not points:
        return {"checked": False, "reason": "empty_patch", "intersections": None}
    tree = BVHTree.FromPolygons(points, indices, all_triangles=True)
    pairs = tree.overlap(tree)
    hits = set()
    epsilon = max((max((p.length for p in points), default=1)) * 1e-8, 1e-12)
    for a, b in pairs:
        if a >= b:
            continue
        va, vb = [points[i] for i in indices[a]], [points[i] for i in indices[b]]
        if {key(p) for p in va} & {key(p) for p in vb}:
            continue
        for source, target in ((va, vb), (vb, va)):
            for i in range(3):
                start, end = source[i], source[(i + 1) % 3]
                direction = end - start
                if direction.length <= epsilon:
                    continue
                hit = intersect_ray_tri(*target, direction, start, True)
                if hit is not None:
                    t = (hit - start).dot(direction) / direction.length_squared
                    if epsilon < t < 1.0 - epsilon:
                        hits.add((a, b))
    return {"checked": True, "intersections": len(hits), "triangle_count": len(triangles),
            "method": "local_BVH_and_nonadjacent_edge_triangle_intersections",
            "limitations": ["Coplanar overlap and adjacent-face foldover require a later specialized auditor."]}


def main():
    parser = argparse.ArgumentParser(description="Micro-valleys + measured local sections; never promotes")
    for name in ("input", "alpha", "plan", "research", "output", "report"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--depth-scale", type=float, required=True)
    args = parser.parse_args()
    if args.depth_scale not in (0.75, 1.0, 1.25):
        raise RuntimeError("PARAMETER_INVALID: sólo tres profundidades hermanas")
    if Path(args.output).resolve() in {Path(args.alpha).resolve(), Path(args.input).resolve()}:
        raise RuntimeError("PROTECTED_BASELINE: output no puede reemplazar Alpha ni working parent")
    if sha(args.alpha) != ALPHA_SHA:
        raise RuntimeError("PROTECTED_BASELINE: SHA Alpha inesperado")
    require_research(args.research, "fingers", technique="micro_valley_cut_local_sections")
    plan = json.loads(Path(args.plan).read_text())
    if plan["parent_sha"] != sha(args.input):
        raise RuntimeError("PARENT_MISMATCH: hermanos requieren working parent idéntico")
    if plan["reference_valleys"] != {"left": 2, "right": 0} or len(plan["targets"]) != 2:
        raise RuntimeError("DIAGNOSTIC_REQUIRED: plan no respeta asimetría")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    mesh = obj.data
    rotation = Matrix.Rotation(math.radians(-90), 4, "X")
    matrix = rotation @ obj.matrix_world
    lo, hi = (Vector(p) for p in plan["canonical_bounds"])
    span = hi - lo
    box = plan["scope_box"]
    hand_lo, hand_hi = (Vector(p) for p in plan["measured_hand_bounds_normalized"])
    uv_before = [layer.name for layer in mesh.uv_layers]
    outside_before = outside_fingerprint(mesh, matrix, lo, span, box)
    normals = normals_snapshot(mesh, matrix, lo, span, box)
    outside_vertices = Counter(key(v.co) for v in mesh.vertices if not inside(normalized(matrix @ v.co, lo, span), box))
    before = {"vertices": len(mesh.vertices), "faces": len(mesh.polygons)}
    # Exact local weld preserves UV per loop. No complete mesh split, no global merge.
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        selected = [v for v in bm.verts if inside(normalized(matrix @ v.co, lo, span), box)]
        bmesh.ops.remove_doubles(bm, verts=selected, dist=span.length * 1e-9)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    tip = float(hand_lo.x)
    hand_width = float(hand_hi.x - hand_lo.x)
    y_margin = (hand_hi.y - hand_lo.y) * 0.05
    ya, yb = lo.y + (hand_lo.y - y_margin) * span.y, lo.y + (hand_hi.y + y_margin) * span.y
    cuts = []
    for target in plan["targets"]:
        za, zb = target["z_range"]
        center, half = (za + zb) / 2, (zb - za) / 2
        depth = min(float(target["reference_depth_normalized"]) * args.depth_scale, box[3] - tip, hand_width * 0.58)
        if depth <= 0 or half <= 0:
            raise RuntimeError("SCOPE_UNSAFE: cutter sin profundidad o anchura")
        # Rounded U root keeps a narrow slot. Only depth changes among siblings.
        start = tip - hand_width * 0.05
        profile_norm = [(start, za), (tip + depth * 0.75, za),
                        (tip + depth, center - half * 0.35),
                        (tip + depth, center + half * 0.35),
                        (tip + depth * 0.75, zb), (start, zb)]
        profile = [(lo.x + x * span.x, lo.z + z * span.z) for x, z in profile_norm]
        cutter = prism(target["id"], profile, ya, yb, rotation.inverted())
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        modifier = obj.modifiers.new("COPOX_MicroValley", "BOOLEAN")
        modifier.operation, modifier.solver, modifier.object = "DIFFERENCE", "EXACT", cutter
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        finally:
            bpy.data.objects.remove(cutter, do_unlink=True)
        cuts.append({**target, "depth_normalized": depth, "depth_mm": depth * span.x * 1000,
                     "slot_height_mm": (zb - za) * span.z * 1000, "profile_normalized_xz": profile_norm})
    mesh = obj.data
    # Local cross-sections, not a global density increase. Prove cycles, do not infer them.
    rings = []
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        max_depth = max(row["depth_normalized"] for row in cuts)
        for label, fraction in (("distal", 0.15), ("middle", 0.40), ("proximal", 0.65), ("base", 0.90)):
            xnorm = tip + max_depth * fraction
            xworld = lo.x + xnorm * span.x
            local_plane = matrix.inverted() @ Vector((xworld, lo.y, lo.z))
            local_normal = matrix.to_3x3().transposed() @ Vector((1, 0, 0))
            faces = [f for f in bm.faces if all(inside(normalized(matrix @ v.co, lo, span), box) for v in f.verts)]
            edges = {e for f in faces for e in f.edges}
            verts = {v for e in edges for v in e.verts}
            if len(faces) > 20000:
                raise RuntimeError("TOPOLOGY_BUDGET_EXCEEDED: patch demasiado grande")
            result = bmesh.ops.bisect_plane(bm, geom=list(verts) + list(edges) + faces,
                                           dist=span.length * 1e-9, plane_co=local_plane,
                                           plane_no=local_normal, clear_inner=False, clear_outer=False)
            cut_edges = [e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
            closed, opened = cycles(cut_edges)
            rings.append({"section": label, "x_normalized": xnorm, "closed_cycles": closed, "open_components": opened})
        local_faces = [f for f in bm.faces if all(inside(normalized(matrix @ v.co, lo, span), box) for v in f.verts)]
        ngons = [f for f in local_faces if len(f.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
        local_faces = [f for f in bm.faces if all(inside(normalized(matrix @ v.co, lo, span), box) for v in f.verts)]
        bmesh.ops.recalc_face_normals(bm, faces=local_faces)
        degenerate = sum(f.calc_area() <= (span.length * 1e-10) ** 2 for f in local_faces)
        local_ngons = sum(len(f.verts) > 4 for f in local_faces)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    restored = restore_normals(mesh, normals)
    outside_after = outside_fingerprint(mesh, matrix, lo, span, box)
    remaining = Counter(key(v.co) for v in mesh.vertices if not inside(normalized(matrix @ v.co, lo, span), box))
    outside_exact = outside_before == outside_after and not (outside_vertices - remaining)
    intersections = local_intersections(mesh, matrix, lo, span, box)
    finite = all(math.isfinite(c) for v in mesh.vertices for c in v.co)
    loops_ready = all(len(row["closed_cycles"]) >= 3 and not row["open_components"] for row in rings)
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out.with_suffix(".blend")))
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB")
    report = {"mode": "micro_valley_cut_local_sections_v1", "parent_sha": plan["parent_sha"],
              "research_id": "fingers-micro-valleys-20261001", "depth_scale": args.depth_scale,
              "cuts": cuts, "before": before, "after": {"vertices": len(mesh.vertices), "faces": len(mesh.polygons)},
              "outside_scope_exact": outside_exact, "outside_face_fingerprint_matches": outside_before == outside_after,
              "outside_missing_vertices": sum((outside_vertices - remaining).values()), "outside_normals_restored": restored,
              "right_hand_mutated": False if outside_exact else None,
              "uv_layers_preserved": uv_before == [layer.name for layer in mesh.uv_layers],
              "local_degenerate_faces": degenerate, "local_ngons": local_ngons, "self_intersection_probe": intersections,
              "local_sections": rings, "loops_ready": loops_ready, "bridge_ready": False,
              "bridge_preparation": "local_section_cycles_recorded; palm boundary correspondence not verified",
              "rig_ready": False, "mesh_integrity": finite and not degenerate and intersections["checked"] and intersections["intersections"] == 0,
              "promotion_allowed": False, "promotion_executed": False}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    if sha(args.alpha) != ALPHA_SHA or sha(args.input) != plan["parent_sha"]:
        raise RuntimeError("PROTECTED_BASELINE: parent o Alpha cambiaron")
    print(json.dumps({k: report[k] for k in ("depth_scale", "outside_scope_exact", "mesh_integrity", "loops_ready", "local_ngons")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
