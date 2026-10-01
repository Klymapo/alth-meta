from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import scipy.ndimage as ndi
from scipy.signal import find_peaks
import trimesh
from PIL import Image

from copox.adapters.alth_character_audit import (
    crop_norm,
    load_config,
    load_scene,
    person_mask,
    registration_from_baseline,
    region_mask,
)
from copox.adapters.finger_reference_fit import (
    _canonical_rotation,
    _dominant,
    _outer_profile,
    _to_h,
)
from copox.adapters.hand_detail_probe import _detail


def _filled(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    rows = np.arange(len(values), dtype=float)
    known = rows[valid]
    if not len(known):
        return np.zeros_like(values, dtype=float)
    raw = values[valid]
    return np.interp(rows, known, raw, left=float(raw[0]), right=float(raw[-1]))


def _valleys_from_reference(ref_mask: np.ndarray, roi: np.ndarray, side: str) -> list[dict[str, float]]:
    profile, valid = _outer_profile(ref_mask, roi, side)
    if not np.any(valid):
        return []
    smooth = ndi.gaussian_filter1d(_filled(profile, valid), sigma=0.8, mode="nearest")
    # Hacia el interior = x mayor en la mano izquierda; x menor en la derecha.
    signal = smooth if side == "left" else -smooth
    detail = _detail(ref_mask & roi, side)
    target_runs = int(detail.get("max_vertical_runs", 0))
    target_valleys = max(0, target_runs - 1)
    if target_valleys == 0:
        return []

    valid_rows = np.where(valid)[0]
    lo, hi = int(valid_rows.min()), int(valid_rows.max())
    local = signal[lo:hi + 1]
    peaks, props = find_peaks(local, prominence=0.75, distance=3)
    rows = peaks + lo
    prominences = np.asarray(props.get("prominences", np.zeros(len(rows))), dtype=float)

    # Si el raster es demasiado suave para find_peaks, usamos máximos locales por prominencia
    # relativa, siempre limitados al número de valles derivado de la referencia.
    if len(rows) < target_valleys:
        candidates = []
        for y in range(lo + 2, hi - 1):
            shoulder = min(signal[y - 2:y].min(), signal[y + 1:y + 3].min())
            prominence = float(signal[y] - shoulder)
            if prominence > 0.20:
                candidates.append((prominence, y))
        used = set(int(x) for x in rows)
        for prominence, y in sorted(candidates, reverse=True):
            if any(abs(y - u) < 3 for u in used):
                continue
            rows = np.append(rows, y)
            prominences = np.append(prominences, prominence)
            used.add(y)
            if len(rows) >= target_valleys:
                break

    ranked = sorted(
        ({"row": int(y), "prominence_px": float(max(p, 0.25))} for y, p in zip(rows, prominences)),
        key=lambda x: (-x["prominence_px"], x["row"]),
    )[:target_valleys]
    return sorted(ranked, key=lambda x: x["row"])


def carve_finger_valleys(
    baseline: str,
    reference_sheet: str,
    config_path: str,
    output: str,
    report_path: str,
    strength: float = 1.0,
    width_fraction: float = 0.055,
) -> dict[str, Any]:
    if not (0.0 < strength <= 1.6):
        raise ValueError("strength debe estar en (0, 1.6]")
    if not (0.02 <= width_fraction <= 0.12):
        raise ValueError("width_fraction debe estar en [0.02, 0.12]")

    cfg = load_config(config_path)
    specs = [s for s in ((cfg.get("regions_by_view") or {}).get("fingers") or []) if str(s.get("view", "front")) == "front"]
    boxes = ((cfg.get("morph_regions") or {}).get("fingers") or {}).get("boxes") or []
    if len(specs) < 2 or len(boxes) < 2:
        raise RuntimeError("Fingers requiere dos ROIs frontales y dos cajas anatómicas")

    scale_mm = float(cfg.get("mesh_to_mm", 1000.0))
    _, baseline_mesh = load_scene(baseline, scale_mm)
    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    ref_mask = person_mask(front)
    registration = registration_from_baseline(baseline_mesh, "front", ref_mask, cfg)

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

    updated = canonical.copy()
    selected_total = np.zeros(len(canonical), dtype=bool)
    side_reports: list[dict[str, Any]] = []
    total_valleys = 0
    max_shift_model = 0.0

    for spec, box in zip(specs[:2], boxes[:2]):
        side = "left" if (float(spec["box"][0]) + float(spec["box"][2])) / 2.0 < 0.5 else "right"
        roi = region_mask(ref_mask, [float(x) for x in spec["box"]])
        valleys = _valleys_from_reference(ref_mask, roi, side)
        b = np.asarray(box, dtype=float)
        inside = np.all((norm >= b[:3]) & (norm <= b[3:]), axis=1)
        if not np.any(inside):
            raise RuntimeError(f"Caja {side} de fingers no seleccionó vértices")
        selected_total |= inside

        x0, x1 = float(b[0]), float(b[3])
        width = max(x1 - x0, 1e-9)
        if side == "left":
            distal = np.clip((x1 - norm[:, 0]) / width, 0.0, 1.0)
            direction = 1.0
        else:
            distal = np.clip((norm[:, 0] - x0) / width, 0.0, 1.0)
            direction = -1.0
        distal = distal * distal * (3.0 - 2.0 * distal)

        local_height = max(float(span[2] * (b[5] - b[2])), 1e-9)
        sigma_z = local_height * float(width_fraction)
        cap_model = float(span[0] * width * 0.34)
        applied = []

        for valley in valleys:
            row = int(valley["row"])
            z_mm = float(registration["vertical_min"]) + (float(registration["pixel_bottom_y"]) - row) / max(float(registration["scale"]), 1e-9)
            target_z = z_mm / scale_mm
            prominence_mm = float(valley["prominence_px"]) / max(float(registration["scale"]), 1e-9)
            # La profundidad nace de la propia muesca de la referencia. Un factor >1 ayuda
            # a que la muesca sobreviva a la triangulación, siempre bajo un cap geométrico local.
            depth_model = min((prominence_mm / scale_mm) * 1.35 * float(strength), cap_model)
            z_weight = np.exp(-0.5 * ((canonical[:, 2] - target_z) / sigma_z) ** 2)
            weight = inside.astype(float) * distal * z_weight
            shift = direction * depth_model * weight
            updated[:, 0] += shift
            max_shift_model = max(max_shift_model, float(np.max(np.abs(shift))))
            applied.append({
                "row": row,
                "prominence_px": float(valley["prominence_px"]),
                "target_z_model": float(target_z),
                "depth_mm": float(depth_model * scale_mm),
                "sigma_mm": float(sigma_z * scale_mm),
            })

        target_runs = int(_detail(ref_mask & roi, side).get("max_vertical_runs", 0))
        total_valleys += len(applied)
        side_reports.append({
            "side": side,
            "target_vertical_runs": target_runs,
            "target_valleys": max(0, target_runs - 1),
            "detected_valleys": len(applied),
            "selected_vertices": int(inside.sum()),
            "valleys": applied,
        })

    updated_raw_world_h = (inv_rotation @ _to_h(updated).T).T
    updated_local = (inv_node @ updated_raw_world_h.T).T[:, :3]
    updated_local[~selected_total] = vertices_local[~selected_total]
    untouched_exact = bool(np.array_equal(updated_local[~selected_total], vertices_local[~selected_total]))
    geom.vertices = updated_local

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb")
    check = trimesh.load(str(out), force="scene").to_geometry()
    finite = bool(len(check.vertices) and len(check.faces) and np.isfinite(check.vertices).all())
    positive_area = bool(np.isfinite(float(check.area)) and float(check.area) > 0.0)
    mesh_integrity = bool(finite and positive_area)
    result = {
        "mode": "finger_reference_valley_carve",
        "object": node_name,
        "geometry": geom_name,
        "strength": float(strength),
        "width_fraction": float(width_fraction),
        "selection_coordinates": "canonical_z_up",
        "selected_vertices": int(selected_total.sum()),
        "total_vertices": int(len(vertices_local)),
        "outside_scope_exact": untouched_exact,
        "mesh_integrity": mesh_integrity,
        "total_reference_valleys": int(total_valleys),
        "max_applied_shift_mm": float(max_shift_model * scale_mm),
        "sides": side_reports,
        "reference_driven": True,
        "invented_finger_count": False,
        "promotion_allowed": False,
        "learning": "Las muescas se derivan de valles reales del borde distal de la referencia. El gate semántico debe demostrar menor gap de bandas verticales que la baseline, no sólo mejor IoU exterior.",
    }
    Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Esculpe valles visibles entre dedos desde la silueta de referencia")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--width-fraction", type=float, default=0.055)
    args = p.parse_args()
    result = carve_finger_valleys(args.baseline, args.reference, args.config, args.output, args.report, args.strength, args.width_fraction)
    print(json.dumps({
        "total_reference_valleys": result["total_reference_valleys"],
        "max_applied_shift_mm": result["max_applied_shift_mm"],
        "mesh_integrity": result["mesh_integrity"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
