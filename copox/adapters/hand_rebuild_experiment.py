from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector

CANONICAL_ROT = Matrix.Rotation(math.radians(-90.0), 4, "X")
RAW_ROT = CANONICAL_ROT.inverted()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_bounds(obj):
    matrix = CANONICAL_ROT @ obj.matrix_world
    pts = [matrix @ v.co for v in obj.data.vertices]
    lo = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
    hi = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
    span = Vector((max(hi.x - lo.x, 1e-9), max(hi.y - lo.y, 1e-9), max(hi.z - lo.z, 1e-9)))
    return lo, hi, span


def add_box_canonical(name, center, dims, material, bevel=0.0, angle_y=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    canonical_transform = Matrix.Translation(Vector(center)) @ Matrix.Rotation(angle_y, 4, "Y")
    obj.matrix_world = RAW_ROT @ canonical_transform
    if material:
        obj.data.materials.append(material)
    if bevel > 0.0:
        mod = obj.modifiers.new("COPOX_joint_softness", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        obj.select_set(False)
    return obj


def delete_distal_hand_geometry(meshes, boxes, lo, span):
    removed = []
    for obj in meshes:
        if not obj.data.vertices:
            continue
        matrix = CANONICAL_ROT @ obj.matrix_world
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        doomed = []
        for v in bm.verts:
            c = matrix @ v.co
            n = Vector(((c.x - lo.x) / span.x, (c.y - lo.y) / span.y, (c.z - lo.z) / span.z))
            for box in boxes:
                x0, y0, z0, x1, y1, z1 = [float(x) for x in box]
                side = -1 if (x0 + x1) * 0.5 < 0.5 else 1
                width = x1 - x0
                # Conserva aproximadamente el 22% proximal para no cortar el antebrazo.
                if side < 0:
                    in_x = x0 - 0.004 <= n.x <= x0 + width * 0.78
                else:
                    in_x = x1 - width * 0.78 <= n.x <= x1 + 0.004
                in_y = y0 - 0.01 <= n.y <= y1 + 0.01
                in_z = z0 - 0.01 <= n.z <= z1 + 0.01
                if in_x and in_y and in_z:
                    doomed.append(v)
                    break
        count = len(set(doomed))
        if count:
            bmesh.ops.delete(bm, geom=list(set(doomed)), context="VERTS")
            bm.to_mesh(obj.data)
            obj.data.update()
        bm.free()
        if count:
            removed.append({"object": obj.name, "vertices_removed": count})
    return removed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--slot", type=int, default=1)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = p.parse_args(argv)
    cfg = read(args.config)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    body = max(meshes, key=lambda o: len(o.data.polygons))
    lo, hi, span = canonical_bounds(body)

    hand_boxes = cfg["morph_regions"]["hands"]["boxes"]
    finger_boxes = cfg["morph_regions"]["fingers"]["boxes"]
    removed = delete_distal_hand_geometry(meshes, hand_boxes, lo, span)

    material = body.data.materials[0] if body.data.materials else bpy.data.materials.new("TheoHand")
    created = []
    segments = [2, 3, 3][max(0, min(args.slot - 1, 2))]
    # La variación sólo cambia resolución/segmentación, no la posición anatómica.
    roundness = [0.16, 0.20, 0.24][max(0, min(args.slot - 1, 2))]

    for index, (hand_box, finger_box) in enumerate(zip(hand_boxes[:2], finger_boxes[:2])):
        hx0, hy0, hz0, hx1, hy1, hz1 = [float(x) for x in hand_box]
        fx0, fy0, fz0, fx1, fy1, fz1 = [float(x) for x in finger_box]
        side = -1 if (hx0 + hx1) * 0.5 < 0.5 else 1

        xa, xb = lo.x + hx0 * span.x, lo.x + hx1 * span.x
        ya, yb = lo.y + hy0 * span.y, lo.y + hy1 * span.y
        za, zb = lo.z + hz0 * span.z, lo.z + hz1 * span.z
        hand_len = abs(xb - xa)
        hand_depth = abs(yb - ya)
        hand_height = abs(zb - za)
        proximal = max(xa, xb) if side < 0 else min(xa, xb)

        palm_len = hand_len * 0.48
        palm_depth = hand_depth * 0.58
        palm_height = hand_height * 0.66
        palm_center = Vector((
            proximal + side * palm_len * 0.52,
            (ya + yb) * 0.5,
            (za + zb) * 0.5,
        ))
        palm = add_box_canonical(
            f"COPOX_Palm_{index}", palm_center, (palm_len, palm_depth, palm_height), material,
            bevel=min(palm_height, palm_len) * roundness,
        )
        created.append(palm.name)

        fxa, fxb = lo.x + fx0 * span.x, lo.x + fx1 * span.x
        fza, fzb = lo.z + fz0 * span.z, lo.z + fz1 * span.z
        finger_max_len = abs(fxb - fxa) * 0.92
        usable_height = abs(fzb - fza) * 0.62
        center_z = (fza + fzb) * 0.5
        z_positions = [center_z + usable_height * q for q in (-0.36, -0.12, 0.12, 0.36)]
        # Sólo relaciones estilizadas para esta prueba de técnica; no se aceptan como medidas finales.
        length_factors = (0.80, 1.00, 0.93, 0.74)
        finger_thickness = max(hand_height * 0.095, 1e-5)
        finger_depth = palm_depth * 0.72
        palm_distal_x = palm_center.x + side * palm_len * 0.50

        for digit, (factor, zc) in enumerate(zip(length_factors, z_positions)):
            total_len = finger_max_len * factor
            seg_len = total_len / segments
            for seg in range(segments):
                cx = palm_distal_x + side * seg_len * (seg + 0.5)
                obj = add_box_canonical(
                    f"COPOX_Finger_{index}_{digit}_{seg}",
                    (cx, palm_center.y, zc),
                    (seg_len * 1.04, finger_depth, finger_thickness),
                    material,
                    bevel=min(seg_len, finger_thickness) * roundness,
                )
                created.append(obj.name)

        thumb_len = finger_max_len * 0.48
        thumb_center = Vector((
            palm_center.x + side * palm_len * 0.18,
            palm_center.y,
            center_z - usable_height * 0.50,
        ))
        thumb = add_box_canonical(
            f"COPOX_Thumb_{index}",
            thumb_center,
            (thumb_len, finger_depth * 0.88, finger_thickness * 1.15),
            material,
            bevel=finger_thickness * roundness,
            angle_y=side * math.radians(24.0),
        )
        created.append(thumb.name)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB")

    report = {
        "mode": "web_research_hand_rebuild_experiment_v2",
        "slot": args.slot,
        "promotion_allowed": False,
        "canonical_coordinates": "z_up_via_minus_90_x",
        "replaces_distal_hand": True,
        "segments_per_finger": segments,
        "technique": [
            "distal hand replacement",
            "palm primitive",
            "four separate finger rays",
            "segmented joint-ready digits",
            "thumb independent",
        ],
        "removed_geometry": removed,
        "created_objects": created,
        "created_count": len(created),
        "note": "Experimento de técnica, no candidato de promoción. Las proporciones finales deberán derivarse de referencia multivista antes de bridge/rig.",
    }
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
