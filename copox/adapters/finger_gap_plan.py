from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import scipy.ndimage as ndi
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


def _inside_envelope(mask: np.ndarray) -> np.ndarray:
    out = np.zeros_like(mask, dtype=bool)
    for x in range(mask.shape[1]):
        ys = np.where(mask[:, x])[0]
        if len(ys) >= 2:
            out[int(ys.min()): int(ys.max()) + 1, x] = True
    return out


def _components(mask: np.ndarray, min_area: int) -> list[dict[str, Any]]:
    labels, count = ndi.label(mask)
    rows: list[dict[str, Any]] = []
    for idx in range(1, count + 1):
        ys, xs = np.where(labels == idx)
        if len(xs) < min_area:
            continue
        rows.append({
            "area_px": int(len(xs)),
            "x0": int(xs.min()), "x1": int(xs.max()),
            "y0": int(ys.min()), "y1": int(ys.max()),
            "cx": float(xs.mean()), "cy": float(ys.mean()),
        })
    return rows


def _pixel_to_norm(px: float, py: float, registration: dict[str, Any], lo: np.ndarray, span: np.ndarray, scale_mm: float) -> tuple[float, float]:
    x_mm = float(registration["horizontal_center"]) + (float(px) - float(registration["pixel_center_x"])) / max(float(registration["scale"]), 1e-9)
    z_mm = float(registration["vertical_min"]) + (float(registration["pixel_bottom_y"]) - float(py)) / max(float(registration["scale"]), 1e-9)
    return float((x_mm / scale_mm - lo[0]) / span[0]), float((z_mm / scale_mm - lo[2]) / span[2])


def plan_gaps(baseline: str, reference_sheet: str, config_path: str, output: str, width_scale: float = 1.0, length_scale: float = 1.0) -> dict[str, Any]:
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

    specs = [s for s in ((cfg.get("regions_by_view") or {}).get("fingers") or []) if str(s.get("view", "front")) == "front"]
    boxes = ((cfg.get("morph_regions") or {}).get("fingers") or {}).get("boxes") or []
    if len(specs) < 2 or len(boxes) < 2:
        raise RuntimeError("Fingers requiere dos ROIs frontales y dos cajas anatómicas")

    hands: list[dict[str, Any]] = []
    all_cutters: list[dict[str, Any]] = []
    for spec, morph_box in zip(specs[:2], boxes[:2]):
        roi_box = [float(x) for x in spec["box"]]
        side = "left" if (roi_box[0] + roi_box[2]) / 2.0 < 0.5 else "right"
        roi = region_mask(ref_mask, roi_box)
        ref = ref_mask & roi
        model = model_mask & roi
        envelope = _inside_envelope(ref)

        # Los valles entre dedos son fondo de la REFERENCIA dentro de su propia
        # envolvente vertical. No exigimos que Alpha ya ocupe esos pixels: ese filtro
        # fue precisamente lo que escondió los huecos en la primera prueba.
        reference_gap = (~ref) & envelope & roi
        model_overlap = reference_gap & model
        min_area = max(2, int(np.count_nonzero(roi) * 0.0004))
        components = _components(reference_gap, min_area)

        ys_roi, xs_roi = np.where(roi)
        rx0, rx1 = int(xs_roi.min()), int(xs_roi.max())
        rw = max(1, rx1 - rx0 + 1)
        distal_limit = rx0 + int(round(rw * 0.78)) if side == "left" else rx1 - int(round(rw * 0.78))

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

        cutters: list[dict[str, Any]] = []
        mb = np.asarray(morph_box, dtype=float)
        for idx, row in enumerate(filtered):
            nx0, nz_top = _pixel_to_norm(row["x0"], row["y0"], registration, lo_model, span_model, scale_mm)
            nx1, nz_bottom = _pixel_to_norm(row["x1"] + 1, row["y1"] + 1, registration, lo_model, span_model, scale_mm)
            xa_map, xb_map = sorted((nx0, nx1))
            za, zb = sorted((nz_bottom, nz_top))

            cz = (za + zb) * 0.5
            half_z = max((zb - za) * 0.5 * length_scale, 0.0012)
            za, zb = max(cz - half_z, float(mb[2])), min(cz + half_z, float(mb[5]))
            if zb <= za:
                continue

            # Cada ranura debe abrir hacia el borde distal. Permitimos que el cutter
            # sobresalga 0.6% fuera del body: fuera del cuerpo no modifica geometría,
            # pero garantiza una separación abierta en la silueta.
            outside = 0.006
            if side == "left":
                proximal = min(max(xb_map, float(mb[0]) + 0.012), float(mb[3]))
                depth = (proximal - float(mb[0])) * width_scale
                xa = float(mb[0]) - outside
                xb = min(float(mb[0]) + depth, float(mb[3]))
            else:
                proximal = max(min(xa_map, float(mb[3]) - 0.012), float(mb[0]))
                depth = (float(mb[3]) - proximal) * width_scale
                xa = max(float(mb[3]) - depth, float(mb[0]))
                xb = float(mb[3]) + outside
            if xb <= xa:
                continue

            cutter = {
                "id": f"{side}_gap_{idx + 1}",
                "side": side,
                "box_normalized": [xa, float(mb[1]), za, xb, float(mb[4]), zb],
                "source_pixels": {k: row[k] for k in ("x0", "x1", "y0", "y1", "area_px")},
                "mapped_x": [float(xa_map), float(xb_map)],
            }
            cutters.append(cutter)
            all_cutters.append(cutter)

        hands.append({
            "side": side,
            "roi_box": roi_box,
            "morph_box": [float(x) for x in morph_box],
            "reference_gap_pixels": int(reference_gap.sum()),
            "model_overlap_gap_pixels": int(model_overlap.sum()),
            "components_detected": len(components),
            "components_selected": len(filtered),
            "component_debug": filtered,
            "cutters": cutters,
        })

    result = {
        "mode": "finger_reference_gap_plan_v2",
        "reference_driven": True,
        "invented_finger_count": False,
        "width_scale": float(width_scale),
        "length_scale": float(length_scale),
        "hands": hands,
        "cutters": all_cutters,
        "cutter_count": len(all_cutters),
        "ready": bool(all_cutters),
        "learning": "Las ranuras provienen de valles de fondo entre bandas verticales de la referencia y se abren hacia el extremo distal. Alpha sólo se usa para registrar escala/posición, no para decidir si el hueco existe.",
    }
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Deriva ranuras abiertas de dedos desde la referencia frontal")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--width-scale", type=float, default=1.0)
    p.add_argument("--length-scale", type=float, default=1.0)
    args = p.parse_args()
    result = plan_gaps(args.baseline, args.reference, args.config, args.output, args.width_scale, args.length_scale)
    print(json.dumps({"cutter_count": result["cutter_count"], "ready": result["ready"]}, ensure_ascii=False))
    return 0 if result["ready"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
