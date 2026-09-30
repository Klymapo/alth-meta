from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402


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
    before_bounds = [Vector(v) for v in obj.bound_box]
    lo = Vector((min(v.x for v in before_bounds), min(v.y for v in before_bounds), min(v.z for v in before_bounds)))
    hi = Vector((max(v.x for v in before_bounds), max(v.y for v in before_bounds), max(v.z for v in before_bounds)))
    span = Vector((max(hi.x-lo.x, 1e-12), max(hi.y-lo.y, 1e-12), max(hi.z-lo.z, 1e-12)))

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    original_verts = list(bm.verts)
    original_coords = [v.co.copy() for v in original_verts]
    selected_faces = [f for f in bm.faces if _inside(f.calc_center_median(), boxes, lo, span)]
    if not selected_faces:
        bm.free()
        raise RuntimeError(f"La región {args.region} no seleccionó caras")
    selected_edges = list({e for f in selected_faces for e in f.edges})
    bmesh.ops.subdivide_edges(bm, edges=selected_edges, cuts=max(1, args.cuts), use_grid_fill=True)
    originals_unchanged = all((v.co - old).length <= 1e-12 for v, old in zip(original_verts, original_coords))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    after_vertices = len(mesh.vertices)
    after_faces = len(mesh.polygons)
    after_bounds = [Vector(v) for v in obj.bound_box]
    bounds_delta = max((a-b).length for a, b in zip(before_bounds, after_bounds))
    uv_layers = len(mesh.uv_layers)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB")

    report = {
        "region": args.region,
        "object": obj.name,
        "before": {"vertices": before_vertices, "faces": before_faces},
        "after": {"vertices": after_vertices, "faces": after_faces},
        "selected_faces": len(selected_faces),
        "selected_edges": len(selected_edges),
        "uv_layers": uv_layers,
        "original_vertices_unchanged": bool(originals_unchanged),
        "bounds_delta": float(bounds_delta),
        "topology_density_increased": bool(after_vertices > before_vertices and after_faces > before_faces),
        "safe_geometry_regression": bool(originals_unchanged and bounds_delta <= 1e-9),
        "promotion_allowed": False,
        "learning": "Si la región requiere más detalle geométrico, subdividir localmente crea grados de libertad sin alterar la forma base; cualquier sculpt posterior sigue sujeto a auditoría regional y render regression."
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
