from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from copox.adapters.alth_character_audit import crop_norm, load_config, load_scene, person_mask, region_mask, registration_from_baseline
from copox.adapters.finger_robust_extrude_plan import _side_spec
from copox.adapters.finger_valley_probe import _valleys
from copox.production.finger_gap_trial import _sha256
from copox.adapters.finger_gap_plan import _pixel_to_norm
from copox.adapters.finger_connected_profile import DEPTH_SCALES


def plan_micro_valleys(parent, reference, config, output):
    cfg = load_config(config)
    scale = float(cfg.get("mesh_to_mm", 1000.0))
    scene, full_mesh = load_scene(parent, scale)
    meshes = []
    for node in scene.graph.nodes_geometry:
        matrix, name = scene.graph.get(node)
        geom = scene.geometry[name]
        if hasattr(geom, "vertices"):
            points = (matrix @ np.column_stack([geom.vertices, np.ones(len(geom.vertices))]).T).T[:, :3]
            meshes.append((len(points), points))
    if not meshes:
        raise RuntimeError("DIAGNOSTIC_REQUIRED: parent sin geometría")
    world = max(meshes, key=lambda row: row[0])[1]
    lo, hi = world.min(axis=0), world.max(axis=0)
    span = hi - lo
    if np.any(span <= 0):
        raise RuntimeError("MESH_INTEGRITY_FAILED: bounds inválidos")
    norm = (world - lo) / span
    front = crop_norm(np.array(Image.open(reference).convert("RGB")), cfg["views"]["front"])
    mask = person_mask(front)
    detected = {}
    for side in ("left", "right"):
        spec, _ = _side_spec(cfg, side)
        roi = region_mask(mask, spec["box"])
        detected[side] = _valleys(mask, roi, side)
    counts = {side: len(rows) for side, rows in detected.items()}
    if counts != {"left": 2, "right": 0}:
        raise RuntimeError(f"DIAGNOSTIC_REQUIRED: asimetría inesperada {counts}")
    spec, morph = _side_spec(cfg, "left")
    hand_box = np.asarray(cfg["morph_regions"]["hands"]["boxes"][0], dtype=float)
    morph = np.asarray(morph, dtype=float)
    inside = np.all((norm >= hand_box[:3]) & (norm <= hand_box[3:]), axis=1)
    hand = norm[inside]
    if len(hand) < 8:
        raise RuntimeError("DIAGNOSTIC_REQUIRED: mano izquierda sin suficientes vértices")
    hand_lo, hand_hi = hand.min(axis=0), hand.max(axis=0)
    ref_hand = mask & region_mask(mask, spec["box"])
    yy, xx = np.where(ref_hand)
    bbox = [int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1]
    ref_w, ref_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    hand_w, hand_h = hand_hi[0] - hand_lo[0], hand_hi[2] - hand_lo[2]
    global_registration = registration_from_baseline(full_mesh, "front", mask, cfg)
    targets = []
    for index, valley in enumerate(sorted(detected["left"], key=lambda row: row["center_px"][1]), 1):
        x0, y0, x1, y1 = valley["bbox_px"]
        global_x0, global_zhi = _pixel_to_norm(x0, y0, global_registration, lo, span, scale)
        global_x1, global_zlo = _pixel_to_norm(x1 + 1, y1 + 1, global_registration, lo, span, scale)
        z_high = hand_hi[2] - (y0 - bbox[1]) / ref_h * hand_h
        z_low = hand_hi[2] - (y1 + 1 - bbox[1]) / ref_h * hand_h
        # Position and width come from local image correspondence, not assumed anatomy.
        za, zb = max(z_low, morph[2]), min(z_high, morph[5])
        if zb <= za:
            raise RuntimeError("SCOPE_UNSAFE: valle fuera de región de dedos")
        targets.append({
            "id": f"left_micro_valley_{index}",
            "side": "left",
            "source": valley,
            "global_camera_mapping": {"x_range": [global_x0, global_x1], "z_range": [global_zlo, global_zhi]},
            "pose_correction_executed": False,
            "z_range": [float(za), float(zb)],
            "reference_depth_normalized": float(valley["width_px"] / ref_w * hand_w),
        })
    ordered = sorted(targets, key=lambda row: row["z_range"][0])
    if ordered[0]["z_range"][1] >= ordered[1]["z_range"][0]:
        raise RuntimeError("SCOPE_UNSAFE: cortes superpuestos")
    result = {
        "mode": "reference_pose_preserving_intrinsic_correspondence_v3",
        "parent_sha": _sha256(parent), "reference_sha": _sha256(reference),
        "reference_valleys": counts, "targets": targets,
        "canonical_bounds": [lo.tolist(), hi.tolist()],
        "scope_box": morph.tolist(), "hand_box": hand_box.tolist(),
        "measured_hand_bounds_normalized": [hand_lo.tolist(), hand_hi.tolist()],
        "reference_hand_bbox_px": bbox,
        "registration": "reference_hand_bbox_to_measured_parent_hand_bbox",
        "global_registration_diagnostic": global_registration,
        "registration_limitations": "Intrinsic feature correspondence only; global hand pose mismatch is preserved and not claimed solved.",
        "pose_correction_executed": False,
        "reference_driven": True, "invented_finger_count": False,
        "promotion_executed": False,
        "depth_scales": list(DEPTH_SCALES),
    }
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    for name in ("parent", "reference", "config", "output"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    print(json.dumps(plan_micro_valleys(a.parent, a.reference, a.config, a.output), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
