from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def diagnose(candidate_report: str, regional_path: str, output: str) -> dict:
    candidate = json.loads(Path(candidate_report).read_text(encoding="utf-8"))
    regional = json.loads(Path(regional_path).read_text(encoding="utf-8"))
    geometry_ok = bool(candidate.get("safe_geometry_regression") and candidate.get("original_vertices_unchanged") and candidate.get("surface_unchanged"))
    density_ok = bool(candidate.get("topology_density_increased") and candidate.get("selected_faces", 0) > 0)
    uv_ok = bool(candidate.get("uv_layers", 0) > 0 and candidate.get("uv_layers_preserved"))
    # The rasterizer quantizes subdivided edge points. Use the same regional
    # mean tolerance as integration; exact surface checks above independently
    # veto geometric changes, including added vertices leaving the old surface.
    deltas = [float(d["delta_pp"]) for d in regional.get("regions", {}).values()]
    view_deltas = [float(v["delta_pp"]) for d in regional.get("regions", {}).values() for v in d.get("views", [d])]
    regression_ok = bool(deltas and all(math.isfinite(x) and abs(x) < 0.05 for x in deltas))
    if not geometry_ok:
        action = "RESTORE_ORIGINAL_VERTEX_POSITIONS"
    elif not uv_ok:
        action = "RESTORE_UV_LAYERS"
    elif not density_ok:
        action = "REVISE_LOCAL_SELECTION"
    elif not regression_ok:
        action = "FIX_EXPORT_REGRESSION"
    else:
        action = "REFINE_LOCAL_DETAIL_WITH_REFERENCE"
    result = {
        "mode": "topology_learning",
        "ready_for_m4_process": bool(geometry_ok and density_ok and uv_ok and regression_ok),
        "action": action,
        "geometry_preserved": geometry_ok,
        "local_density_increased": density_ok,
        "uv_available": uv_ok,
        "regression_ok": regression_ok,
        "max_regional_delta_pp": max((abs(x) for x in deltas), default=None),
        "max_view_raster_delta_pp": max((abs(x) for x in view_deltas), default=None),
        "promotion_allowed": False,
        "learning": "La subdivisión ofrece detalle local sin definir todavía dedos ni uniones. Cualquier modelado posterior necesita comparación contra referencia y revisión de UV/normales.",
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnóstico de refinamiento topológico local")
    p.add_argument("--candidate-report", required=True)
    p.add_argument("--regional", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = diagnose(args.candidate_report, args.regional, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ready_for_m4_process"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
