from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from copox.adapters.regional_reference_audit import audit_regions
from copox.adapters.regional_vertex_morph import morph
from copox.learning.regional_diagnosis import diagnose


def run_process(
    baseline: str,
    reference: str,
    config: str,
    region: str,
    params: dict[str, Any],
    output_dir: str,
    freeze_tolerance_pp: float = -0.20,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    params = dict(params)
    params["region"] = region
    params_path = root / "params.json"
    params_path.write_text(json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    model = root / "model.glb"
    morph_report = morph(baseline, config, params_path, model, root / "morph.json")
    regional = audit_regions(
        baseline,
        str(model),
        reference,
        config,
        str(root / "regional_metrics.json"),
        str(root / "evidence"),
    )
    learning = diagnose(root / "regional_metrics.json", root / "learning.json", [region])

    regressions = []
    for name, data in regional["regions"].items():
        if name == region:
            continue
        delta = float(data.get("delta_pp", 0.0))
        if delta < freeze_tolerance_pp:
            regressions.append({"region": name, "delta_pp": delta})
    target = regional["regions"].get(region, {})
    result = {
        "mode": "regional_m4_process",
        "region": region,
        "capabilities": {
            "evidence": True,
            "auditor": True,
            "mutator": True,
            "learning": True,
            "regression": True,
        },
        "morph": morph_report,
        "target_metrics": target,
        "learning": learning,
        "regression": {
            "ok": not regressions,
            "freeze_tolerance_pp": freeze_tolerance_pp,
            "failed_regions": regressions,
        },
        "technically_m4_ready": bool(
            morph_report.get("mesh_integrity")
            and morph_report.get("safe_scope")
            and target
        ),
        "promotion_allowed": False,
    }
    (root / "process.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Proceso regional M4: evidencia+auditor+mutator+learning+regression")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--params")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--freeze-tolerance-pp", type=float, default=-0.20)
    args = p.parse_args()
    params = {"scale": [0.995, 0.995, 0.995], "shift_mm": [0.0, 0.0, 0.0]}
    if args.params:
        params.update(json.loads(Path(args.params).read_text(encoding="utf-8")))
    result = run_process(args.baseline, args.reference, args.config, args.region, params, args.output_dir, args.freeze_tolerance_pp)
    print(json.dumps({"region": args.region, "m4": result["technically_m4_ready"], "regression": result["regression"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
