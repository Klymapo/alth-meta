from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REGION_TO_MODULE = {
    "whole_body_silhouette": "whole_body_silhouette",
    "head_shape": "head_shape",
    "hair": "hair",
    "ears": "ears",
    "face": "face",
    "neck": "neck",
    "torso": "torso",
    "shoulders": "shoulders",
    "arms": "arms",
    "elbows_forearms": "elbows_forearms",
    "hands": "hands",
    "fingers": "fingers",
    "pelvis_hips": "pelvis_hips",
    "legs": "legs",
    "knees": "knees",
    "ankles": "ankles",
    "feet_footwear": "feet_footwear",
}

LEARNING_BOOST = {"ears": 1.0, "hands": 0.9, "fingers": 1.0}


def build(regional_metrics: dict[str, Any]) -> dict[str, Any]:
    modules: dict[str, Any] = {}
    for region, data in (regional_metrics.get("regions") or {}).items():
        module = REGION_TO_MODULE.get(region)
        if not module:
            continue
        error_pct = max(0.0, float(data.get("error_score", 0.0)))
        modules[module] = {
            "error": error_pct / 100.0,
            "confidence": 1.0,
            "learning_need": LEARNING_BOOST.get(module, 0.25),
            "actionable": True,
            "reason": f"regional_error={error_pct:.3f}%",
            "source": region,
        }

    regional_errors = [x["error"] for name, x in modules.items() if name != "whole_body_silhouette"]
    mean_regional = sum(regional_errors) / max(len(regional_errors), 1)
    modules["global_proportions"] = {
        "error": mean_regional,
        "confidence": 0.5,
        "learning_need": 0.15,
        "actionable": True,
        "reason": "proxy_from_mean_regional_error",
    }
    # Los módulos técnicos existen y son M5, pero se activan sólo cuando un diagnóstico
    # específico indique que son la causa del mismatch; no compiten por defecto con forma.
    for module in ("materials_colors", "mesh_topology", "orientation", "rig_readiness", "facial_animation_readiness"):
        modules[module] = {
            "error": 0.0,
            "confidence": 1.0,
            "learning_need": 0.0,
            "actionable": False,
            "reason": "deferred_until_specific_signal",
        }
    return {"mode": "reference_driven_module_diagnostics", "modules": modules}


def main() -> int:
    p = argparse.ArgumentParser(description="Convierte auditoría regional a diagnóstico del router M5")
    p.add_argument("--regional-metrics", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    data = json.loads(Path(args.regional_metrics).read_text(encoding="utf-8"))
    result = build(data)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
