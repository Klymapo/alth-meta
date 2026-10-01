from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from copox.adapters.alth_character_audit import crop_norm, load_config, person_mask, region_mask


def _side_spec(cfg: dict[str, Any], side: str) -> tuple[dict[str, Any], list[float]]:
    specs = [
        s for s in ((cfg.get("regions_by_view") or {}).get("hands") or [])
        if str(s.get("view", "front")) == "front"
    ]
    boxes = ((cfg.get("morph_regions") or {}).get("hands") or {}).get("boxes") or []
    if len(specs) < 2 or len(boxes) < 2:
        raise RuntimeError("Se requieren ROIs y morph boxes bilaterales de hands")
    for spec, box in zip(specs[:2], boxes[:2]):
        b = [float(v) for v in spec["box"]]
        current = "left" if (b[0] + b[2]) * 0.5 < 0.5 else "right"
        if current == side:
            return spec, [float(v) for v in box]
    raise RuntimeError(f"No se encontró {side}")


def plan_outline(reference_sheet: str, config_path: str, output: str, side: str = "left", tolerance_px: float = 1.25) -> dict[str, Any]:
    """Traza la silueta plana de la mano y la mapea al morph box existente.

    La dependencia de skimage se carga sólo cuando se ejecuta el experimento; no se
    introduce en el motor estable. Este plan sigue literalmente el enfoque de bloquear
    primero la forma 2D y volumizar después.
    """
    try:
        from skimage import measure
    except ImportError as exc:
        raise RuntimeError("Este experimento requiere scikit-image") from exc
    if side not in {"left", "right"}:
        raise ValueError("side debe ser left o right")

    cfg = load_config(config_path)
    spec, morph_box = _side_spec(cfg, side)
    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    mask = person_mask(front)
    roi = region_mask(mask, [float(v) for v in spec["box"]])
    hand = mask & roi
    ys, xs = np.where(hand)
    if not len(xs):
        raise RuntimeError("Referencia sin mano detectable")
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())

    contours = measure.find_contours(hand.astype(np.float32), 0.5)
    if not contours:
        raise RuntimeError("No se encontró contorno")
    # Preferimos el contorno más largo que recorra la zona distal de la mano.
    distal_x = x0 + (x1 - x0) * 0.35 if side == "left" else x1 - (x1 - x0) * 0.35
    viable = []
    for contour in contours:
        cols = contour[:, 1]
        reaches = float(cols.min()) <= distal_x if side == "left" else float(cols.max()) >= distal_x
        if reaches:
            viable.append(contour)
    contour = max(viable or contours, key=len)
    contour = measure.approximate_polygon(contour, tolerance=float(tolerance_px))
    if len(contour) > 96:
        step = int(np.ceil(len(contour) / 96.0))
        contour = contour[::step]
    if len(contour) < 8:
        raise RuntimeError(f"Contorno demasiado pobre: {len(contour)} puntos")

    mb = np.asarray(morph_box, dtype=float)
    w = max(float(x1 - x0), 1.0)
    h = max(float(y1 - y0), 1.0)
    points = []
    for row, col in contour:
        tx = float(np.clip((float(col) - x0) / w, 0.0, 1.0))
        ty = float(np.clip((float(row) - y0) / h, 0.0, 1.0))
        nx = float(mb[0] + tx * (mb[3] - mb[0]))
        nz = float(mb[5] - ty * (mb[5] - mb[2]))
        points.append([nx, nz])

    # Eliminar punto final duplicado si find_contours cierra explícitamente la curva.
    if len(points) > 2 and np.linalg.norm(np.asarray(points[0]) - np.asarray(points[-1])) < 1e-7:
        points.pop()

    result = {
        "mode": "reference_hand_outline_plan_v1",
        "side": side,
        "reference_driven": True,
        "invented_finger_count": False,
        "research_prototype": True,
        "promotion_allowed": False,
        "hand_roi_box": [float(v) for v in spec["box"]],
        "hand_morph_box": [float(v) for v in morph_box],
        "reference_hand_bbox_px": [x0, y0, x1, y1],
        "outline_points": points,
        "outline_point_count": len(points),
        "tolerance_px": float(tolerance_px),
        "learning": (
            "Contorno completo trazado desde la referencia frontal; no decide cuántos dedos existen. "
            "La forma se volumiza como una sola pieza en el siguiente paso."
        ),
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Traza mano 2D desde referencia para experimento de extrusión")
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--side", choices=("left", "right"), default="left")
    p.add_argument("--tolerance-px", type=float, default=1.25)
    a = p.parse_args()
    r = plan_outline(a.reference, a.config, a.output, a.side, a.tolerance_px)
    print(json.dumps({"side": r["side"], "outline_point_count": r["outline_point_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
