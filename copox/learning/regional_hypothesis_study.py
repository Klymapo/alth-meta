from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from copox.adapters.regional_reference_audit import audit_regions
from copox.adapters.regional_vertex_morph import morph


def run_study(
    baseline: str,
    reference: str,
    config: str,
    hypotheses_path: str,
    output_dir: str,
) -> dict[str, Any]:
    hypotheses = json.loads(Path(hypotheses_path).read_text(encoding="utf-8"))
    region = str(hypotheses["region"])
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for item in hypotheses.get("hypotheses", []):
        hid = str(item["id"])
        hdir = root / hid
        hdir.mkdir(parents=True, exist_ok=True)
        model = hdir / "model.glb"
        if item.get("baseline", False):
            shutil.copy2(baseline, model)
            morph_report = {"region": region, "mode": "baseline", "mesh_integrity": True}
        else:
            params = {
                "region": region,
                "scale": item.get("scale", [1.0, 1.0, 1.0]),
                "shift_mm": item.get("shift_mm", [0.0, 0.0, 0.0]),
            }
            params_path = hdir / "params.json"
            params_path.write_text(json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            morph_report = morph(baseline, config, params_path, model, hdir / "morph.json")

        audit = audit_regions(
            baseline,
            str(model),
            reference,
            config,
            str(hdir / "regional_metrics.json"),
            str(hdir / "evidence"),
        )
        region_metrics = audit["regions"][region]
        results.append({
            "id": hid,
            "label": item.get("label", hid),
            "curr_iou": float(region_metrics["curr_iou"]),
            "delta_pp": float(region_metrics["delta_pp"]),
            "visible_delta_pct": float(region_metrics["visible_delta_pct"]),
            "error_score": float(region_metrics["error_score"]),
            "morph": morph_report,
        })

    ranking = sorted(results, key=lambda x: (x["curr_iou"], x["delta_pp"]), reverse=True)
    baseline_result = next((x for x in results if x["id"] == "baseline"), None)
    winner = ranking[0] if ranking else None
    conclusion = "NO_CONCLUSION"
    if baseline_result and winner:
        if winner["id"] == "baseline":
            conclusion = "KEEP_BASELINE_GEOMETRY"
        elif winner["delta_pp"] > 0.0:
            conclusion = "HYPOTHESIS_IMPROVES_REFERENCE_MATCH"
        else:
            conclusion = "NO_HYPOTHESIS_IMPROVES_BASELINE"

    study = {
        "mode": "learning_only_no_promotion",
        "region": region,
        "results": results,
        "ranking": ranking,
        "best_hypothesis": winner["id"] if winner else None,
        "conclusion": conclusion,
        "promotion_allowed": False,
    }
    (root / "study.json").write_text(json.dumps(study, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return study


def main() -> int:
    p = argparse.ArgumentParser(description="Estudio regional de hipótesis, sólo aprendizaje")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--hypotheses", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    study = run_study(args.baseline, args.reference, args.config, args.hypotheses, args.output_dir)
    print(json.dumps({"region": study["region"], "best": study["best_hypothesis"], "conclusion": study["conclusion"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
