from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from copox.adapters.alth_character_audit import crop_norm, load_config, load_scene, person_mask, region_mask, registration_from_baseline, raster_silhouette
from copox.adapters.finger_gap_plan import _pixel_to_norm
from copox.adapters.finger_connected_profile import DEPTH_SCALES
from copox.adapters.finger_robust_extrude_plan import _side_spec
from copox.adapters.finger_valley_probe import _valleys
from copox.production.finger_gap_trial import _sha256


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
    registration = registration_from_baseline(full_mesh, "front", mask, cfg)
    model_mask = raster_silhouette(full_mesh, "front", mask.shape, registration, cfg)
    envelope = []
    for column in range(mask.shape[1]):
        xn, _ = _pixel_to_norm(column, 0, registration, lo, span, scale)
        if not morph[0] <= xn <= morph[3]:
            continue
        ry = np.where(ref_hand[:, column])[0]
        my = np.where(model_mask[:, column] & region_mask(mask, spec["box"])[:, column])[0]
        if len(ry) < 2 or len(my) < 2:
            continue
        _, rhi = _pixel_to_norm(column, int(ry.min()), registration, lo, span, scale)
        _, rlo = _pixel_to_norm(column, int(ry.max()) + 1, registration, lo, span, scale)
        _, mhi = _pixel_to_norm(column, int(my.min()), registration, lo, span, scale)
        _, mlo = _pixel_to_norm(column, int(my.max()) + 1, registration, lo, span, scale)
        if not morph[2] < rlo < rhi < morph[5] or not morph[2] < mlo < mhi < morph[5]:
            continue
        envelope.append({"x": float(xn), "model_z": [float(mlo), float(mhi)],
                         "reference_z": [float(rlo), float(rhi)], "column_px": column})
    if len(envelope) < 3:
        raise RuntimeError("DIAGNOSTIC_REQUIRED: insuficiente contorno frontal emparejado")
    targets = []
    for index, valley in enumerate(sorted(detected["left"], key=lambda row: row["center_px"][1]), 1):
        x0, y0, x1, y1 = valley["bbox_px"]
        xa, z_high = _pixel_to_norm(x0, y0, registration, lo, span, scale)
        xb, z_low = _pixel_to_norm(x1 + 1, y1 + 1, registration, lo, span, scale)
        if not morph[2] < z_low < z_high < morph[5] or xb >= morph[3]:
            raise RuntimeError("SCOPE_UNSAFE: valle real fuera del patch izquierdo")
        targets.append({"id": f"left_micro_valley_{index}", "side": "left", "source": valley,
                       "z_range": [float(z_low), float(z_high)], "mapped_x": [float(xa), float(xb)],
                       "reference_depth_normalized": float(valley["width_px"] / registration["scale"] / scale / span[0])})
    ordered = sorted(targets, key=lambda row: row["z_range"][0])
    if ordered[0]["z_range"][1] >= ordered[1]["z_range"][0]:
        raise RuntimeError("SCOPE_UNSAFE: cortes superpuestos")
    result = {
        "mode": "reference_connected_notch_global_correspondence_v2",
        "parent_sha": _sha256(parent), "reference_sha": _sha256(reference),
        "reference_valleys": counts, "targets": targets,
        "canonical_bounds": [lo.tolist(), hi.tolist()],
        "scope_box": morph.tolist(), "hand_box": hand_box.tolist(),
        "measured_hand_bounds_normalized": [hand_lo.tolist(), hand_hi.tolist()],
        "reference_hand_bbox_px": bbox,
        "registration": registration,
        "registration_method": "fixed_parent_front_camera_global_pixel_to_canonical",
        "contour_envelope": envelope,
        "contour_anchor_x": float(morph[3]),
        "contour_full_influence_x": float(max(t["mapped_x"][1] for t in targets)),
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
