from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
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
from copox.adapters.finger_gap_plan import _components, _inside_envelope, _pixel_to_norm


def plan_gaps(
    baseline: str,
    reference_sheet: str,
    config_path: str,
    output: str,
    width_scale: float = 1.0,
    length_scale: float = 1.0,
) -> dict[str, Any]:
    """Detecta valles con ROI de manos, pero permite editar sólo morph_regions.fingers."""
    if not (0.5 <= width_scale <= 1.5):
        raise ValueError("width_scale debe estar en [0.5, 1.5]")
    if not (0.5 <= length_scale <= 1.5):
        raise ValueError("length_scale debe estar en [0.5, 1.5]")

    cfg = load_config(config_path)
    scale_mm = float(cfg.get("mesh_to_mm", 1000.0))
    _, mesh = load_scene(baseline, scale_mm)
    bounds_mm = np.asarray(mesh.bounds, dtype=float)
    lo_model = bounds_mm[0] / scale_mm
    span_model = np.maximum((bounds_mm[1] - bounds_mm[0]) / scale_mm, 1e-12)

    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    ref_mask = person_mask(front)
    registration = registration_from_baseline(mesh, "front", ref_mask, cfg)
    model_mask = raster_silhouette(mesh, "front", front.shape[:2], registration, cfg)

    detection_specs = [
        s for s in ((cfg.get("regions_by_view") or {}).get("hands") or [])
        if str(s.get("view", "front")) == "front"
    ]
    edit_boxes = ((cfg.get("morph_regions") or {}).get("fingers") or {}).get("boxes") or []
    if len(detection_specs) < 2 or len(edit_boxes) < 2:
        raise RuntimeError("Se requieren dos ROIs frontales de manos y dos cajas editables de fingers")

    hands: list[dict[str, Any]] = []
    all_cutters: list[dict[str, Any]] = []
    for spec, morph_box in zip(detection_specs[:2], edit_boxes[:2]):
        roi_box = [float(x) for x in spec["box"]]
        side = "left" if (roi_box[0] + roi_box[2]) / 2.0 < 0.5 else "right"
        roi = region_mask(ref_mask, roi_box)
        ref = ref_mask & roi
        model = model_mask & roi
        envelope = _inside_envelope(ref)
        reference_gap = (~ref) & envelope & roi
        model_overlap = reference_gap & model
        min_area = max(2, int(np.count_nonzero(roi) * 0.00035))
        components = _components(reference_gap, min_area)

        ys_roi, xs_roi = np.where(roi)
        rx0, rx1 = int(xs_roi.min()), int(xs_roi.max())
        rw = max(1, rx1 - rx0 + 1)
        # Mantener sólo valles que nacen desde la mitad distal de la mano.
        distal_limit = rx0 + int(round(rw * 0.66)) if side == "left" else rx1 - int(round(rw * 0.66))

        filtered: list[dict[str, Any]] = []
        for row in components:
            w = row["x1"] - row["x0"] + 1
            h = row["y1"] - row["y0"] + 1
            touches_distal = row["x0"] <= distal_limit if side == "left" else row["x1"] >= distal_limit
            if touches_distal and h >= 1:
                row = dict(row)
                row["aspect_h_over_w"] = float(h / max(w, 1))
                filtered.append(row)
        filtered.sort(key=lambda r: (-r["aspect_h_over_w"], -r["area_px"]))
        filtered = filtered[:4]

        mb = np.asarray(morph_box, dtype=float)
        cutters: list[dict[str, Any]] = []
        for idx, row in enumerate(filtered):
            nx0, nz_top = _pixel_to_norm(row["x0"], row["y0"], registration, lo_model, span_model, scale_mm)
            nx1, nz_bottom = _pixel_to_norm(row["x1"] + 1, row["y1"] + 1, registration, lo_model, span_model, scale_mm)
            xa_map, xb_map = sorted((nx0, nx1))
            za_map, zb_map = sorted((nz_bottom, nz_top))

            # La detección puede ser amplia, pero Z queda estrictamente intersectado
            # con fingers. Si un valle sólo existe en palma, no produce cutter.
            cz = (za_map + zb_map) * 0.5
            half_z = max((zb_map - za_map) * 0.5 * length_scale, 0.0012)
            za = max(cz - half_z, float(mb[2]))
            zb = min(cz + half_z, float(mb[5]))
            if zb <= za:
                continue

            outside = 0.006
            if side == "left":
                proximal = min(max(xb_map, float(mb[0]) + 0.010), float(mb[3]))
                depth = (proximal - float(mb[0])) * width_scale
                xa = float(mb[0]) - outside
                xb = min(float(mb[0]) + depth, float(mb[3]))
            else:
                proximal = max(min(xa_map, float(mb[3]) - 0.010), float(mb[0]))
                depth = (float(mb[3]) - proximal) * width_scale
                xa = max(float(mb[3]) - depth, float(mb[0]))
                xb = float(mb[3]) + outside
            if xb <= xa:
                continue

            cutter = {
                "id": f"{side}_handctx_gap_{idx + 1}",
                "side": side,
                "box_normalized": [xa, float(mb[1]), za, xb, float(mb[4]), zb],
                "source_pixels": {k: row[k] for k in ("x0", "x1", "y0", "y1", "area_px")},
                "mapped_x": [float(xa_map), float(xb_map)],
            }
            cutters.append(cutter)
            all_cutters.append(cutter)

        hands.append({
            "side": side,
            "detection_region": "hands",
            "detection_roi_box": roi_box,
            "edit_region": "fingers",
            "edit_morph_box": [float(x) for x in morph_box],
            "reference_gap_pixels": int(reference_gap.sum()),
            "model_overlap_gap_pixels": int(model_overlap.sum()),
            "components_detected": len(components),
            "components_selected": len(filtered),
            "cutters": cutters,
        })

    result = {
        "mode": "finger_reference_gap_plan_hand_context",
        "reference_driven": True,
        "invented_finger_count": False,
        "detection_region": "hands",
        "edit_region": "fingers",
        "width_scale": float(width_scale),
        "length_scale": float(length_scale),
        "hands": hands,
        "cutters": all_cutters,
        "cutter_count": len(all_cutters),
        "ready": bool(all_cutters),
        "learning": "La detección usa la mano completa para no recortar valles visibles; cada cutter se intersecta después con la caja editable de fingers, protegiendo palma/muñeca/antebrazo.",
    }
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
