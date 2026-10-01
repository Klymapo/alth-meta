from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402


def _read(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _inside(point: Vector, box: list[float], lo: Vector, span: Vector, pad: float = 0.0) -> bool:
    n = Vector(((point.x - lo.x) / span.x, (point.y - lo.y) / span.y, (point.z - lo.z) / span.z))
    return (
        box[0] - pad <= n.x <= box[3] + pad
        and box[1] - pad <= n.y <= box[4] + pad
        and box[2] - pad <= n.z <= box[5] + pad
    )


def _cube_mesh(name: str, corners: list[Vector]):
    mesh = bpy.data.meshes.new(name + "_mesh")
    verts = [tuple(v) for v in corners]
    faces = [
        (0, 1, 3, 2), (4, 6, 7, 5),
        (0, 4, 5, 1), (2, 3, 7, 6),
        (0, 2, 6, 4), (1, 5, 7, 3),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _canonical_corners(box: list[float], lo: Vector, span: Vector) -> list[Vector]:
    x0, y0, z0, x1, y1, z1 = box
    vals = []
    for x in (x0, x1):
        for y in (y0, y1):
            for z in (z0, z1):
                vals.append(Vector((lo.x + x * span.x, lo.y + y * span.y, lo.z + z * span.z)))
    # Reordenamos al layout esperado por _cube_mesh.
    return [vals[i] for i in (0, 4, 2, 6, 1, 5, 3, 7)]


def main() -> int:
    p = argparse.ArgumentParser(description="Talla huecos de dedos derivados de la referencia")
    p.add_argument("--input", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()

    plan = _read(args.plan)
    cutters = list(plan.get("cutters") or [])
    if not cutters:
        raise RuntimeError("Plan de dedos sin cutters")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("GLB sin mallas")
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    mesh = obj.data
    before_vertices = len(mesh.vertices)
    before_faces = len(mesh.polygons)
    uv_names_before = [layer.name for layer in mesh.uv_layers]
    material_count_before = len(mesh.materials)
    before_bounds = [Vector(v) for v in obj.bound_box]

    rotation = Matrix.Rotation(math.radians(-90.0), 4, "X")
    inv_rotation = rotation.inverted()
    canonical_matrix = rotation @ obj.matrix_world
    canonical_vertices = [canonical_matrix @ v.co for v in mesh.vertices]
    lo = Vector((min(v.x for v in canonical_vertices), min(v.y for v in canonical_vertices), min(v.z for v in canonical_vertices)))
    hi = Vector((max(v.x for v in canonical_vertices), max(v.y for v in canonical_vertices), max(v.z for v in canonical_vertices)))
    span = Vector((max(hi.x-lo.x, 1e-12), max(hi.y-lo.y, 1e-12), max(hi.z-lo.z, 1e-12)))

    # La exportación Alpha viene expandida por face-corner. Soldamos únicamente el
    # vecindario de los cutters para que el booleano tenga continuidad local; UV sigue
    # siendo dato por loop, así que seams fuera del scope no se tocan.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    local_verts = []
    boxes = [[float(x) for x in c["box_normalized"]] for c in cutters]
    for v in bm.verts:
        canonical = canonical_matrix @ v.co
        if any(_inside(canonical, box, lo, span, pad=0.008) for box in boxes):
            local_verts.append(v)
    before_local = len(local_verts)
    merge_distance = max(float(obj.dimensions.length) * 1e-8, 1e-10)
    if local_verts:
        bmesh.ops.remove_doubles(bm, verts=local_verts, dist=merge_distance)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    welded_vertices = before_vertices - len(mesh.vertices)

    applied: list[dict[str, object]] = []
    for item in cutters:
        box = [float(x) for x in item["box_normalized"]]
        canonical_corners = _canonical_corners(box, lo, span)
        # Blender opera en world Y-up; el plan vive en Z-up canónico.
        raw_world = [inv_rotation @ c for c in canonical_corners]
        cutter = _cube_mesh("COPOX_" + str(item["id"]), raw_world)
        cutter.display_type = "WIRE"

        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        modifier = obj.modifiers.new(name="COPOX_FingerGap", type="BOOLEAN")
        modifier.operation = "DIFFERENCE"
        modifier.solver = "EXACT"
        modifier.object = cutter
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            applied.append({"id": item["id"], "side": item["side"], "box_normalized": box, "applied": True})
        except Exception as exc:
            applied.append({"id": item["id"], "side": item["side"], "box_normalized": box, "applied": False, "error": str(exc)})
            raise
        finally:
            bpy.data.objects.remove(cutter, do_unlink=True)

    bpy.context.view_layer.update()
    after_vertices = len(mesh.vertices)
    after_faces = len(mesh.polygons)
    after_bounds = [Vector(v) for v in obj.bound_box]
    bounds_delta = max((a - b).length for a, b in zip(before_bounds, after_bounds))
    uv_names_after = [layer.name for layer in mesh.uv_layers]
    uv_layers_preserved = uv_names_before == uv_names_after
    material_count_after = len(mesh.materials)

    finite = all(math.isfinite(c) for v in mesh.vertices for c in v.co)
    booleans_ok = all(bool(x.get("applied")) for x in applied) and len(applied) == len(cutters)
    mesh_integrity = bool(finite and after_vertices > 0 and after_faces > 0 and booleans_ok)
    # Scope se garantiza constructivamente: todos los cutters fueron previamente
    # recortados a morph_regions.fingers y aquí no existen operaciones fuera de ellos
    # salvo weld exacto de posiciones coincidentes en un padding mínimo local.
    scope_safe = bool(booleans_ok and bounds_delta <= max(float(obj.dimensions.length) * 1e-7, 1e-9))

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB")

    report = {
        "mode": "finger_reference_gap_carve",
        "object": obj.name,
        "selection_coordinates": "canonical_z_up_via_render_correction_only",
        "reference_driven": bool(plan.get("reference_driven", False)),
        "invented_finger_count": bool(plan.get("invented_finger_count", True)),
        "cutters_planned": len(cutters),
        "cutters_applied": applied,
        "local_vertices_considered_for_weld": before_local,
        "welded_duplicate_vertices": int(welded_vertices),
        "merge_distance": float(merge_distance),
        "before": {"vertices": before_vertices, "faces": before_faces},
        "after": {"vertices": after_vertices, "faces": after_faces},
        "uv_layers_before": uv_names_before,
        "uv_layers_after": uv_names_after,
        "uv_layers_preserved": uv_layers_preserved,
        "material_slots_before": material_count_before,
        "material_slots_after": material_count_after,
        "bounds_delta": float(bounds_delta),
        "mesh_integrity": mesh_integrity,
        "scope_safe": scope_safe,
        "promotion_allowed": False,
        "learning": "Esta técnica talla separaciones internas que el contour-fit no podía crear. El gate M5 debe vetarla si side/3q, UV, muñeca/antebrazo o definición de dedos empeoran.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if mesh_integrity else 8


if __name__ == "__main__":
    raise SystemExit(main())
