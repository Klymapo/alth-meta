from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import scipy.ndimage as ndi
from PIL import Image

from copox.adapters.alth_character_audit import crop_norm, load_config, person_mask, region_mask


def _valleys(mask: np.ndarray, roi: np.ndarray, side: str) -> list[dict[str, Any]]:
    target = ndi.binary_closing(mask & roi, iterations=1)
    ys, xs = np.where(target)
    if not len(xs):
        return []
    x0, x1 = int(xs.min()), int(xs.max())
    width = max(1, x1 - x0 + 1)
    # Sólo extremo distal: excluye palma/muñeca.
    if side == "left":
        distal_limit = x0 + int(round(width * 0.58))
        work = target[:, x0:distal_limit + 1]
        xoff = x0
    else:
        distal_limit = x1 - int(round(width * 0.58))
        work = target[:, distal_limit:x1 + 1]
        xoff = distal_limit

    # Huecos internos: fondo encerrado verticalmente por silueta en la misma columna.
    holes = np.zeros_like(work, dtype=bool)
    for x in range(work.shape[1]):
        rows = np.where(work[:, x])[0]
        if len(rows) < 2:
            continue
        a, b = int(rows.min()), int(rows.max())
        holes[a:b + 1, x] = ~work[a:b + 1, x]
    labels, n = ndi.label(holes)
    out: list[dict[str, Any]] = []
    min_area = max(2, int(work.size * 0.0005))
    for label in range(1, n + 1):
        yy, xx = np.where(labels == label)
        if len(xx) < min_area:
            continue
        out.append({
            "center_px": [float(np.mean(xx) + xoff), float(np.mean(yy))],
            "bbox_px": [int(xx.min() + xoff), int(yy.min()), int(xx.max() + xoff), int(yy.max())],
            "area_px": int(len(xx)),
            "depth_px": int(yy.max() - yy.min() + 1),
            "width_px": int(xx.max() - xx.min() + 1),
        })
    return sorted(out, key=lambda v: (-v["depth_px"], -v["area_px"]))


def probe(reference_sheet: str, config_path: str, output: str) -> dict[str, Any]:
    cfg = load_config(config_path)
    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    mask = person_mask(front)
    specs = [s for s in (cfg.get("regions_by_view") or {}).get("hands", []) if s.get("view", "front") == "front"]
    hands = []
    for spec in specs[:2]:
        box = [float(v) for v in spec["box"]]
        side = "left" if (box[0] + box[2]) / 2.0 < 0.5 else "right"
        roi = region_mask(mask, box)
        valleys = _valleys(mask, roi, side)
        hands.append({"side": side, "valleys": valleys, "valley_count": len(valleys)})
    result = {
        "mode": "finger_valley_reference_probe",
        "hands": hands,
        "reference_driven": True,
        "invented_finger_count": False,
        "note": "Los valles se extraen de la silueta de referencia; no se impone un número anatómico inventado.",
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return result


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    a=p.parse_args()
    r=probe(a.reference,a.config,a.output)
    print(json.dumps({x["side"]:x["valley_count"] for x in r["hands"]},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
