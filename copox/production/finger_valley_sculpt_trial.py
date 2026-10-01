from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_reference_fit import fit_fingers
from copox.adapters.finger_valley_sculpt import sculpt_valleys
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _copy_hand_evidence, _read, _sha256
from copox.production.module_gate import evaluate
from copox.production.regional_trial import _refine_finger_topology


SCULPT_STRENGTHS = (0.55, 0.75, 0.95)
CONTOUR_STRENGTH = 1.20


def _dominant_topology(report: dict) -> dict:
    rows = list(report.get("geometries") or [])
    if not rows:
        return {}
    return max(rows, key=lambda r: int(r.get("vertices", 0)))


def run_trial(baseline: str, reference: str, config: str, policy_path: str, slot: int, output_dir: str):
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    sculpt_strength = SCULPT_STRENGTHS[slot - 1]

    refined_input, refine = _refine_finger_topology(baseline, config, root, 1)

    # Conservamos la silueta exterior del semantic-finish c02.
    contoured = root / "contoured.glb"
    contour = fit_fingers(
        refined_input, reference, config, str(contoured), str(root / "contour_report.json"),
        strength=CONTOUR_STRENGTH,
    )

    # Después abrimos sólo los valles robustos, sin booleans ni cambios de conectividad.
    model = root / "model.glb"
    sculpt = sculpt_valleys(
        baseline, str(contoured), reference, config, str(model), str(root / "sculpt_report.json"),
        strength=sculpt_strength, length_scale=1.0,
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
        baseline, str(model), reference, "hands,fingers", config,
        None, str(root / "full_metrics.json"), str(root / "full_evidence"),
    )
    detail = hand_probe(str(model), reference, config, str(root / "hand_detail.json"), str(root / "hand_detail_evidence"))
    topology = topology_probe(str(model), str(root / "topology_report.json"))
    dominant = _dominant_topology(topology)
    welded = dominant.get("welded_topology") or {}

    labels = {"learning", "finger_detail", "topology_report"}
    _copy_hand_evidence(root, labels)
    semantic_ready = bool(detail.get("summary", {}).get("definition_match", False))

    # Alpha/contour ya puede contener boundary edges por su representación GLB.
    # Sculpt no cambia conectividad: exigimos cuentas preservadas, UV presentes y
    # ninguna cara degenerada/non-manifold nueva en la dominante, no closed-manifold absoluto.
    topology_ok = bool(
        dominant.get("valid", False)
        and int(welded.get("nonmanifold_edges", 0)) == 0
        and int(welded.get("degenerate_faces", 0)) == 0
        and sculpt.get("topology_counts_preserved", False)
    )
    uv_ok = bool((dominant.get("uv") or {}).get("available", False))
    scope_ok = bool(
        refine.get("safe_geometry_regression", False)
        and contour.get("outside_scope_exact", False)
        and sculpt.get("outside_scope_exact", False)
        and sculpt.get("topology_counts_preserved", False)
    )
    regression_ok = bool(not failures and topology_ok and uv_ok)

    flags = []
    if not semantic_ready:
        flags.append("mitten_shape")
    if not topology_ok or not uv_ok or not sculpt.get("topology_counts_preserved", False):
        flags.append("finger_topology_regression")

    learning = {
        "mode": "topology_contour_valley_surface_sculpt_v2",
        "topology_cuts": 1,
        "contour_strength": CONTOUR_STRENGTH,
        "sculpt_strength": sculpt_strength,
        "reference_valley_count": sculpt.get("reference_valley_count"),
        "definition_match": semantic_ready,
        "target_delta_pp": float(target.get("delta_pp", 0.0)),
        "frozen_region_failures": failures,
        "dominant_topology": {
            "boundary_edges": int(welded.get("boundary_edges", 0)),
            "nonmanifold_edges": int(welded.get("nonmanifold_edges", 0)),
            "degenerate_faces": int(welded.get("degenerate_faces", 0)),
            "uv_available": uv_ok,
        },
        "note": "No usa booleanos ni soldadura. Closed-manifold absoluto no se exige porque Alpha ya conserva bordes abiertos; se veta cualquier nonmanifold/degenerado y cualquier cambio de conteo topológico.",
    }
    (root / "learning.json").write_text(json.dumps(learning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    view_deltas = full["visual"]["full"]["delta_pp"]
    result = {
        "module": "fingers",
        "baseline_sha256": _sha256(baseline),
        "mesh_integrity": bool(contour.get("mesh_integrity", False) and sculpt.get("mesh_integrity", False) and topology_ok),
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
            "technique": "topology_1cut_contour_then_relative_valley_surface_sculpt",
            "topology_cuts": 1,
            "contour_strength": CONTOUR_STRENGTH,
            "sculpt_strength": sculpt_strength,
        },
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(_read(policy_path), result, baseline_model=baseline)
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trial = {
        "slot": slot,
        "refine": refine,
        "contour": contour,
        "sculpt": sculpt,
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
    p = argparse.ArgumentParser(description="COPOX valley surface sculpt trial; nunca promociona")
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
        "sculpt_strength": SCULPT_STRENGTHS[a.slot - 1],
        "semantic_ready": t["result"]["semantic_ready"],
        "reference_valleys": d.get("reference_valleys"),
        "model_valleys": d.get("model_valleys"),
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
