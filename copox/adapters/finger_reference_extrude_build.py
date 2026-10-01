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


def _inside_norm(p: Vector, box: list[float]) -> bool:
    return box[0] <= p.x <= box[3] and box[1] <= p.y <= box[4] and box[2] <= p.z <= box[5]


def _ring_faces(offset_a: int, offset_b: int) -> list[tuple[int, int, int, int]]:
    return [
        (offset_a + 0, offset_a + 1, offset_b + 1, offset_b + 0),
        (offset_a + 1, offset_a + 2, offset_b + 2, offset_b + 1),
        (offset_a + 2, offset_a + 3, offset_b + 3, offset_b + 2),
        (offset_a + 3, offset_a + 0, offset_b + 0, offset_b + 3),
    ]


def main() -> int:
    p = argparse.ArgumentParser(description="Prototipo learning-only: reemplaza zona distal por dedos extruidos desde referencia")
    p.add_argument("--input", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--segments", type=int, default=3)
    p.add_argument("--depth-scale", type=float, default=0.82)
    p.add_argument("--tip-scale", type=float, default=0.82)
    p.add_argument("--length-scale", type=float, default=1.0)
    p.add_argument("--delete-distal-fraction", type=float, default=1.0)
    args = p.parse_args()

    if args.segments < 2 or args.segments > 5:
        raise ValueError("segments debe estar en 2..5")
    if not (0.45 <= args.depth_scale <= 1.15):
        raise ValueError("depth-scale fuera de rango")
    if not (0.55 <= args.tip_scale <= 1.0):
        raise ValueError("tip-scale fuera de rango")
    if not (0.80 <= args.length_scale <= 1.10):
        raise ValueError("length-scale fuera de rango")
    if not (0.35 <= args.delete_distal_fraction <= 1.0):
        raise ValueError("delete-distal-fraction fuera de rango")

    plan = _read(args.plan)
    if not plan.get("research_prototype") or plan.get("promotion_allowed"):
        raise RuntimeError("El plan debe ser learning-only")
    digits = list(plan.get("digits") or [])
    if len(digits) < 2:
        raise RuntimeError("Plan sin suficientes bandas visibles")
    box = [float(v) for v in plan["finger_morph_box"]]
    side = str(plan["side"])

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
    canonical_vertices = [canonical_matrix @ v.co for v in mesh.vertices]
    lo = Vector((min(v.x for v in canonical_vertices), min(v.y for v in canonical_vertices), min(v.z for v in canonical_vertices)))
    hi = Vector((max(v.x for v in canonical_vertices), max(v.y for v in canonical_vertices), max(v.z for v in canonical_vertices)))
    span = Vector((max(hi.x-lo.x, 1e-12), max(hi.y-lo.y, 1e-12), max(hi.z-lo.z, 1e-12)))

    def norm_point(c: Vector) -> Vector:
        return Vector(((c.x-lo.x)/span.x, (c.y-lo.y)/span.y, (c.z-lo.z)/span.z))

    sampled_y = []
    for c in canonical_vertices:
        n = norm_point(c)
        if box[0] <= n.x <= box[3] and box[2] <= n.z <= box[5]:
            sampled_y.append(float(c.y))
    if len(sampled_y) >= 8:
        y_lo, y_hi = np.quantile(np.asarray(sampled_y, dtype=float), [0.12, 0.88])
    else:
        y_lo = float(lo.y + box[1] * span.y)
        y_hi = float(lo.y + box[4] * span.y)
    y_center = (float(y_lo) + float(y_hi)) * 0.5
    half_depth = max((float(y_hi) - float(y_lo)) * 0.5 * float(args.depth_scale), float(span.y) * 0.008)

    full_length = max(float(box[3] - box[0]), 1e-9)
    distal_fraction = float(args.delete_distal_fraction)
    if side == "left":
        delete_cutoff = float(box[0] + full_length * distal_fraction)
    else:
        delete_cutoff = float(box[3] - full_length * distal_fraction)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    delete_faces = []
    for f in bm.faces:
        c = canonical_matrix @ f.calc_center_median()
        n = norm_point(c)
        in_box = _inside_norm(n, box)
        in_distal_slice = (n.x <= delete_cutoff) if side == "left" else (n.x >= delete_cutoff)
        if in_box and in_distal_slice:
            delete_faces.append(f)
    deleted_faces = len(delete_faces)
    if delete_faces:
        bmesh.ops.delete(bm, geom=delete_faces, context="FACES")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    proxy_verts: list[tuple[float, float, float]] = []
    proxy_faces: list[tuple[int, ...]] = []
    digit_reports = []

    for digit in digits:
        za_n, zb_n = [float(v) for v in digit["z_range_normalized"]]
        if zb_n <= za_n:
            continue
        z_center = float(lo.z + ((za_n + zb_n) * 0.5) * span.z)
        base_half_h = max(float((zb_n - za_n) * span.z * 0.5 * 0.92), float(span.z) * 0.0015)
        frac = float(digit.get("distal_fraction", 1.0))
        length_n = float(np.clip(full_length * frac * float(args.length_scale), full_length * 0.30, full_length * 1.03))
        if side == "left":
            base_n = float(box[3] - full_length * 0.03)
            tip_n = max(float(box[0] - full_length * 0.02), base_n - length_n)
        else:
            base_n = float(box[0] + full_length * 0.03)
            tip_n = min(float(box[3] + full_length * 0.02), base_n + length_n)
        base_x = float(lo.x + base_n * span.x)
        tip_x = float(lo.x + tip_n * span.x)

        first = len(proxy_verts)
        rings = int(args.segments) + 1
        for ring in range(rings):
            t = ring / max(1, rings - 1)
            x = base_x + (tip_x - base_x) * t
            taper = 1.0 + (float(args.tip_scale) - 1.0) * t
            hz = base_half_h * taper
            hy = half_depth * taper
            canonical_ring = [
                Vector((x, y_center - hy, z_center - hz)), Vector((x, y_center + hy, z_center - hz)),
                Vector((x, y_center + hy, z_center + hz)), Vector((x, y_center - hy, z_center + hz)),
            ]
            for c in canonical_ring:
                raw_world = inv_rotation @ c
                local = inv_obj @ raw_world
                proxy_verts.append((float(local.x), float(local.y), float(local.z)))
        proxy_faces.append((first + 0, first + 3, first + 2, first + 1))
        for ring in range(rings - 1):
            proxy_faces.extend(_ring_faces(first + ring * 4, first + (ring + 1) * 4))
        end = first + (rings - 1) * 4
        proxy_faces.append((end + 0, end + 1, end + 2, end + 3))
        digit_reports.append({"id": digit["id"], "rings": rings, "segments": int(args.segments), "base_x_normalized": base_n, "tip_x_normalized": tip_n, "z_range_normalized": [za_n, zb_n], "distal_fraction": frac})

    if len(digit_reports) < 2:
        raise RuntimeError("No se construyeron suficientes dedos")

    proxy_mesh = bpy.data.meshes.new("COPOX_ReferenceExtrudedDigits_mesh")
    proxy_mesh.from_pydata(proxy_verts, [], proxy_faces)
    proxy_mesh.update()
    proxy_obj = bpy.data.objects.new("COPOX_ReferenceExtrudedDigits", proxy_mesh)
    bpy.context.scene.collection.objects.link(proxy_obj)
    proxy_obj.matrix_world = obj.matrix_world.copy()
    if len(mesh.materials):
        proxy_mesh.materials.append(mesh.materials[0])
    for poly in proxy_mesh.polygons:
        poly.use_smooth = True
    bpy.context.view_layer.update()

    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB")

    finite = all(math.isfinite(c) for v in proxy_mesh.vertices for c in v.co)
    result = {
        "mode": "reference_visible_digit_extrusion_build_v2",
        "research_prototype": True,
        "reference_driven": bool(plan.get("reference_driven")),
        "invented_finger_count": bool(plan.get("invented_finger_count")),
        "side": side,
        "digits_built": len(digit_reports),
        "digit_reports": digit_reports,
        "loop_rings_per_digit": int(args.segments) + 1,
        "deleted_baseline_faces": int(deleted_faces),
        "delete_distal_fraction": distal_fraction,
        "delete_cutoff_normalized": delete_cutoff,
        "baseline_vertices_before": int(before_vertices),
        "baseline_faces_before": int(before_faces),
        "baseline_faces_after_distal_delete": int(len(mesh.polygons)),
        "proxy_vertices": int(len(proxy_mesh.vertices)),
        "proxy_faces": int(len(proxy_mesh.polygons)),
        "sampled_depth_vertices": int(len(sampled_y)),
        "depth_scale": float(args.depth_scale),
        "tip_scale": float(args.tip_scale),
        "length_scale": float(args.length_scale),
        "mesh_integrity": bool(finite and len(proxy_mesh.vertices) > 0 and len(proxy_mesh.polygons) > 0),
        "bridge_to_palm_validated": False,
        "scope_safe": False,
        "promotion_allowed": False,
        "learning": "El borrado distal ahora puede acotarse sin cambiar la extrusión ni las bandas derivadas de referencia. La unión final a palma sigue pendiente.",
    }
    Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"digits_built": result["digits_built"], "loop_rings_per_digit": result["loop_rings_per_digit"], "deleted_baseline_faces": result["deleted_baseline_faces"], "delete_distal_fraction": distal_fraction, "mesh_integrity": result["mesh_integrity"]}, ensure_ascii=False))
    return 0 if result["mesh_integrity"] else 8


if __name__ == "__main__":
    raise SystemExit(main())
