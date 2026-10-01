from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from copox.adapters.alth_character_audit import crop_norm, load_config, person_mask, region_mask
from copox.adapters.finger_valley_probe import _valleys


def _side_spec(cfg: dict[str, Any], side: str) -> tuple[dict[str, Any], list[float]]:
    specs = [s for s in ((cfg.get("regions_by_view") or {}).get("hands") or []) if str(s.get("view", "front")) == "front"]
    boxes = ((cfg.get("morph_regions") or {}).get("fingers") or {}).get("boxes") or []
    if len(specs) < 2 or len(boxes) < 2:
        raise RuntimeError("Se requieren dos ROIs frontales de hands y dos morph boxes de fingers")
    for spec, box in zip(specs[:2], boxes[:2]):
        b = [float(v) for v in spec["box"]]
        current = "left" if (b[0] + b[2]) * 0.5 < 0.5 else "right"
        if current == side:
            return spec, [float(v) for v in box]
    raise RuntimeError(f"No se encontró ROI para {side}")


def plan_robust_extruded_fingers(reference_sheet: str, config_path: str, output: str, side: str = "left") -> dict[str, Any]:
    if side not in {"left", "right"}:
        raise ValueError("side debe ser left o right")
    cfg = load_config(config_path)
    spec, morph_box = _side_spec(cfg, side)
    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    ref_mask = person_mask(front)
    roi = region_mask(ref_mask, [float(v) for v in spec["box"]])
    hand = ref_mask & roi
    ys, xs = np.where(hand)
    if not len(xs):
        raise RuntimeError(f"Referencia sin mano detectable: {side}")
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())

    valleys = _valleys(hand, roi, side)
    if not valleys:
        raise RuntimeError("Referencia sin valles robustos visibles")
    valleys = sorted(valleys, key=lambda v: int(v["bbox_px"][1]))

    # Los valles robustos son las fronteras entre bandas. Su complemento vertical
    # dentro del bbox de mano define exactamente N+1 bandas, sin contar ruido de una
    # columna aislada como dedos extra.
    gaps = [(int(v["bbox_px"][1]), int(v["bbox_px"][3])) for v in valleys]
    bands: list[tuple[int, int]] = []
    cursor = y0
    for ga, gb in gaps:
        if ga > cursor:
            bands.append((cursor, ga - 1))
        cursor = max(cursor, gb + 1)
    if cursor <= y1:
        bands.append((cursor, y1))
    bands = [(a, b) for a, b in bands if b >= a]
    if len(bands) != len(valleys) + 1:
        raise RuntimeError(f"Bandas/valles inconsistentes: bands={bands}, valleys={gaps}")

    mb = np.asarray(morph_box, dtype=float)
    height_px = max(1.0, float(y1 - y0 + 1))
    hand_width = max(1.0, float(x1 - x0 + 1))
    digits: list[dict[str, Any]] = []
    for index, (ra, rb) in enumerate(bands, start=1):
        ta = np.clip((float(ra) - float(y0)) / height_px, 0.0, 1.0)
        tb = np.clip((float(rb + 1) - float(y0)) / height_px, 0.0, 1.0)
        z_hi = float(mb[5] - ta * (mb[5] - mb[2]))
        z_lo = float(mb[5] - tb * (mb[5] - mb[2]))
        za, zb = sorted((z_lo, z_hi))
        if zb - za <= 1e-4:
            continue

        band_mask = hand[max(0, ra):min(hand.shape[0], rb + 1), :]
        _, bx = np.where(band_mask)
        if not len(bx):
            continue
        tip_px = int(bx.min()) if side == "left" else int(bx.max())
        if side == "left":
            length_fraction = np.clip((float(x1) - float(tip_px)) / hand_width, 0.30, 1.0)
        else:
            length_fraction = np.clip((float(tip_px) - float(x0)) / hand_width, 0.30, 1.0)
        digits.append({
            "id": f"{side}_robust_band_{index}",
            "z_range_normalized": [float(za), float(zb)],
            "distal_fraction": float(length_fraction),
            "source_run_px": [int(ra), int(rb)],
            "source_tip_px": int(tip_px),
        })

    result = {
        "mode": "reference_robust_valley_extrusion_plan_v1",
        "side": side,
        "reference_driven": True,
        "invented_finger_count": False,
        "research_prototype": True,
        "promotion_allowed": False,
        "hand_roi_box": [float(v) for v in spec["box"]],
        "finger_morph_box": [float(v) for v in morph_box],
        "reference_hand_bbox_px": [x0, y0, x1, y1],
        "robust_valley_count": len(valleys),
        "robust_valleys": valleys,
        "visible_band_count": len(digits),
        "digits": digits,
        "learning": "Dos valles robustos generan tres bandas por complemento vertical. Evita sobresegmentación causada por una sola columna de píxeles.",
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Plan robusto de extrusión basado en valles")
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--side", choices=("left", "right"), default="left")
    a = p.parse_args()
    r = plan_robust_extruded_fingers(a.reference, a.config, a.output, a.side)
    print(json.dumps({"valleys": r["robust_valley_count"], "bands": r["visible_band_count"]}, ensure_ascii=False))
    return 0 if r["visible_band_count"] >= 2 else 7


if __name__ == "__main__":
    raise SystemExit(main())
