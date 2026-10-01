from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from copox.adapters.alth_character import ensure_runtime
from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_robust_extrude_plan import plan_robust_extruded_fingers
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _read, _sha256
from copox.production.finger_semantic_finish_trial import run_trial as run_semantic
from copox.production.module_gate import evaluate


VARIANTS = (
    {"segments": 2, "depth_scale": 0.68, "tip_scale": 0.88, "length_scale": 0.90},
    {"segments": 3, "depth_scale": 0.76, "tip_scale": 0.82, "length_scale": 0.96},
    {"segments": 3, "depth_scale": 0.84, "tip_scale": 0.78, "length_scale": 1.00},
)


def _copy_hand_evidence(root: Path, labels: set[str]) -> None:
    dst = root / "evidence"
    dst.mkdir(parents=True, exist_ok=True)
    src = root / "hand_detail_evidence"
    for side in ("left", "right"):
        p = src / f"hand_detail_{side}.png"
        if p.exists():
            shutil.copy2(p, dst / f"hand_{side}.png")
            labels.add(f"hand_{side}")


def run_trial(baseline: str, reference: str, config: str, policy_path: str, slot: int, output_dir: str) -> dict:
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    params = dict(VARIANTS[slot - 1])

    semantic_root = root / "semantic_base"
    semantic = run_semantic(baseline, reference, config, policy_path, 2, str(semantic_root))
    semantic_model = semantic_root / "model.glb"

    plan = plan_robust_extruded_fingers(reference, config, str(root / "robust_plan.json"), side="left")
    if int(plan.get("robust_valley_count", -1)) != 2 or int(plan.get("visible_band_count", -1)) != 3:
        raise RuntimeError(f"Esta referencia debe producir 2 valles/3 bandas robustas: {plan}")

    repo = Path.cwd().resolve()
    alth_python = ensure_runtime(repo)
    model = root / "model.glb"
    build_report = root / "robust_build.json"
    subprocess.run([
        alth_python,
        str((repo / "copox" / "adapters" / "finger_reference_extrude_build.py").resolve()),
        "--input", str(semantic_model.resolve()),
        "--plan", str((root / "robust_plan.json").resolve()),
        "--output", str(model.resolve()),
        "--report", str(build_report.resolve()),
        "--segments", str(params["segments"]),
        "--depth-scale", str(params["depth_scale"]),
        "--tip-scale", str(params["tip_scale"]),
        "--length-scale", str(params["length_scale"]),
    ], cwd=repo, check=True)
    build = _read(build_report)

    regional = audit_regions(baseline, str(model), reference, config, str(root / "regional_metrics.json"), str(root / "evidence"))
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

    full = audit_full(baseline, str(model), reference, "hair,profile", config, None, str(root / "full_metrics.json"), str(root / "full_evidence"))
    detail = hand_probe(str(model), reference, config, str(root / "hand_detail.json"), str(root / "hand_detail_evidence"))
    topology = topology_probe(str(model), str(root / "topology_report.json"))

    labels: set[str] = {"learning", "finger_detail", "topology_report"}
    _copy_hand_evidence(root, labels)
    semantic_ready = bool((detail.get("summary") or {}).get("definition_match", False))
    learning = {
        "mode": "semantic_finish_plus_robust_reference_extrusion",
        "research_applied": [
            "separate digit volumes with regular loop rings",
            "two robust reference valleys define exactly three visible bands",
            "semantic-finish c02 retained as proximal hand/body base",
        ],
        "robust_valleys": int(plan["robust_valley_count"]),
        "visible_bands": int(plan["visible_band_count"]),
        "model_valleys": (detail.get("summary") or {}).get("model_valleys"),
        "reference_valleys": (detail.get("summary") or {}).get("reference_valleys"),
        "bridge_to_palm_validated": False,
        "frozen_region_failures": failures,
        "promotion_executed": False,
    }
    (root / "learning.json").write_text(json.dumps(learning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    view_deltas = full["visual"]["full"]["delta_pp"]
    result = {
        "module": "fingers",
        "baseline_sha256": _sha256(baseline),
        "mesh_integrity": bool(build.get("mesh_integrity", False)),
        "scope_safe": False,
        "regression_ok": bool(not failures),
        "evidence_complete": {"hand_left", "hand_right", "finger_detail", "topology_report", "learning"} <= labels,
        "semantic_ready": semantic_ready,
        "target_gain_pp": float(target.get("delta_pp", 0.0)),
        "global_gain_pp": float(full["visual"].get("weighted_gain_pp", 0.0)),
        "worst_view_delta_pp": float(min(float(view_deltas[v]) for v in ("front", "side", "back", "threeq"))),
        "evidence": sorted(labels),
        "flags": sorted(set(["bridge_pending", "robust_extrude_prototype"] + ([] if semantic_ready else ["mitten_shape"]))),
        "params": {"technique": "semantic_plus_robust_valley_extrusion", **params},
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(_read(policy_path), result, baseline_model=baseline)
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    trial = {
        "slot": slot,
        "params": params,
        "semantic_base": semantic["result"],
        "plan": plan,
        "build": build,
        "topology": topology,
        "hand_detail": detail,
        "learning": learning,
        "result": result,
        "gate": gate,
        "promotion_executed": False,
    }
    (root / "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="Trial robusto de extrusión; learning-only")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    s = t["hand_detail"]["summary"]
    print(json.dumps({
        "slot": a.slot,
        "bands": t["plan"]["visible_band_count"],
        "reference_valleys": s.get("reference_valleys"),
        "model_valleys": s.get("model_valleys"),
        "semantic_ready": t["result"]["semantic_ready"],
        "target_gain_pp": t["result"]["target_gain_pp"],
        "global_gain_pp": t["result"]["global_gain_pp"],
        "worst_view_delta_pp": t["result"]["worst_view_delta_pp"],
        "promotion_executed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
