from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import scipy.ndimage as ndi
import trimesh
from PIL import Image

from copox.adapters.alth_character_audit import (
    crop_norm,
    load_config,
    load_scene,
    person_mask,
    raster_silhouette,
    registration_from_baseline,
    region_mask,
)


def _canonical_rotation() -> np.ndarray:
    a = math.radians(-90.0)
    c, s = math.cos(a), math.sin(a)
    return np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, c, -s, 0.0],
        [0.0, s, c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=float)


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


def _front_specs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    specs = (cfg.get("regions_by_view") or {}).get("fingers") or []
    return [s for s in specs if str(s.get("view", "front")) == "front"]


def _outer_profile(mask: np.ndarray, roi: np.ndarray, side: str) -> tuple[np.ndarray, np.ndarray]:
    h = mask.shape[0]
    values = np.full(h, np.nan, dtype=float)
    valid = np.zeros(h, dtype=bool)
    target = mask & roi
    for y in range(h):
        xs = np.where(target[y])[0]
        if len(xs):
            values[y] = float(xs.min() if side == "left" else xs.max())
            valid[y] = True
    return values, valid


def _filled_smoothed_delta(ref_values: np.ndarray, ref_valid: np.ndarray, model_values: np.ndarray, model_valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    valid = ref_valid & model_valid
    delta = np.zeros_like(ref_values, dtype=float)
    if not np.any(valid):
        return delta, valid
    rows = np.arange(len(delta), dtype=float)
    known = rows[valid]
    raw = ref_values[valid] - model_values[valid]
    interpolated = np.interp(rows, known, raw, left=float(raw[0]), right=float(raw[-1]))
    # La referencia raster puede tener dientes de 1 px; suavizamos apenas la tendencia,
    # conservando los valles/protrusiones de varios píxeles que forman los dedos.
    smooth = ndi.gaussian_filter1d(interpolated, sigma=1.0, mode="nearest")
    delta[:] = smooth
    return delta, valid


def fit_fingers(
    baseline: str,
    reference_sheet: str,
    config_path: str,
    output: str,
    report_path: str,
    strength: float = 0.65,
) -> dict[str, Any]:
    if not (0.0 < strength <= 1.25):
        raise ValueError("strength debe estar en (0, 1.25]")
    cfg = load_config(config_path)
    specs = _front_specs(cfg)
    boxes = ((cfg.get("morph_regions") or {}).get("fingers") or {}).get("boxes") or []
    if len(specs) < 2 or len(boxes) < 2:
        raise RuntimeError("Fingers requiere dos ROIs frontales y dos cajas anatómicas")

    # Auditoría/proyección usa la escena concatenada ya normalizada por trimesh.
    scale_mm = float(cfg.get("mesh_to_mm", 1000.0))
    _, baseline_mesh = load_scene(baseline, scale_mm)
    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    ref_mask = person_mask(front)
    registration = registration_from_baseline(baseline_mesh, "front", ref_mask, cfg)
    model_mask = raster_silhouette(baseline_mesh, "front", front.shape[:2], registration, cfg)

    # Edición usa geometría/nodos crudos; la convertimos al mismo Z-up canónico.
    scene = trimesh.load(str(baseline), force="scene")
    node_name, geom_name, node_matrix, geom = _dominant(scene)
    vertices_local = np.asarray(geom.vertices, dtype=float).copy()
    rotation = _canonical_rotation()
    inv_rotation = np.linalg.inv(rotation)
    inv_node = np.linalg.inv(node_matrix)
    raw_world_h = (node_matrix @ _to_h(vertices_local).T).T
    canonical = (rotation @ raw_world_h.T).T[:, :3]
    lo, hi = canonical.min(axis=0), canonical.max(axis=0)
    span = np.maximum(hi - lo, 1e-12)
    norm = (canonical - lo) / span

    px = registration["pixel_center_x"] + ((canonical[:, 0] * scale_mm) - registration["horizontal_center"]) * registration["scale"]
    py = registration["pixel_bottom_y"] - ((canonical[:, 2] * scale_mm) - registration["vertical_min"]) * registration["scale"]

    updated = canonical.copy()
    selected_total = np.zeros(len(canonical), dtype=bool)
    side_reports: list[dict[str, Any]] = []
    max_shift_model = 0.0

    for idx, (spec, box) in enumerate(zip(specs[:2], boxes[:2])):
        side = "left" if (float(spec["box"][0]) + float(spec["box"][2])) / 2.0 < 0.5 else "right"
        roi = region_mask(ref_mask, [float(x) for x in spec["box"]])
        ref_profile, ref_valid = _outer_profile(ref_mask, roi, side)
        model_profile, model_valid = _outer_profile(model_mask, roi, side)
        delta_px, profile_valid = _filled_smoothed_delta(ref_profile, ref_valid, model_profile, model_valid)

        b = np.asarray(box, dtype=float)
        inside = np.all((norm >= b[:3]) & (norm <= b[3:]), axis=1)
        if not np.any(inside):
            raise RuntimeError(f"Caja {side} de fingers no seleccionó vértices")
        selected_total |= inside

        x0, x1 = float(b[0]), float(b[3])
        width = max(x1 - x0, 1e-9)
        if side == "left":
            distal = np.clip((x1 - norm[:, 0]) / width, 0.0, 1.0)
        else:
            distal = np.clip((norm[:, 0] - x0) / width, 0.0, 1.0)
        distal = distal * distal * (3.0 - 2.0 * distal)
        weight = distal * inside.astype(float)

        rows = np.clip(np.rint(py).astype(int), 0, len(delta_px) - 1)
        shift_mm = delta_px[rows] / max(float(registration["scale"]), 1e-9)
        shift_model = (shift_mm / scale_mm) * float(strength) * weight

        # No permitimos que una sola hipótesis recorra más de la mitad del ancho
        # geométrico de la propia caja de dedos. El límite se deriva del modelo.
        cap_model = float(span[0] * width * 0.50)
        shift_model = np.clip(shift_model, -cap_model, cap_model)
        updated[:, 0] += shift_model
        max_shift_model = max(max_shift_model, float(np.max(np.abs(shift_model))))

        valid_rows = np.where(profile_valid)[0]
        side_reports.append({
            "side": side,
            "box": [float(x) for x in box],
            "selected_vertices": int(inside.sum()),
            "profile_rows": int(len(valid_rows)),
            "reference_minus_model_px_mean_abs": float(np.mean(np.abs(delta_px[valid_rows]))) if len(valid_rows) else None,
            "reference_minus_model_px_max_abs": float(np.max(np.abs(delta_px[valid_rows]))) if len(valid_rows) else None,
            "max_applied_shift_mm": float(np.max(np.abs(shift_model[inside])) * scale_mm),
        })

    # Mapear sólo el scope seleccionado; fuera de él se conservan coordenadas exactas.
    updated_raw_world_h = (inv_rotation @ _to_h(updated).T).T
    updated_local = (inv_node @ updated_raw_world_h.T).T[:, :3]
    updated_local[~selected_total] = vertices_local[~selected_total]
    untouched_exact = bool(np.array_equal(updated_local[~selected_total], vertices_local[~selected_total]))
    geom.vertices = updated_local

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb")
    check = trimesh.load(str(out), force="scene").to_geometry()
    mesh_integrity = bool(len(check.vertices) and len(check.faces) and np.isfinite(check.vertices).all())
    result = {
        "mode": "finger_reference_contour_fit",
        "object": node_name,
        "geometry": geom_name,
        "strength": float(strength),
        "selection_coordinates": "canonical_z_up",
        "selected_vertices": int(selected_total.sum()),
        "total_vertices": int(len(vertices_local)),
        "outside_scope_exact": untouched_exact,
        "mesh_integrity": mesh_integrity,
        "max_applied_shift_mm": float(max_shift_model * scale_mm),
        "sides": side_reports,
        "reference_driven": True,
        "invented_finger_count": False,
        "promotion_allowed": False,
        "learning": "El perfil distal se deriva de la silueta frontal de referencia. El gate de manos/dedos debe confirmar que aumentan las separaciones visibles sin regresión en otras vistas.",
    }
    Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Ajusta el borde distal de dedos al contorno de referencia")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--strength", type=float, default=0.65)
    args = p.parse_args()
    result = fit_fingers(args.baseline, args.reference, args.config, args.output, args.report, args.strength)
    print(json.dumps({"selected_vertices": result["selected_vertices"], "max_applied_shift_mm": result["max_applied_shift_mm"], "mesh_integrity": result["mesh_integrity"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
