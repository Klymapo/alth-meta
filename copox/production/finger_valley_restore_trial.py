from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_reference_valley_restore import restore_valleys
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _read, _sha256
from copox.production.finger_semantic_finish_trial import run_trial as run_semantic
from copox.production.module_gate import evaluate


STRENGTHS = (0.75, 1.00, 1.25)


def _left(detail: dict) -> dict:
    for row in detail.get("hands") or []:
        if row.get("side") == "left":
            return row
    raise RuntimeError("Probe sin mano izquierda")


def _copy_hand_evidence(root: Path, labels: set[str]) -> None:
    ev = root / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    src = root / "hand_detail_evidence"
    for side in ("left", "right"):
        p = src / f"hand_detail_{side}.png"
        if p.exists():
            shutil.copy2(p, ev / f"hand_{side}.png")
            labels.add(f"hand_{side}")


def run_trial(baseline: str, reference: str, config: str, policy_path: str, slot: int, output_dir: str) -> dict:
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Partimos del semantic-finish c02: fue el candidato estable con todos los gates
    # técnicos verdes salvo la lectura tipo mitten_shape.
    semantic_root = root / "semantic_base"
    semantic = run_semantic(baseline, reference, config, policy_path, 2, str(semantic_root))
    semantic_model = semantic_root / "model.glb"
    base_detail = semantic["extra"]["hand_detail"]
    left = _left(base_detail)
    valleys = list((left.get("reference") or {}).get("valleys") or [])
    if len(valleys) != int((left.get("reference") or {}).get("valley_count", -1)):
        raise RuntimeError("Conteo/bboxes de valles de referencia inconsistente")
    if not valleys:
        raise RuntimeError("La referencia no contiene valles visibles para restaurar")

    plan = {
        "mode": "reference_valley_restore_plan",
        "side": "left",
        "reference_driven": True,
        "invented_finger_count": False,
        "valley_count": len(valleys),
        "valleys": valleys,
        "source": "hand_detail_probe_v2.reference",
    }
    plan_path = root / "valley_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    strength = float(STRENGTHS[slot - 1])
    model = root / "model.glb"
    restore = restore_valleys(
        str(semantic_model), reference, config, str(plan_path),
        str(model), str(root / "valley_restore.json"), strength,
    )

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
    topology = topology_probe(str(model), str(root / "topology_report.json"))

    labels: set[str] = {"learning", "finger_detail", "topology_report"}
    _copy_hand_evidence(root, labels)
    learning = {
        "mode": "semantic_shape_plus_reference_valley_restore",
        "research_applied": [
            "preserve the successful semantic-finish silhouette",
            "restore only valleys explicitly visible in the reference",
            "modify distal edge by vertex displacement instead of boolean carving",
        ],
        "semantic_base_strength": 1.20,
        "valley_restore_strength": strength,
        "reference_left_valleys": int((_left(detail).get("reference") or {}).get("valley_count", 0)),
        "model_left_valleys": int((_left(detail).get("model") or {}).get("valley_count", 0)),
        "frozen_region_failures": failures,
        "promotion_executed": False,
    }
    (root / "learning.json").write_text(json.dumps(learning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    semantic_ready = bool((detail.get("summary") or {}).get("definition_match", False))
    view_deltas = full["visual"]["full"]["delta_pp"]
    result = {
        "module": "fingers",
        "baseline_sha256": _sha256(baseline),
        "mesh_integrity": bool(restore.get("mesh_integrity", False)),
        "scope_safe": bool(semantic["result"].get("scope_safe", False) and restore.get("outside_scope_exact", False)),
        "regression_ok": bool(not failures),
        "evidence_complete": {"hand_left", "hand_right", "finger_detail", "topology_report", "learning"} <= labels,
        "semantic_ready": semantic_ready,
        "target_gain_pp": float(target.get("delta_pp", 0.0)),
        "global_gain_pp": float(full["visual"].get("weighted_gain_pp", 0.0)),
        "worst_view_delta_pp": float(min(float(view_deltas[v]) for v in ("front", "side", "back", "threeq"))),
        "evidence": sorted(labels),
        "flags": [] if semantic_ready else ["mitten_shape"],
        "params": {
            "technique": "semantic_finish_plus_reference_valley_restore",
            "semantic_strength": 1.20,
            "valley_strength": strength,
            "reference_valleys": len(valleys),
        },
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(_read(policy_path), result, baseline_model=baseline)
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    trial = {
        "slot": slot,
        "params": result["params"],
        "semantic_base": {
            "target_gain_pp": semantic["result"]["target_gain_pp"],
            "global_gain_pp": semantic["result"]["global_gain_pp"],
            "semantic_ready": semantic["result"]["semantic_ready"],
        },
        "plan": plan,
        "restore": restore,
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
    p = argparse.ArgumentParser(description="COPOX hybrid valley-restore experiment; nunca promociona")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    d = t["hand_detail"]["summary"]
    print(json.dumps({
        "slot": a.slot,
        "reference_valleys": d.get("reference_valleys"),
        "model_valleys": d.get("model_valleys"),
        "semantic_ready": t["result"]["semantic_ready"],
        "target_gain_pp": t["result"]["target_gain_pp"],
        "global_gain_pp": t["result"]["global_gain_pp"],
        "worst_view_delta_pp": t["result"]["worst_view_delta_pp"],
        "gate_would_allow_promotion": t["gate"]["promotion_allowed"],
        "promotion_executed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
