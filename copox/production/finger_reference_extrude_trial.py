from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from copox.adapters.alth_character import ensure_runtime
from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_reference_extrude_plan import plan_extruded_fingers
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _read, _sha256
from copox.production.module_gate import evaluate


VARIANTS = (
    {"segments": 2, "depth_scale": 0.72, "tip_scale": 0.88, "length_scale": 0.92},
    {"segments": 3, "depth_scale": 0.82, "tip_scale": 0.82, "length_scale": 1.00},
    {"segments": 4, "depth_scale": 0.90, "tip_scale": 0.76, "length_scale": 1.05},
)


def _copy_evidence(root: Path, labels: set[str]) -> None:
    dst = root / "evidence"
    dst.mkdir(parents=True, exist_ok=True)
    src = root / "hand_detail_evidence"
    for side in ("left", "right"):
        p = src / f"hand_detail_{side}.png"
        if p.exists():
            shutil.copy2(p, dst / f"hand_{side}.png")
            labels.add(f"hand_{side}")


def _side_row(detail: dict[str, Any], side: str) -> dict[str, Any]:
    for row in detail.get("hands") or []:
        if row.get("side") == side:
            return row
    raise RuntimeError(f"Probe sin mano {side}")


def run_trial(
    baseline: str,
    reference: str,
    config: str,
    policy_path: str,
    slot: int,
    output_dir: str,
) -> dict[str, Any]:
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    params = dict(VARIANTS[slot - 1])

    plan = plan_extruded_fingers(reference, config, str(root / "extrude_plan.json"), side="left")
    if int(plan.get("visible_band_count", 0)) < 2:
        raise RuntimeError(f"Referencia insuficiente para extrusión: {plan}")

    repo = Path.cwd().resolve()
    alth_python = ensure_runtime(repo)
    model = root / "model.glb"
    build_report = root / "extrude_build.json"
    subprocess.run([
        alth_python,
        str((repo / "copox" / "adapters" / "finger_reference_extrude_build.py").resolve()),
        "--input", str(Path(baseline).resolve()),
        "--plan", str((root / "extrude_plan.json").resolve()),
        "--output", str(model.resolve()),
        "--report", str(build_report.resolve()),
        "--segments", str(params["segments"]),
        "--depth-scale", str(params["depth_scale"]),
        "--tip-scale", str(params["tip_scale"]),
        "--length-scale", str(params["length_scale"]),
    ], cwd=repo, check=True)
    build = _read(build_report)

    regional = audit_regions(
        baseline, str(model), reference, config,
        str(root / "regional_metrics.json"), str(root / "evidence"),
    )
    target = regional["regions"]["fingers"]
    cfg = _read(config)
    tolerance = float((cfg.get("approval") or {}).get("freeze_tolerance_pp", -0.20))
    failures = []
    for name, data in regional["regions"].items():
        if name in {"fingers", "hands"}:
            continue
        delta = float(data.get("delta_pp", 0.0))
        if delta < tolerance:
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
        "mode": "internet_research_reference_extrusion_prototype",
        "research_applied": [
            "trace/reference-driven visible digit bands before volumizing",
            "regular loop rings along each digit",
            "distal geometry rebuilt instead of carving mitten gaps",
        ],
        "left_definition_match": left_definition,
        "left_component_gap": int(left.get("component_gap", 0)),
        "left_valley_count_gap": int(left.get("valley_count_gap", 0)),
        "reference_left_valleys": int((left.get("reference") or {}).get("valley_count", 0)),
        "model_left_valleys": int((left.get("model") or {}).get("valley_count", 0)),
        "bridge_to_palm_validated": False,
        "frozen_region_failures": failures,
        "note": (
            "Experimento aislado: valida si reconstruir dedos como volúmenes con loops supera mitten_shape. "
            "No se permite promoción hasta diseñar/validar bridge palma-dedos y repetir bilateral/multivista."
        ),
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
        "flags": sorted(set(
            ["research_extrude_prototype", "bridge_pending"]
            + ([] if full_definition else ["mitten_shape"])
        )),
        "params": {"technique": "reference_visible_digit_extrusion", **params},
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(_read(policy_path), result, baseline_model=baseline)
    if gate.get("promotion_allowed"):
        raise RuntimeError("Prototipo de investigación nunca debe ser promovible")
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    trial = {
        "slot": slot,
        "params": params,
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
    p = argparse.ArgumentParser(description="Trial learning-only de dedos extruidos desde referencia")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    l = t["learning"]
    print(json.dumps({
        "slot": a.slot,
        "visible_bands": t["plan"]["visible_band_count"],
        "left_definition_match": l["left_definition_match"],
        "left_valley_gap": l["left_valley_count_gap"],
        "target_gain_pp": t["result"]["target_gain_pp"],
        "global_gain_pp": t["result"]["global_gain_pp"],
        "worst_view_delta_pp": t["result"]["worst_view_delta_pp"],
        "promotion_allowed": t["gate"]["promotion_allowed"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
