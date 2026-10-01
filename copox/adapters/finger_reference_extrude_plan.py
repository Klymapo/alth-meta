from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from copox.adapters.alth_character_audit import crop_norm, load_config, person_mask, region_mask


def _runs(values: np.ndarray, min_len: int = 2) -> list[tuple[int, int]]:
    values = np.asarray(values, dtype=bool)
    if not values.any():
        return []
    padded = np.pad(values.astype(np.int8), (1, 1))
    diff = np.diff(padded)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    return [(int(s), int(e - 1)) for s, e in zip(starts, ends) if int(e - s) >= min_len]


def _side_spec(cfg: dict[str, Any], side: str) -> tuple[dict[str, Any], list[float]]:
    specs = [
        s for s in ((cfg.get("regions_by_view") or {}).get("hands") or [])
        if str(s.get("view", "front")) == "front"
    ]
    boxes = ((cfg.get("morph_regions") or {}).get("fingers") or {}).get("boxes") or []
    if len(specs) < 2 or len(boxes) < 2:
        raise RuntimeError("Se requieren dos ROIs frontales de hands y dos morph boxes de fingers")
    pairs = []
    for spec, box in zip(specs[:2], boxes[:2]):
        b = [float(v) for v in spec["box"]]
        current = "left" if (b[0] + b[2]) * 0.5 < 0.5 else "right"
        pairs.append((current, spec, [float(v) for v in box]))
    for current, spec, box in pairs:
        if current == side:
            return spec, box
    raise RuntimeError(f"No se encontró ROI para {side}")


def plan_extruded_fingers(
    reference_sheet: str,
    config_path: str,
    output: str,
    side: str = "left",
) -> dict[str, Any]:
    """Deriva bandas visibles de dedos directamente de la referencia frontal.

    Es un experimento learning-only inspirado en el flujo habitual de modelado de
    manos: definir primero la silueta plana y después darle volumen/loops. No impone
    un número anatómico de dedos; usa únicamente las bandas separadas que la propia
    referencia hace visibles en la mitad distal de la mano.
    """
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
    width = max(1, x1 - x0 + 1)
    # Buscar el corte con mayor número de bandas visibles sólo en la zona distal.
    # En empate preferimos el corte más cercano a la palma, porque produce una base
    # de extrusión más estable y evita medir únicamente las puntas.
    if side == "left":
        xa, xb = x0, x0 + int(round(width * 0.62))
        columns = range(max(0, xa), min(hand.shape[1] - 1, xb) + 1)
        tie_key = lambda x: x
    else:
        xa, xb = x1 - int(round(width * 0.62)), x1
        columns = range(max(0, xa), min(hand.shape[1] - 1, xb) + 1)
        tie_key = lambda x: -x

    samples: list[dict[str, Any]] = []
    for x in columns:
        runs = _runs(hand[:, x], min_len=2)
        if not runs:
            continue
        occupied = int(sum(b - a + 1 for a, b in runs))
        samples.append({"x": int(x), "runs": runs, "count": len(runs), "occupied": occupied})
    if not samples:
        raise RuntimeError(f"No se hallaron bandas distales en {side}")
    best_count = max(int(s["count"]) for s in samples)
    robust = [s for s in samples if int(s["count"]) == best_count]
    # Favorece una columna con bandas largas y, después, la más proximal.
    best = max(robust, key=lambda s: (int(s["occupied"]), tie_key(int(s["x"]))))

    runs = list(best["runs"])
    # Descartar ruido extremo si una sola banda es diminuta respecto de la mediana.
    lengths = np.array([b - a + 1 for a, b in runs], dtype=float)
    median = float(np.median(lengths)) if len(lengths) else 0.0
    if median > 0:
        runs = [(a, b) for a, b in runs if (b - a + 1) >= max(2.0, median * 0.35)]

    mb = np.asarray(morph_box, dtype=float)
    height_px = max(1.0, float(y1 - y0 + 1))
    digits: list[dict[str, Any]] = []
    for index, (ra, rb) in enumerate(runs, start=1):
        # Mapear sólo la distribución vertical relativa de la referencia dentro del
        # morph box ya localizado en Theo. Así evitamos reusar la conversión píxel→3D
        # que produjo cutters desplazados en el experimento booleano anterior.
        ta = np.clip((float(ra) - float(y0)) / height_px, 0.0, 1.0)
        tb = np.clip((float(rb + 1) - float(y0)) / height_px, 0.0, 1.0)
        z_hi = float(mb[5] - ta * (mb[5] - mb[2]))
        z_lo = float(mb[5] - tb * (mb[5] - mb[2]))
        za, zb = sorted((z_lo, z_hi))
        if zb - za <= 1e-4:
            continue

        # Longitud relativa desde la propia silueta: buscar hasta dónde llega la banda.
        band = hand[max(0, ra): min(hand.shape[0], rb + 1), :]
        by, bx = np.where(band)
        if not len(bx):
            continue
        tip_px = int(bx.min()) if side == "left" else int(bx.max())
        if side == "left":
            distal_fraction = np.clip((float(best["x"]) - float(tip_px)) / max(float(best["x"] - x0), 1.0), 0.30, 1.0)
        else:
            distal_fraction = np.clip((float(tip_px) - float(best["x"])) / max(float(x1 - best["x"]), 1.0), 0.30, 1.0)
        digits.append({
            "id": f"{side}_visible_digit_{index}",
            "z_range_normalized": [float(za), float(zb)],
            "distal_fraction": float(distal_fraction),
            "source_run_px": [int(ra), int(rb)],
            "source_column_px": int(best["x"]),
            "source_tip_px": int(tip_px),
        })

    result = {
        "mode": "reference_visible_digit_extrusion_plan_v1",
        "side": side,
        "reference_driven": True,
        "invented_finger_count": False,
        "research_prototype": True,
        "promotion_allowed": False,
        "hand_roi_box": [float(v) for v in spec["box"]],
        "finger_morph_box": [float(v) for v in morph_box],
        "reference_hand_bbox_px": [x0, y0, x1, y1],
        "sample_column_px": int(best["x"]),
        "visible_band_count": len(digits),
        "digits": digits,
        "learning": (
            "Traza las bandas separadas visibles de la referencia y las convierte en bases de extrusión. "
            "La conectividad final palma-dedos se deja fuera de este experimento; primero se prueba si la familia geométrica elimina mitten_shape."
        ),
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Plan learning-only de dedos extruidos desde referencia")
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--side", choices=("left", "right"), default="left")
    a = p.parse_args()
    r = plan_extruded_fingers(a.reference, a.config, a.output, a.side)
    print(json.dumps({"side": r["side"], "visible_band_count": r["visible_band_count"], "sample_column_px": r["sample_column_px"]}, ensure_ascii=False))
    return 0 if r["visible_band_count"] >= 2 else 7


if __name__ == "__main__":
    raise SystemExit(main())
