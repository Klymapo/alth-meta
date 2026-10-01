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
    region_mask,
    registration_from_baseline,
)
from copox.adapters.finger_valley_probe import _valleys


def _component_count(mask: np.ndarray, min_area: int) -> int:
    labels, count = ndi.label(mask)
    if count == 0:
        return 0
    areas = ndi.sum(mask, labels, range(1, count + 1))
    return int(sum(float(a) >= min_area for a in areas))


def _runs_1d(values: np.ndarray, min_len: int = 2) -> int:
    values = np.asarray(values, dtype=bool)
    if not values.any():
        return 0
    padded = np.pad(values.astype(np.int8), (1, 1))
    diff = np.diff(padded)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    return int(sum((e - s) >= min_len for s, e in zip(starts, ends)))


def _detail(mask: np.ndarray, roi: np.ndarray, side: str, distal_fraction: float = 0.58) -> dict[str, Any]:
    ys, xs = np.where(mask)
    if not len(xs):
        return {
            "components": 0,
            "max_vertical_runs": 0,
            "mean_vertical_runs": 0.0,
            "occupied_pixels": 0,
            "valleys": [],
            "valley_count": 0,
        }
    x0, x1 = int(xs.min()), int(xs.max())
    width = max(1, x1 - x0 + 1)
    if side == "left":
        threshold = x0 + int(round(width * distal_fraction))
        distal = mask.copy()
        distal[:, threshold + 1:] = False
        columns = range(x0, max(x0 + 1, threshold + 1))
    else:
        threshold = x1 - int(round(width * distal_fraction))
        distal = mask.copy()
        distal[:, :threshold] = False
        columns = range(max(0, threshold), x1 + 1)

    min_area = max(2, int(mask.size * 0.0007))
    components = _component_count(distal, min_area)
    runs = [_runs_1d(distal[:, x]) for x in columns if 0 <= x < distal.shape[1]]
    valleys = _valleys(mask, roi, side)
    return {
        "components": components,
        "max_vertical_runs": int(max(runs, default=0)),
        "mean_vertical_runs": float(np.mean(runs)) if runs else 0.0,
        "occupied_pixels": int(distal.sum()),
        "distal_fraction": distal_fraction,
        "valleys": valleys,
        "valley_count": len(valleys),
    }


def probe(model_glb: str, reference_sheet: str, config_path: str, output: str, evidence_dir: str) -> dict[str, Any]:
    cfg = load_config(config_path)
    scale = float(cfg.get("mesh_to_mm", 1000.0))
    _, mesh = load_scene(model_glb, scale)
    reference = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(reference, cfg["views"]["front"])
    ref_mask = person_mask(front)
    registration = registration_from_baseline(mesh, "front", ref_mask, cfg)
    model_mask = raster_silhouette(mesh, "front", front.shape[:2], registration, cfg)

    specs = (cfg.get("regions_by_view") or {}).get("hands", [])
    front_specs = [s for s in specs if str(s.get("view", "front")) == "front"]
    if len(front_specs) < 2:
        raise RuntimeError("Se requieren al menos dos ROIs frontales de manos")

    rows = []
    ev = Path(evidence_dir)
    ev.mkdir(parents=True, exist_ok=True)
    for spec in front_specs[:2]:
        box = [float(v) for v in spec["box"]]
        side = "left" if (box[0] + box[2]) / 2.0 < 0.5 else "right"
        roi = region_mask(ref_mask, box)
        ref = ref_mask & roi
        mod = model_mask & roi
        ref_detail = _detail(ref, roi, side)
        model_detail = _detail(mod, roi, side)
        component_gap = abs(ref_detail["components"] - model_detail["components"])
        run_gap = abs(ref_detail["max_vertical_runs"] - model_detail["max_vertical_runs"])
        valley_gap = abs(ref_detail["valley_count"] - model_detail["valley_count"])
        rows.append({
            "side": side,
            "reference": ref_detail,
            "model": model_detail,
            "component_gap": int(component_gap),
            "vertical_run_gap": int(run_gap),
            "valley_count_gap": int(valley_gap),
            "valley_count_match": bool(valley_gap == 0),
        })

        ys, xs = np.where(roi)
        if len(xs):
            x0, x1 = max(0, int(xs.min()) - 3), min(front.shape[1], int(xs.max()) + 4)
            y0, y1 = max(0, int(ys.min()) - 3), min(front.shape[0], int(ys.max()) + 4)
            ref_img = (ref[y0:y1, x0:x1] * 255).astype(np.uint8)
            model_img = (mod[y0:y1, x0:x1] * 255).astype(np.uint8)
            gap = np.full((ref_img.shape[0], 6), 127, dtype=np.uint8)
            comparison = np.concatenate([ref_img, gap, model_img], axis=1)
            Image.fromarray(comparison, mode="L").resize((comparison.shape[1] * 4, comparison.shape[0] * 4)).save(ev / f"hand_detail_{side}.png")

    mean_component_gap = float(np.mean([r["component_gap"] for r in rows]))
    mean_run_gap = float(np.mean([r["vertical_run_gap"] for r in rows]))
    mean_valley_gap = float(np.mean([r["valley_count_gap"] for r in rows]))
    reference_valleys = {r["side"]: int(r["reference"]["valley_count"]) for r in rows}
    model_valleys = {r["side"]: int(r["model"]["valley_count"]) for r in rows}

    # Semántica primaria: valles robustos extraídos de la propia referencia. Los
    # vertical-runs se conservan como diagnóstico, pero ya no pueden inventar dedos
    # por ruido de una sola columna. Componentes separados siguen siendo un veto útil.
    valley_match = all(r["valley_count_match"] for r in rows)
    definition_match = bool(mean_component_gap == 0.0 and valley_match)
    result = {
        "mode": "hand_detail_reference_probe_v2",
        "hands": rows,
        "summary": {
            "mean_component_gap": mean_component_gap,
            "mean_vertical_run_gap": mean_run_gap,
            "mean_valley_count_gap": mean_valley_gap,
            "reference_valleys": reference_valleys,
            "model_valleys": model_valleys,
            "valley_definition_match": valley_match,
            "definition_match": definition_match,
        },
        "interpretation": {
            "components": "Componentes separados en la franja distal; detecta fragmentación o separación extrema.",
            "valleys": "Huecos robustos encerrados verticalmente en la zona distal. Es la señal semántica principal y su cantidad se deriva de la referencia.",
            "vertical_runs": "Diagnóstico secundario sensible a borde/pixel; ya no decide por sí solo cuántos dedos deben existir.",
            "note": "El probe no impone anatomía humana genérica. Para esta referencia frontal detecta los valles que realmente son visibles; otras vistas y el gate regional siguen siendo obligatorios."
        },
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Probe de definición de manos/dedos contra referencia")
    p.add_argument("--model", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--evidence-dir", required=True)
    args = p.parse_args()
    result = probe(args.model, args.reference, args.config, args.output, args.evidence_dir)
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
