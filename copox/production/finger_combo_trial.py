from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from copox.adapters.alth_character import ensure_runtime
from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_gap_plan import plan_gaps
from copox.adapters.finger_reference_fit import fit_fingers
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _copy_hand_evidence, _read, _sha256
from copox.production.module_gate import evaluate
from copox.production.regional_trial import _refine_finger_topology


# Alrededor del mejor gap previo (1.04/1.00/1.05) y del mejor contour+topology (1.10).
VARIANTS = (
    (0.98, 0.98, 1.05),
    (1.04, 1.00, 1.10),
    (1.08, 1.02, 1.20),
)


def run_trial(baseline: str, reference: str, config: str, policy_path: str, slot: int, output_dir: str):
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    width_scale, length_scale, contour_strength = VARIANTS[slot - 1]

    # 1) Aumentar grados de libertad sin mover la superficie original.
    refined_input, refine = _refine_finger_topology(baseline, config, root, 1)

    # 2) Los valles siguen derivándose de la referencia y del registro contra Alpha.
    plan = plan_gaps(
        baseline, reference, config, str(root / "gap_plan.json"),
        width_scale=width_scale, length_scale=length_scale,
    )
    if not plan.get("ready"):
        raise RuntimeError("La referencia no produjo huecos utilizables para dedos")

    # 3) Tallar esos valles sobre la versión refinada, no sobre una manopla de baja libertad.
    repo = Path.cwd().resolve()
    alth_python = ensure_runtime(repo)
    carved_model = root / "carved_model.glb"
    carve_report = root / "carve_report.json"
    subprocess.run([
        alth_python, str((repo / "copox" / "adapters" / "finger_gap_carve.py").resolve()),
        "--input", str(Path(refined_input).resolve()),
        "--plan", str((root / "gap_plan.json").resolve()),
        "--output", str(carved_model.resolve()),
        "--report", str(carve_report.resolve()),
    ], cwd=repo, check=True)
    carve = _read(carve_report)

    # 4) Reconstruir el borde exterior usando el Z-up corregido.
    model = root / "model.glb"
    contour = fit_fingers(
        str(carved_model), reference, config, str(model), str(root / "contour_report.json"),
        strength=contour_strength,
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

    labels = {"learning", "finger_detail", "topology_report"}
    _copy_hand_evidence(root, labels)
    semantic_ready = bool(detail.get("summary", {}).get("definition_match", False))
    topology_ok = bool(topology.get("summary", {}).get("dominant_welds_to_closed_manifold", False))
    uv_ok = bool(carve.get("uv_layers_preserved", False) and topology.get("summary", {}).get("dominant_has_uv_seams", False))
    scope_ok = bool(
        refine.get("safe_geometry_regression", False)
        and carve.get("scope_safe", False)
        and contour.get("outside_scope_exact", False)
    )
    regression_ok = bool(not failures and uv_ok and topology_ok)

    flags = []
    if not semantic_ready:
        flags.append("mitten_shape")
    if not topology_ok or not uv_ok:
        flags.append("finger_merge_regression")

    learning = {
        "mode": "topology_gap_contour_learning",
        "topology_cuts": 1,
        "cutter_count": int(plan.get("cutter_count", 0)),
        "width_scale": width_scale,
        "length_scale": length_scale,
        "contour_strength": contour_strength,
        "definition_match": semantic_ready,
        "target_delta_pp": float(target.get("delta_pp", 0.0)),
        "frozen_region_failures": failures,
        "note": "Combina exclusivamente los tres componentes que mejoraron evidencia previa: una subdivisión segura, valles de referencia y contour-fit Z-up corregido.",
    }
    (root / "learning.json").write_text(json.dumps(learning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    view_deltas = full["visual"]["full"]["delta_pp"]
    result = {
        "module": "fingers",
        "baseline_sha256": _sha256(baseline),
        "mesh_integrity": bool(carve.get("mesh_integrity", False) and contour.get("mesh_integrity", False) and topology_ok),
        "scope_safe": scope_ok,
        "regression_ok": regression_ok,
        "evidence_complete": {"hand_left", "hand_right", "finger_detail", "topology_report", "learning"} <= labels,
        "semantic_ready": semantic_ready,
        "target_gain_pp": float(target.get("delta_pp", 0.0)),
        "global_gain_pp": float(full["visual"].get("weighted_gain_pp", 0.0)),
        "worst_view_delta_pp": float(min(float(view_deltas[v]) for v in ("front", "side", "back", "threeq"))),
        "evidence": sorted(labels),
        "flags": sorted(set(flags)),
        "params": {
            "technique": "topology_1cut_plus_reference_gap_plus_contour",
            "topology_cuts": 1,
            "width_scale": width_scale,
            "length_scale": length_scale,
            "contour_strength": contour_strength,
        },
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(_read(policy_path), result, baseline_model=baseline)
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trial = {
        "slot": slot,
        "refine": refine,
        "plan": plan,
        "carve": carve,
        "contour": contour,
        "hand_detail": detail,
        "topology": topology,
        "learning": learning,
        "result": result,
        "gate": gate,
        "promotion_executed": False,
    }
    (root / "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="COPOX topology+gap+contour finger trial; nunca promociona")
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
        "semantic_ready": t["result"]["semantic_ready"],
        "vertical_run_gap": d.get("mean_vertical_run_gap"),
        "valley_gap": d.get("mean_valley_count_gap"),
        "target_gain_pp": t["result"]["target_gain_pp"],
        "global_gain_pp": t["result"]["global_gain_pp"],
        "worst_view_delta_pp": t["result"]["worst_view_delta_pp"],
        "promotion_allowed": t["gate"]["promotion_allowed"],
        "reasons": t["gate"]["reasons"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
