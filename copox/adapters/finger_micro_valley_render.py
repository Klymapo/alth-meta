from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bpy
from mathutils import Matrix, Vector
import alth

VIEWS = {"front": (0, -1, 0), "side": (1, 0, 0), "back": (0, 1, 0), "threeq": (0.62, -0.72, 0.32)}


def camera(name, lower, upper, direction):
    center = (lower + upper) / 2
    radius = max((upper - lower).length, 1.0)
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = radius * 1.12
    data.clip_start, data.clip_end = 0.1, radius * 40
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = center + Vector(direction).normalized() * radius * 10
    obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def main():
    p = argparse.ArgumentParser()
    for name in ("input", "config", "output-dir"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    alth.nueva_escena()
    bpy.ops.import_scene.gltf(filepath=str(Path(a.input).resolve()))
    imported = list(bpy.context.scene.objects)
    # ALTH cameras/light operate in mm. GLB transport is metres and Y-up.
    correction = Matrix.Scale(1000.0, 4) @ Matrix.Rotation(math.radians(-90), 4, "X")
    for root in [o for o in imported if o.parent is None]:
        root.matrix_world = correction @ root.matrix_world
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("EVIDENCE_INCOMPLETE: GLB sin mallas")
    dominant = max(meshes, key=lambda o: len(o.data.polygons))
    points = [dominant.matrix_world @ v.co for v in dominant.data.vertices]
    lo = Vector(tuple(min(pt[i] for pt in points) for i in range(3)))
    hi = Vector(tuple(max(pt[i] for pt in points) for i in range(3)))
    span = hi - lo
    if span.z <= span.y:
        raise RuntimeError("EVIDENCE_INCOMPLETE: orientación no vertical")
    all_lo, all_hi = alth._limites(meshes)
    alth.estudio()
    scene = bpy.context.scene
    scene.cycles.samples = 16
    scene.render.resolution_percentage = 100
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {"input": a.input, "coordinate_correction": "glb_to_alth_zup_mm", "files": {}, "orientation_ok": True}
    def capture(name, lower, upper, direction, resolution):
        cam = camera("COPOX_" + name, lower, upper, direction)
        scene.camera = cam
        scene.render.resolution_x = scene.render.resolution_y = resolution
        path = out / (name + ".png")
        scene.render.filepath = str(path.resolve())
        bpy.ops.render.render(write_still=True)
        alth._componer(path)
        report["files"][name] = str(path)
    for view, direction in VIEWS.items():
        capture(view, all_lo, all_hi, direction, 600)
    for side, box in zip(("left", "right"), cfg["morph_regions"]["hands"]["boxes"]):
        hand = [pt for pt in points if all(box[i] <= (pt[i] - lo[i]) / span[i] <= box[i + 3] for i in range(3))]
        if not hand:
            raise RuntimeError("EVIDENCE_INCOMPLETE: closeup vacío " + side)
        lower = Vector(tuple(min(pt[i] for pt in hand) for i in range(3)))
        upper = Vector(tuple(max(pt[i] for pt in hand) for i in range(3)))
        capture("hand_" + side, lower, upper, VIEWS["front"], 640)
        if side == "left":
            capture("hand_left_threeq", lower, upper, VIEWS["threeq"], 640)
    box = cfg["morph_regions"]["fingers"]["boxes"][0]
    lower = Vector(tuple(lo[i] + box[i] * span[i] for i in range(3)))
    upper = Vector(tuple(lo[i] + box[i + 3] * span[i] for i in range(3)))
    capture("finger_region", lower, upper, VIEWS["threeq"], 640)
    (out / "render_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
