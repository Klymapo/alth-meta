from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from copox.adapters.alth_character_audit import crop_norm, load_config, load_scene, person_mask, region_mask
from copox.adapters.finger_robust_extrude_plan import _side_spec
from copox.adapters.finger_valley_probe import _valleys
from copox.production.finger_gap_trial import _sha256


def plan_micro_valleys(parent, reference, config, output):
    cfg = load_config(config)
    scale = float(cfg.get("mesh_to_mm", 1000.0))
    scene, _ = load_scene(parent, scale)
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
    targets = []
    for index, valley in enumerate(sorted(detected["left"], key=lambda row: row["center_px"][1]), 1):
        x0, y0, x1, y1 = valley["bbox_px"]
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
            "z_range": [float(za), float(zb)],
            "reference_depth_normalized": float(valley["width_px"] / ref_w * hand_w),
        })
    ordered = sorted(targets, key=lambda row: row["z_range"][0])
    if ordered[0]["z_range"][1] >= ordered[1]["z_range"][0]:
        raise RuntimeError("SCOPE_UNSAFE: cortes superpuestos")
    result = {
        "mode": "reference_micro_valley_local_correspondence_v1",
        "parent_sha": _sha256(parent), "reference_sha": _sha256(reference),
        "reference_valleys": counts, "targets": targets,
        "canonical_bounds": [lo.tolist(), hi.tolist()],
        "scope_box": morph.tolist(), "hand_box": hand_box.tolist(),
        "measured_hand_bounds_normalized": [hand_lo.tolist(), hand_hi.tolist()],
        "reference_hand_bbox_px": bbox,
        "registration": "reference_hand_bbox_to_measured_parent_hand_bbox",
        "reference_driven": True, "invented_finger_count": False,
        "promotion_executed": False,
        "depth_scales": [0.75, 1.0, 1.25],
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
