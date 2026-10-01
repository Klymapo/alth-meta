from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from copox.adapters.alth_character import ensure_runtime
from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_reference_outline_plan import plan_outline
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _read, _sha256
from copox.production.module_gate import evaluate


DEPTHS = (0.55, 0.72, 0.90)
TOLERANCES = (1.75, 1.25, 0.85)


def _copy_evidence(root: Path, labels: set[str]) -> None:
    dst = root / "evidence"
    dst.mkdir(parents=True, exist_ok=True)
    for side in ("left", "right"):
        p = root / "hand_detail_evidence" / f"hand_detail_{side}.png"
        if p.exists():
            shutil.copy2(p, dst / f"hand_{side}.png")
            labels.add(f"hand_{side}")


def _side_row(detail: dict[str, Any], side: str) -> dict[str, Any]:
    for row in detail.get("hands") or []:
        if row.get("side") == side:
            return row
    raise RuntimeError(f"Probe sin {side}")


def run_trial(baseline: str, reference: str, config: str, policy_path: str, slot: int, output_dir: str):
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    depth = float(DEPTHS[slot - 1])
    tolerance_px = float(TOLERANCES[slot - 1])

    plan = plan_outline(reference, config, str(root / "outline_plan.json"), side="left", tolerance_px=tolerance_px)
    repo = Path.cwd().resolve()
    alth_python = ensure_runtime(repo)
    model = root / "model.glb"
    build_report = root / "outline_build.json"
    subprocess.run([
        alth_python,
        str((repo / "copox" / "adapters" / "finger_reference_outline_build.py").resolve()),
        "--input", str(Path(baseline).resolve()),
        "--plan", str((root / "outline_plan.json").resolve()),
        "--output", str(model.resolve()),
        "--report", str(build_report.resolve()),
        "--depth-scale", str(depth),
    ], cwd=repo, check=True)
    build = _read(build_report)

    regional = audit_regions(
        baseline, str(model), reference, config,
        str(root / "regional_metrics.json"), str(root / "evidence"),
    )
    target = regional["regions"]["fingers"]
    cfg = _read(config)
    freeze = float((cfg.get("approval") or {}).get("freeze_tolerance_pp", -0.20))
    failures = []
    for name, data in regional["regions"].items():
        if name in {"fingers", "hands"}:
            continue
        delta = float(data.get("delta_pp", 0.0))
        if delta < freeze:
            failures.append({"region": name, "delta_pp": delta})

    full = audit_full(
        baseline, str(model), reference, "hair,profile", config,
        None, str(root / "full_metrics.json"), str(root / "full_evidence"),
    )
    detail = hand_probe(str(model), reference, config, str(root / "hand_detail.json"), str(root / "hand_detail_evidence"))
    left = _side_row(detail, "left")
    left_definition = bool(int(left.get("component_gap", 99)) == 0 and int(left.get("valley_count_gap", 99)) == 0)
    full_definition = bool(detail.get("summary", {}).get("definition_match", False))

    labels: set[str] = {"learning", "finger_detail"}
    _copy_evidence(root, labels)
    learning = {
        "mode": "internet_research_full_outline_then_volume",
        "research_applied": [
            "trace complete flat hand outline from reference",
            "give the traced form volume only after silhouette is established",
            "defer deformation topology/bridge until visual hypothesis is proven",
        ],
        "left_definition_match": left_definition,
        "left_component_gap": int(left.get("component_gap", 0)),
        "left_valley_count_gap": int(left.get("valley_count_gap", 0)),
        "reference_left_valleys": int((left.get("reference") or {}).get("valley_count", 0)),
        "model_left_valleys": int((left.get("model") or {}).get("valley_count", 0)),
        "bridge_to_wrist_validated": False,
        "outline_point_count": int(plan.get("outline_point_count", 0)),
        "frozen_region_failures": failures,
    }
    (root / "learning.json").write_text(json.dumps(learning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    view_deltas = full["visual"]["full"]["delta_pp"]
    result = {
        "module": "fingers",
        "baseline_sha256": _sha256(baseline),
        "mesh_integrity": bool(build.get("mesh_integrity", False)),
        "scope_safe": False,
        "regression_ok": bool(not failures),
        "evidence_complete": {"hand_left", "hand_right", "finger_detail", "learning"} <= labels,
        "semantic_ready": full_definition,
        "target_gain_pp": float(target.get("delta_pp", 0.0)),
        "global_gain_pp": float(full["visual"].get("weighted_gain_pp", 0.0)),
        "worst_view_delta_pp": float(min(float(view_deltas[v]) for v in ("front", "side", "back", "threeq"))),
        "evidence": sorted(labels),
        "flags": sorted(set(["research_outline_prototype", "bridge_pending"] + ([] if full_definition else ["mitten_shape"]))),
        "params": {"technique": "reference_full_outline_extrusion", "depth_scale": depth, "tolerance_px": tolerance_px},
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(_read(policy_path), result, baseline_model=baseline)
    if gate.get("promotion_allowed"):
        raise RuntimeError("Prototipo outline nunca puede promocionarse")
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trial = {
        "slot": slot,
        "plan": plan,
        "build": build,
        "hand_detail": detail,
        "learning": learning,
        "result": result,
        "gate": gate,
        "promotion_executed": False,
    }
    (root / "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p=argparse.ArgumentParser(description="Trial de contorno 2D→volumen, learning-only")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a=p.parse_args()
    t=run_trial(a.baseline,a.reference,a.config,a.policy,a.slot,a.output_dir)
    l=t["learning"]
    print(json.dumps({
        "slot":a.slot,
        "outline_points":l["outline_point_count"],
        "left_definition_match":l["left_definition_match"],
        "left_valley_gap":l["left_valley_count_gap"],
        "target_gain_pp":t["result"]["target_gain_pp"],
        "global_gain_pp":t["result"]["global_gain_pp"],
        "worst_view_delta_pp":t["result"]["worst_view_delta_pp"],
        "promotion_allowed":t["gate"]["promotion_allowed"],
    },ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
