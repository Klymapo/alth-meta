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
from copox.adapters.finger_connected_profile import DEPTH_SCALES, SECTION_FRACTIONS, notch_x

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
        if all(inside(normalized(matrix @ mesh.vertices[i].co, lo, span), box) for i in poly.vertices):
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



def face_rows(mesh):
    uv = mesh.uv_layers.active
    rows = []
    for poly in mesh.polygons:
        corners = [(key(mesh.vertices[mesh.loops[li].vertex_index].co),
                    key(uv.data[li].uv) if uv else ()) for li in poly.loop_indices]
        rows.append((tuple(sorted(corners)), poly.material_index, poly.use_smooth))
    return rows


def protected_rows(mesh, matrix, lo, span, box):
    # Protect crossing faces as well, not just faces with every corner outside.
    rows = face_rows(mesh)
    return Counter(rows[p.index] for p in mesh.polygons
                   if not all(inside(normalized(matrix @ mesh.vertices[i].co, lo, span), box) for i in p.vertices))


def bisect_local(bm, layer, matrix, lo, span, axis, normalized_value, locked_edges):
    faces = [f for f in bm.faces if f[layer]]
    if len(faces) > 20000:
        raise RuntimeError("TOPOLOGY_BUDGET_EXCEEDED: local patch >20000 faces")
    face_set = set(faces)
    # Bisect splits radial faces too. Never pass an edge incident to a protected face.
    edges = {e for f in faces for e in f.edges if all(other in face_set for other in e.link_faces)
             and tuple(sorted(key(v.co) for v in e.verts)) not in locked_edges}
    verts = {v for e in edges for v in e.verts}
    point = lo.copy()
    point[axis] += normalized_value * span[axis]
    normal = Vector(tuple(1. if i == axis else 0. for i in range(3)))
    bmesh.ops.bisect_plane(bm, geom=list(verts) + list(edges) + faces,
        dist=span.length * 1e-9, plane_co=matrix.inverted() @ point,
        plane_no=matrix.to_3x3().transposed() @ normal, use_snap_center=False,
        clear_inner=False, clear_outer=False)


