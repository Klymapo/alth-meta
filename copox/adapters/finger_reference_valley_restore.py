from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image

from copox.adapters.alth_character_audit import (
    crop_norm,
    load_config,
    load_scene,
    person_mask,
    raster_silhouette,
    region_mask,
    registration_from_baseline,
)


def _to_h(points: np.ndarray) -> np.ndarray:
    return np.column_stack([points, np.ones(len(points), dtype=float)])


def _dominant(scene: trimesh.Scene):
    rows = []
    for node in scene.graph.nodes_geometry:
        matrix, geom_name = scene.graph.get(node)
        geom = scene.geometry[geom_name]
        if hasattr(geom, "vertices"):
            rows.append((str(node), str(geom_name), np.asarray(matrix, dtype=float), geom))
    if not rows:
        raise RuntimeError("GLB sin geometría editable")
    return max(rows, key=lambda x: len(x[3].vertices))


def _yrange(mask: np.ndarray) -> tuple[float, float]:
    ys, _ = np.where(mask)
    if not len(ys):
        raise RuntimeError("Máscara local de mano vacía")
    return float(ys.min()), float(ys.max())


def _map_y(y: float, src: tuple[float, float], dst: tuple[float, float]) -> float:
    s0, s1 = src
    d0, d1 = dst
    t = (float(y) - s0) / max(s1 - s0, 1e-9)
    return d0 + t * (d1 - d0)


