from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from copox.adapters.alth_character_audit import (
    bbox,
    crop_norm,
    iou,
    load_config,
    load_scene,
    person_mask,
    raster_silhouette,
    region_mask,
    registration_from_baseline,
    save_overlay,
    xor_ratio,
)


def _region_specs(cfg: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw = cfg.get("regions_by_view") or {}
    out: dict[str, list[dict[str, Any]]] = {}
    for name, specs in raw.items():
        if isinstance(specs, dict):
            specs = [specs]
        out[str(name)] = []
        for spec in specs or []:
            view = str(spec.get("view", "front"))
            box = [float(x) for x in spec.get("box", [])]
            if len(box) != 4:
                raise ValueError(f"ROI inválida para {name}: {spec}")
            out[str(name)].append({"view": view, "box": box})
    return out


def _crop_by_mask(image: np.ndarray, mask: np.ndarray, pad: int = 4) -> np.ndarray:
    ys, xs = np.where(mask)
    if not len(xs):
        return image[:1, :1]
    x0, x1 = max(0, int(xs.min()) - pad), min(image.shape[1], int(xs.max()) + pad + 1)
    y0, y1 = max(0, int(ys.min()) - pad), min(image.shape[0], int(ys.max()) + pad + 1)
    return image[y0:y1, x0:x1]


def audit_regions(
    prev_glb: str,
    curr_glb: str,
    reference_sheet: str,
    config_path: str,
    output: str,
    evidence_dir: str,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    specs = _region_specs(cfg)
    if not specs:
        raise RuntimeError("regions_by_view no está definido en la configuración")

    scale = float(cfg.get("mesh_to_mm", 1000.0))
    _, prev_mesh = load_scene(prev_glb, scale)
    _, curr_mesh = load_scene(curr_glb, scale)
    reference = np.array(Image.open(reference_sheet).convert("RGB"))
    refs = {name: crop_norm(reference, box) for name, box in cfg["views"].items()}
    ref_masks = {name: person_mask(img) for name, img in refs.items()}

    registrations = {
        view: registration_from_baseline(prev_mesh, view, ref_masks[view], cfg)
        for view in refs
    }
    silhouettes: dict[tuple[str, str], np.ndarray] = {}
    for label, mesh in (("prev", prev_mesh), ("curr", curr_mesh)):
        for view in refs:
            silhouettes[(label, view)] = raster_silhouette(
                mesh, view, refs[view].shape[:2], registrations[view], cfg
            )

    evidence = Path(evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    regions: dict[str, Any] = {}

    for region_name, region_specs in specs.items():
        per_view: list[dict[str, Any]] = []
        for idx, spec in enumerate(region_specs):
            view = spec["view"]
            if view not in refs:
                raise ValueError(f"Vista desconocida en {region_name}: {view}")
            roi = region_mask(ref_masks[view], spec["box"])
            ref_region = ref_masks[view] & roi
            prev_region = silhouettes[("prev", view)] & roi
            curr_region = silhouettes[("curr", view)] & roi
            prev_iou = iou(prev_region, ref_region)
            curr_iou = iou(curr_region, ref_region)
            visible = xor_ratio(prev_region, curr_region) * 100.0
            delta_pp = (curr_iou - prev_iou) * 100.0
            entry = {
                "view": view,
                "prev_iou": prev_iou,
                "curr_iou": curr_iou,
                "delta_pp": delta_pp,
                "visible_delta_pct": visible,
                "error_score": (1.0 - curr_iou) * 100.0,
            }
            per_view.append(entry)

            overlay_path = evidence / f"region_{region_name}_{view}_{idx + 1}.png"
            temp_path = evidence / f".tmp_{region_name}_{view}_{idx + 1}.png"
            save_overlay(temp_path, refs[view], silhouettes[("prev", view)], silhouettes[("curr", view)])
            overlay = np.array(Image.open(temp_path).convert("RGB"))
            Image.fromarray(_crop_by_mask(overlay, roi)).save(overlay_path)
            temp_path.unlink(missing_ok=True)

        regions[region_name] = {
            "prev_iou": float(np.mean([x["prev_iou"] for x in per_view])),
            "curr_iou": float(np.mean([x["curr_iou"] for x in per_view])),
            "delta_pp": float(np.mean([x["delta_pp"] for x in per_view])),
            "visible_delta_pct": float(np.mean([x["visible_delta_pct"] for x in per_view])),
            "error_score": float(np.mean([x["error_score"] for x in per_view])),
            "views": per_view,
        }

    ranking = sorted(
        ({"region": name, "error_score": data["error_score"], "curr_iou": data["curr_iou"]}
         for name, data in regions.items()),
        key=lambda x: x["error_score"],
        reverse=True,
    )
    result = {
        "mode": "regional_reference_audit",
        "registration": {"mode": "baseline_locked", "coordinate_system": cfg["coordinates"]},
        "regions": regions,
        "error_ranking": ranking,
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Auditor regional multivista contra referencia")
    p.add_argument("--prev", required=True)
    p.add_argument("--curr", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--evidence-dir", required=True)
    args = p.parse_args()
    result = audit_regions(args.prev, args.curr, args.reference, args.config, args.output, args.evidence_dir)
    print(json.dumps({"top_errors": result["error_ranking"][:5]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
