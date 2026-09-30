from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402


def _read(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _inside(point: Vector, boxes: list[list[float]], lo: Vector, span: Vector) -> bool:
    n = Vector(((point.x - lo.x) / span.x, (point.y - lo.y) / span.y, (point.z - lo.z) / span.z))
    for box in boxes:
        if box[0] <= n.x <= box[3] and box[1] <= n.y <= box[4] and box[2] <= n.z <= box[5]:
            return True
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Subdivide topología sólo dentro de una región anatómica")
    p.add_argument("--input", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--cuts", type=int, default=1)
    args = p.parse_args()

    cfg = _read(args.config)
    spec = (cfg.get("morph_regions") or {}).get(args.region) or {}
    boxes = spec.get("boxes") or []
    if not boxes:
        raise RuntimeError(f"{args.region} no tiene cajas de malla para subdivisión local")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("GLB sin mallas")
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    mesh = obj.data
    before_vertices = len(mesh.vertices)
    before_faces = len(mesh.polygons)

    # Blender importa este GLB con su eje longitudinal sobre -Y. Las cajas de COPOX,
    # en cambio, están definidas en el sistema canónico Z-up que usan las auditorías.
    # Usamos la misma corrección -90° X del renderer SÓLO para calcular selección;
    # no modificamos matrix_world ni persistimos esta rotación.
    canonical_rotation = Matrix.Rotation(math.radians(-90.0), 4, "X")
    canonical_matrix = canonical_rotation @ obj.matrix_world
    canonical_vertices = [canonical_matrix @ v.co for v in mesh.vertices]
    lo = Vector((
        min(v.x for v in canonical_vertices),
        min(v.y for v in canonical_vertices),
        min(v.z for v in canonical_vertices),
    ))
    hi = Vector((
        max(v.x for v in canonical_vertices),
        max(v.y for v in canonical_vertices),
        max(v.z for v in canonical_vertices),
    ))
    span = Vector((max(hi.x-lo.x, 1e-12), max(hi.y-lo.y, 1e-12), max(hi.z-lo.z, 1e-12)))

    before_bounds_local = [Vector(v) for v in obj.bound_box]

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    # Subdivision may replace BMVert handles. Snapshot values, never keep
    # references to BMesh elements across an operation that can remove them.
    original_coords = Counter(tuple(v.co) for v in bm.verts)
    original_surface = BVHTree.FromBMesh(bm)
    area_before = sum(f.calc_area() for f in bm.faces)
    uv_names_before = [layer.name for layer in mesh.uv_layers]
    selected_faces = [
        f for f in bm.faces
        if _inside(canonical_matrix @ f.calc_center_median(), boxes, lo, span)
    ]
    if not selected_faces:
        bm.free()
        raise RuntimeError(
            f"La región {args.region} no seleccionó caras en coordenadas canónicas; "
            f"bounds={tuple(round(x, 6) for x in (*lo, *hi))}"
        )
    selected_face_count = len(selected_faces)
    selected_edges = list({e for f in selected_faces for e in f.edges})
    selected_edge_count = len(selected_edges)
    bmesh.ops.subdivide_edges(bm, edges=selected_edges, cuts=max(1, args.cuts), smooth=0.0, use_grid_fill=True)
    current_coords = Counter(tuple(v.co) for v in bm.verts)
    missing_originals = original_coords - current_coords
    originals_unchanged = not missing_originals
    new_positions = set(current_coords) - set(original_coords)
    surface_distances = []
    for point in new_positions:
        nearest = original_surface.find_nearest(Vector(point))
        surface_distances.append(float(nearest[3]) if nearest[0] is not None else math.inf)
    max_surface_distance = max(surface_distances, default=0.0)
    area_after = sum(f.calc_area() for f in bm.faces)
    relative_area_delta = abs(area_after - area_before) / max(area_before, 1e-12)
    surface_unchanged = bool(max_surface_distance <= 1e-7 and relative_area_delta <= 1e-6)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    bpy.context.view_layer.update()

    after_vertices = len(mesh.vertices)
    after_faces = len(mesh.polygons)
    after_bounds_local = [Vector(v) for v in obj.bound_box]
    bounds_delta = max((a-b).length for a, b in zip(before_bounds_local, after_bounds_local))
    uv_layers = len(mesh.uv_layers)
    uv_layers_preserved = uv_names_before == [layer.name for layer in mesh.uv_layers]

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB")

    report = {
        "region": args.region,
        "object": obj.name,
        "selection_coordinates": "canonical_z_up_via_render_correction_only",
        "before": {"vertices": before_vertices, "faces": before_faces},
        "after": {"vertices": after_vertices, "faces": after_faces},
        "selected_faces": selected_face_count,
        "selected_edges": selected_edge_count,
        "uv_layers": uv_layers,
        "original_vertices_unchanged": bool(originals_unchanged),
        "original_vertex_check": "exact_coordinate_multiset_including_duplicate_positions",
        "missing_original_vertices": sum(missing_originals.values()),
        "surface_unchanged": surface_unchanged,
        "max_new_vertex_surface_distance": max_surface_distance,
        "relative_area_delta": relative_area_delta,
        "uv_layers_preserved": uv_layers_preserved,
        "bounds_delta": float(bounds_delta),
        "topology_density_increased": bool(after_vertices > before_vertices and after_faces > before_faces),
        "safe_geometry_regression": bool(originals_unchanged and surface_unchanged and uv_layers_preserved and bounds_delta <= 1e-9),
        "promotion_allowed": False,
        "learning": "La subdivisión sólo aumenta grados de libertad locales. La orientación canónica se usa para seleccionar, no se persiste. Cualquier sculpt posterior sigue sujeto a auditoría regional y render regression."
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
