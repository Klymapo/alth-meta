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
    """Rellena sólo entre primer/último pixel ocupado por columna.

    Los huecos de dedos quedan dentro de esta envolvente, mientras el fondo exterior
    se excluye. Esto evita inventar ranuras a partir del contorno externo de la mano.
    """
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
    x_model = x_mm / scale_mm
    z_model = z_mm / scale_mm
    return float((x_model - lo[0]) / span[0]), float((z_model - lo[2]) / span[2])


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
    hi_model = bounds_mm[1] / scale_mm
    span_model = np.maximum(hi_model - lo_model, 1e-12)

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
        gap = model & (~ref) & envelope & roi
        min_area = max(3, int(np.count_nonzero(roi) * 0.0008))
        components = _components(gap, min_area)

        x_mid = (roi_box[0] + roi_box[2]) * 0.5 * front.shape[1]
        filtered: list[dict[str, Any]] = []
        for row in components:
            w = row["x1"] - row["x0"] + 1
            h = row["y1"] - row["y0"] + 1
            distal = row["cx"] <= x_mid if side == "left" else row["cx"] >= x_mid
            if distal and h >= 2 and row["area_px"] >= min_area:
                row = dict(row)
                row["aspect_h_over_w"] = float(h / max(w, 1))
                filtered.append(row)
        filtered.sort(key=lambda r: (-r["area_px"], -r["aspect_h_over_w"]))
        filtered = filtered[:4]

        cutters: list[dict[str, Any]] = []
        mb = np.asarray(morph_box, dtype=float)
        for idx, row in enumerate(filtered):
            nx0, nz_top = _pixel_to_norm(row["x0"], row["y0"], registration, lo_model, span_model, scale_mm)
            nx1, nz_bottom = _pixel_to_norm(row["x1"] + 1, row["y1"] + 1, registration, lo_model, span_model, scale_mm)
            xa, xb = sorted((nx0, nx1))
            za, zb = sorted((nz_bottom, nz_top))
            cx, cz = (xa + xb) * 0.5, (za + zb) * 0.5
            half_x = max((xb - xa) * 0.5 * width_scale, 0.0015)
            half_z = max((zb - za) * 0.5 * length_scale, 0.0015)
            xa, xb = cx - half_x, cx + half_x
            za, zb = cz - half_z, cz + half_z
            xa, xb = max(xa, float(mb[0])), min(xb, float(mb[3]))
            za, zb = max(za, float(mb[2])), min(zb, float(mb[5]))
            if xb <= xa or zb <= za:
                continue
            cutter = {
                "id": f"{side}_gap_{idx + 1}",
                "side": side,
                "box_normalized": [xa, float(mb[1]), za, xb, float(mb[4]), zb],
                "source_pixels": {k: row[k] for k in ("x0", "x1", "y0", "y1", "area_px")},
            }
            cutters.append(cutter)
            all_cutters.append(cutter)

        hands.append({
            "side": side,
            "roi_box": roi_box,
            "morph_box": [float(x) for x in morph_box],
            "gap_pixels": int(gap.sum()),
            "components_detected": len(components),
            "cutters": cutters,
        })

    result = {
        "mode": "finger_reference_gap_plan",
        "reference_driven": True,
        "invented_finger_count": False,
        "width_scale": float(width_scale),
        "length_scale": float(length_scale),
        "hands": hands,
        "cutters": all_cutters,
        "cutter_count": len(all_cutters),
        "ready": bool(all_cutters),
        "learning": "Cada cutter nace de pixels ocupados por Alpha pero vacíos en la referencia dentro de la envolvente de la mano. No se inventa número ni posición de dedos.",
    }
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Deriva ranuras de dedos desde la referencia frontal")
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