def restore_valleys(
    input_glb: str,
    reference_sheet: str,
    config_path: str,
    plan_path: str,
    output_glb: str,
    report_path: str,
    strength: float = 1.0,
) -> dict[str, Any]:
    if not (0.5 <= strength <= 1.5):
        raise ValueError("strength debe estar en [0.5, 1.5]")
    cfg = load_config(config_path)
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    valleys = list(plan.get("valleys") or [])
    if not valleys:
        raise RuntimeError("Plan sin valles de referencia")

    scale_mm = float(cfg.get("mesh_to_mm", 1000.0))
    _, audit_mesh = load_scene(input_glb, scale_mm)
    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    ref_mask = person_mask(front)
    registration = registration_from_baseline(audit_mesh, "front", ref_mask, cfg)
    model_mask = raster_silhouette(audit_mesh, "front", front.shape[:2], registration, cfg)

    # Retarget vertical local: cada valle se expresa dentro del bbox de la propia
    # mano de referencia y se lleva a la misma fracción del bbox de la mano modelo.
    hand_specs = [s for s in ((cfg.get("regions_by_view") or {}).get("hands") or []) if str(s.get("view", "front")) == "front"]
    if len(hand_specs) < 2:
        raise RuntimeError("Se requieren dos ROIs frontales de manos")
    left_roi = region_mask(ref_mask, [float(v) for v in hand_specs[0]["box"]])
    ref_hand = ref_mask & left_roi
    model_hand = model_mask & left_roi
    ref_hand_y = _yrange(ref_hand)
    model_hand_y = _yrange(model_hand)

    scene = trimesh.load(str(input_glb), force="scene")
    node_name, geom_name, node_matrix, geom = _dominant(scene)
    vertices_local = np.asarray(geom.vertices, dtype=float).copy()
    inv_node = np.linalg.inv(node_matrix)
    world_h = (node_matrix @ _to_h(vertices_local).T).T
    world = world_h[:, :3].copy()
    lo, hi = world.min(axis=0), world.max(axis=0)
    span = np.maximum(hi - lo, 1e-12)
    norm = (world - lo) / span

    coord = cfg["coordinates"]
    h_axis = int(coord["front_horizontal_axis"])
    v_axis = int(coord["vertical_axis"])
    d_axis = int(coord["depth_axis"])
    h_sign = float(coord.get("front_sign", 1.0))
    py = registration["pixel_bottom_y"] - ((world[:, v_axis] * scale_mm) - registration["vertical_min"]) * registration["scale"]

    morph = cfg.get("morph_regions") or {}
    finger_boxes = (morph.get("fingers") or {}).get("boxes") or []
    hand_boxes = (morph.get("hands") or {}).get("boxes") or []
    if not finger_boxes or not hand_boxes:
        raise RuntimeError("Config sin morph_regions.fingers/hands")

    finger_box = np.asarray(finger_boxes[0], dtype=float)
    hand_box = np.asarray(hand_boxes[0], dtype=float)
    depth_lo = float(hand_box[d_axis])
    depth_hi = float(hand_box[d_axis + 3])
    inside_depth = (norm[:, d_axis] >= depth_lo) & (norm[:, d_axis] <= depth_hi)

    fx0, fx1 = float(finger_box[h_axis]), float(finger_box[h_axis + 3])
    finger_width = max(fx1 - fx0, 1e-9)
    inside_horizontal = (norm[:, h_axis] >= fx0) & (norm[:, h_axis] <= fx1)
    distal = np.clip((fx1 - norm[:, h_axis]) / finger_width, 0.0, 1.0)
    distal_weight = np.clip((distal - 0.42) / 0.58, 0.0, 1.0)
    distal_weight = distal_weight * distal_weight * (3.0 - 2.0 * distal_weight)
    distal_scope = inside_depth & inside_horizontal & (distal_weight > 0.0)

    updated = world.copy()
    selected_total = np.zeros(len(world), dtype=bool)
    valley_reports = []
    max_shift = 0.0

    py_scope_min = float(np.min(py[distal_scope])) if np.any(distal_scope) else None
    py_scope_max = float(np.max(py[distal_scope])) if np.any(distal_scope) else None

    for idx, valley in enumerate(valleys, 1):
        bbox = [float(v) for v in valley["bbox_px"]]
        x0, y0, x1, y1 = bbox
        mapped_y0 = _map_y(y0, ref_hand_y, model_hand_y)
        mapped_y1 = _map_y(y1, ref_hand_y, model_hand_y)
        ma, mb = sorted((mapped_y0, mapped_y1))
        yc = 0.5 * (ma + mb)
        half = max(1.5, 0.5 * (mb - ma + 1.0))
        feather = max(1.5, half * 0.45)
        dy = np.abs(py - yc)
        vertical = np.clip((half + feather - dy) / feather, 0.0, 1.0)
        vertical[dy <= half] = 1.0

        active = distal_scope & (vertical > 0.0)
        if not np.any(active):
            debug = {
                "distal_scope_vertices": int(distal_scope.sum()),
                "py_scope_min": py_scope_min,
                "py_scope_max": py_scope_max,
                "reference_valley_bbox": bbox,
                "reference_hand_y": list(ref_hand_y),
                "model_hand_y": list(model_hand_y),
                "mapped_model_y": [ma, mb],
            }
            raise RuntimeError(f"Valle {idx} no seleccionó vértices: {debug}")

        valley_width_px = max(1.0, x1 - x0 + 1.0)
        shift_model = (valley_width_px / max(float(registration["scale"]), 1e-9)) / scale_mm
        shift_model *= float(strength)
        cap_model = float(span[h_axis] * finger_width * 0.42)
        shift_model = min(shift_model, cap_model)
        weights = distal_weight * vertical * active.astype(float)
        applied = shift_model * weights

        updated[:, h_axis] += applied * h_sign
        selected_total |= active
        max_shift = max(max_shift, float(np.max(applied)))
        valley_reports.append({
            "id": idx,
            "reference_bbox_px": bbox,
            "mapped_model_y_px": [float(ma), float(mb)],
            "area_px": int(valley.get("area_px", 0)),
            "selected_vertices": int(active.sum()),
            "reference_width_px": float(valley_width_px),
            "max_shift_mm": float(np.max(applied) * scale_mm),
        })

    updated_local = (inv_node @ _to_h(updated).T).T[:, :3]
    updated_local[~selected_total] = vertices_local[~selected_total]
    outside_exact = bool(np.array_equal(updated_local[~selected_total], vertices_local[~selected_total]))
    geom.vertices = updated_local

    out = Path(output_glb)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb")
    check = trimesh.load(str(out), force="scene").to_geometry()
    mesh_integrity = bool(len(check.vertices) and len(check.faces) and np.isfinite(check.vertices).all())

    result = {
        "mode": "reference_valley_restore_experiment",
        "object": node_name,
        "geometry": geom_name,
        "selection_coordinates": "trimesh_world_z_up_no_extra_rotation",
        "coordinate_axes": {"horizontal": h_axis, "vertical": v_axis, "depth": d_axis},
        "vertical_scope_source": "local_hand_bbox_retarget",
        "reference_hand_y": list(ref_hand_y),
        "model_hand_y": list(model_hand_y),
        "depth_scope_source": "hands",
        "distal_horizontal_source": "fingers",
        "distal_scope_vertices": int(distal_scope.sum()),
        "projected_scope_py": [py_scope_min, py_scope_max],
        "reference_driven": True,
        "invented_finger_count": False,
        "valley_count": len(valleys),
        "strength": float(strength),
        "selected_vertices": int(selected_total.sum()),
        "outside_scope_exact": outside_exact,
        "mesh_integrity": mesh_integrity,
        "max_shift_mm": float(max_shift * scale_mm),
        "valleys": valley_reports,
        "promotion_allowed": False,
        "note": "Cada valle conserva su posición relativa dentro de la mano; hands limita profundidad y fingers limita X distal. Nunca promociona por sí mismo.",
    }
    Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Restaura valles visibles de dedos desde referencia")
    p.add_argument("--input", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--strength", type=float, default=1.0)
    a = p.parse_args()
    r = restore_valleys(a.input, a.reference, a.config, a.plan, a.output, a.report, a.strength)
    print(json.dumps({"valley_count": r["valley_count"], "max_shift_mm": r["max_shift_mm"], "mesh_integrity": r["mesh_integrity"]}, ensure_ascii=False))
    return 0 if r["mesh_integrity"] else 8


if __name__ == "__main__":
    raise SystemExit(main())