def main():
    parser = argparse.ArgumentParser(description="Connected reference-driven local notch; no Boolean or promotion")
    for name in ("input", "alpha", "plan", "research", "output", "report"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--depth-scale", type=float, required=True)
    args = parser.parse_args()
    if args.depth_scale not in DEPTH_SCALES:
        raise RuntimeError("PARAMETER_INVALID: exactly three researched sibling depths")
    if Path(args.output).resolve() in {Path(args.alpha).resolve(), Path(args.input).resolve()}:
        raise RuntimeError("PROTECTED_BASELINE: output cannot replace Alpha or parent")
    if sha(args.alpha) != ALPHA_SHA:
        raise RuntimeError("PROTECTED_BASELINE: unexpected Alpha SHA")
    for technique in ("pose_preserving_reference_notch_sections",):
        require_research(args.research, "fingers", technique=technique)
    plan = json.loads(Path(args.plan).read_text())
    if plan["parent_sha"] != sha(args.input):
        raise RuntimeError("PARENT_MISMATCH: expected immutable sibling parent")
    if plan["reference_valleys"] != {"left": 2, "right": 0} or len(plan["targets"]) != 2:
        raise RuntimeError("DIAGNOSTIC_REQUIRED: reference asymmetry missing")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    obj = max((o for o in bpy.context.scene.objects if o.type == "MESH"), key=lambda o: len(o.data.polygons))
    mesh = obj.data
    matrix = Matrix.Rotation(math.radians(-90), 4, "X") @ obj.matrix_world
    inverse = matrix.inverted()
    lo, hi = (Vector(p) for p in plan["canonical_bounds"])
    span, box = hi - lo, plan["scope_box"]
    uv_before = [layer.name for layer in mesh.uv_layers]
    protected = protected_rows(mesh, matrix, lo, span, box)
    protected_vertex_keys = {key(mesh.vertices[i].co) for p in mesh.polygons
        if not all(inside(normalized(matrix @ mesh.vertices[j].co, lo, span), box) for j in p.vertices)
        for i in p.vertices}
    locked_edges = {tuple(sorted((key(mesh.vertices[mesh.loops[li].vertex_index].co),
                                   key(mesh.vertices[mesh.loops[poly.loop_indices[(i+1)%len(poly.loop_indices)]].vertex_index].co))))
                    for poly in mesh.polygons
                    if not all(inside(normalized(matrix @ mesh.vertices[j].co, lo, span), box) for j in poly.vertices)
                    for i, li in enumerate(poly.loop_indices)}
    outside_vertices = Counter(key(v.co) for v in mesh.vertices if key(v.co) in protected_vertex_keys or not inside(normalized(matrix @ v.co, lo, span), box))
    normals = normals_snapshot(mesh, matrix, lo, span, box)
    before = {"vertices": len(mesh.vertices), "faces": len(mesh.polygons)}
    other_meshes = {o.name: Counter(face_rows(o.data)) for o in bpy.context.scene.objects if o.type == "MESH" and o != obj}
    cuts, rings = [], []
    contour_moved = 0
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        layer = bm.faces.layers.int.new("copox_local_patch")
        for face in bm.faces:
            face[layer] = int(all(inside(normalized(matrix @ v.co, lo, span), box) for v in face.verts))
        selected = [v for v in bm.verts if v.link_faces and all(f[layer] for f in v.link_faces) and key(v.co) not in protected_vertex_keys]
        bmesh.ops.remove_doubles(bm, verts=selected, dist=span.length * 1e-9)
        tris = [f for f in bm.faces if f[layer] and len(f.verts) == 3]
        if tris:
            # Only coplanar compatible faces; delimit UV/material/shading boundaries.
            bmesh.ops.join_triangles(bm, faces=tris, cmp_seam=True, cmp_sharp=True, cmp_uvs=True,
                cmp_vcols=True, cmp_materials=True, angle_face_threshold=1e-5, angle_shape_threshold=math.pi)
        current = [normalized(matrix @ v.co, lo, span) for v in bm.verts if v.link_faces and all(f[layer] for f in v.link_faces) and key(v.co) not in protected_vertex_keys]
        zmin, zmax = min(p.z for p in current), max(p.z for p in current)
        xmin = min(p.x for p in current)
        # A small fixed common grid prepares interpolation; all dimensions are measured.
        for fraction in (.2, .4, .6, .8):
            bisect_local(bm, layer, matrix, lo, span, 2, zmin + (zmax - zmin) * fraction, locked_edges)
            bisect_local(bm, layer, matrix, lo, span, 0, xmin + (box[3] - xmin) * fraction, locked_edges)
        # Keep Valley c01 pose; no contour warp is executed in this researched round.
        for target in plan["targets"]:
            za, zb = target["z_range"]
            for fraction in (0., .2, .4, .6, .8, 1.):
                bisect_local(bm, layer, matrix, lo, span, 2, za + (zb - za) * fraction, locked_edges)
        for target in plan["targets"]:
            za, zb = target["z_range"]
            active = [normalized(matrix @ v.co, lo, span) for v in bm.verts
                      if v.link_faces and all(f[layer] for f in v.link_faces) and key(v.co) not in protected_vertex_keys
                      and za <= normalized(matrix @ v.co, lo, span).z <= zb]
            if not active:
                raise RuntimeError("DIAGNOSTIC_REQUIRED: no volume in pose-preserving mapped valley")
            tip = min(p.x for p in active)
            measured_depth = target["reference_depth_normalized"]
            support = min(box[3], tip + measured_depth * max(DEPTH_SCALES) / .85 * 1.20)
            if measured_depth <= 0:
                raise RuntimeError("DIAGNOSTIC_REQUIRED: reference-derived valley depth is invalid")
            depth = min(measured_depth * args.depth_scale, (support - tip) * .85)
            moved = 0
            for vert in bm.verts:
                if not vert.link_faces or not all(f[layer] for f in vert.link_faces) or key(vert.co) in protected_vertex_keys:
                    continue
                point = normalized(matrix @ vert.co, lo, span)
                if not za < point.z < zb:
                    continue
                new_x = notch_x(point.x, point.z, tip=tip, support_root=support, depth=depth, z_range=(za, zb))
                if abs(new_x - point.x) > 1e-12:
                    point.x = new_x
                    vert.co = inverse @ Vector(tuple(lo[i] + point[i] * span[i] for i in range(3)))
                    moved += 1
            cuts.append({**target, "distal_x": tip, "support_root_x": support, "depth_normalized": depth,
                "depth_mm": depth * span.x * 1000, "slot_height_mm": (zb - za) * span.z * 1000,
                "root_x": tip + depth, "moved_vertices": moved, "monotone_x_derivative_min": 1-depth/(support-tip)})
        # Each visible digit gets its own length and four measured section planes.
        ordered = sorted(cuts, key=lambda row: sum(row["z_range"]) / 2)
        centers = [sum(row["z_range"]) / 2 for row in ordered]
        bands = [(box[2], centers[0]), (centers[0], centers[1]), (centers[1], box[5])]
        sections = []
        for digit, band in enumerate(bands):
            points = [normalized(matrix @ v.co, lo, span) for v in bm.verts if v.link_faces and all(f[layer] for f in v.link_faces) and key(v.co) not in protected_vertex_keys
                      and band[0] <= normalized(matrix @ v.co, lo, span).z <= band[1]]
            adjacent = [ordered[0]] if digit == 0 else [ordered[1]] if digit == 2 else ordered
            tip = min(p.x for p in points)
            root = min(row["root_x"] for row in adjacent)
            if root <= tip:
                sections.append({"digit": digit + 1, "section": "missing_length", "x_normalized": None,
                                 "closed_cycles": [], "open_components": [], "verified": False})
                continue
            for label, fraction in SECTION_FRACTIONS:
                x = tip + (root - tip) * fraction
                bisect_local(bm, layer, matrix, lo, span, 0, x, locked_edges)
                sections.append({"digit": digit + 1, "section": label, "x_normalized": x, "z_band": band})
        epsilon = 2e-6
        for row in sections:
            if row["x_normalized"] is None:
                rings.append(row)
                continue
            edges = [e for e in bm.edges if all(f[layer] for f in e.link_faces) and len(e.link_faces) == 2
                     and all(abs(normalized(matrix @ v.co, lo, span).x - row["x_normalized"]) < epsilon for v in e.verts)]
            closed, opened = cycles(edges)
            def in_digit(cycle):
                points = [normalized(matrix @ Vector(p), lo, span) for p in cycle["points_local"]]
                return all(row["z_band"][0] + epsilon < p.z < row["z_band"][1] - epsilon for p in points)
            matched = [cycle for cycle in closed if in_digit(cycle)]
            rings.append({**row, "closed_cycles": matched, "open_components": opened, "other_closed_cycles": len(closed)-len(matched),
                          "verified": len(matched) == 1 and not opened})
        local_faces = [f for f in bm.faces if f[layer]]
        ngons = [f for f in local_faces if len(f.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
        local_faces = [f for f in bm.faces if f[layer]]
        bmesh.ops.recalc_face_normals(bm, faces=local_faces)
        degenerate = sum(f.calc_area() <= (span.length * 1e-10) ** 2 for f in local_faces)
        quads = sum(len(f.verts) == 4 for f in local_faces)
        tris_count = sum(len(f.verts) == 3 for f in local_faces)
        local_ngons = sum(len(f.verts) > 4 for f in local_faces)
        # Do not leave experimental custom layers in transport.
        bm.faces.layers.int.remove(layer)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    restored = restore_normals(mesh, normals)
    missing_faces = protected - Counter(face_rows(mesh))
    remaining = Counter(key(v.co) for v in mesh.vertices)
    compacted_duplicates = outside_vertices - remaining
    missing_vertex_positions = set(outside_vertices) - set(remaining)
    other_exact = all(Counter(face_rows(bpy.data.objects[name].data)) == rows for name, rows in other_meshes.items())
    outside_exact = not missing_faces and not missing_vertex_positions and other_exact
    intersections = local_intersections(mesh, matrix, lo, span, box)
    finite = all(math.isfinite(c) for v in mesh.vertices for c in v.co)
    loops_ready = len(rings) == 12 and all(row["verified"] for row in rings)
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out.with_suffix(".blend")))
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB")
    report = {"mode": "pose_preserving_reference_notch_sections_v3", "parent_sha": plan["parent_sha"],
        "research_id": "fingers-pose-preserving-micro-valleys-20261001", "depth_scale": args.depth_scale,
        "contour_warp": {"executed": False, "source": "pose_preserved_Valley_c01", "moved_vertices": 0,
                         "common_to_all_siblings": True, "y_thickness_unchanged": True},
        "cuts": cuts, "before": before, "after": {"vertices": len(mesh.vertices), "faces": len(mesh.polygons)},
        "outside_scope_exact": outside_exact, "outside_face_fingerprint_matches": not missing_faces,
        "outside_missing_faces": sum(missing_faces.values()), "outside_missing_vertices": len(missing_vertex_positions),
        "compacted_corner_duplicates": sum(compacted_duplicates.values()),
        "protected_vertex_positions": len(protected_vertex_keys), "locked_geometric_edges": len(locked_edges),
        "outside_normals_restored": restored, "other_objects_exact": other_exact, "right_hand_mutated": False if outside_exact else None,
        "uv_layers_preserved": uv_before == [layer.name for layer in mesh.uv_layers], "local_degenerate_faces": degenerate,
        "local_ngons": local_ngons, "local_quads": quads, "local_triangles": tris_count, "all_quads": tris_count == 0,
        "self_intersection_probe": intersections, "local_sections": rings, "loops_ready": loops_ready,
        "bridge_ready": False, "bridge_preparation": "per_digit_sections_recorded; palm correspondence not verified",
        "rig_ready": False, "mesh_integrity": finite and not degenerate and intersections["checked"] and intersections["intersections"] == 0,
        "promotion_allowed": False, "promotion_executed": False}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    if sha(args.alpha) != ALPHA_SHA or sha(args.input) != plan["parent_sha"]:
        raise RuntimeError("PROTECTED_BASELINE: Alpha or parent changed")
    print("COPOX_MUTATION:" + json.dumps({k: report[k] for k in ("mode", "outside_scope_exact", "outside_missing_faces", "outside_missing_vertices", "mesh_integrity", "loops_ready", "local_quads", "local_triangles")}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
