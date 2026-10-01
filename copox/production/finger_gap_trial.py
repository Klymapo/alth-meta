from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from copox.adapters.alth_character import ensure_runtime
from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_gap_plan import plan_gaps
from copox.adapters.finger_reference_fit import fit_fingers
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.module_gate import evaluate


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _variant(slot: int) -> tuple[float, float, float]:
    # Ranura, longitud vertical, y fuerza de reconstrucción del borde exterior.
    variants = (
        (0.78, 0.86, 0.55),
        (0.92, 0.94, 0.82),
        (1.04, 1.00, 1.05),
    )
    return variants[(max(1, slot) - 1) % len(variants)]


def _copy_hand_evidence(root: Path, labels: set[str]) -> None:
    src = root / "hand_detail_evidence"
    dst = root / "evidence"
    dst.mkdir(parents=True, exist_ok=True)
    for side in ("left", "right"):
        p = src / f"hand_detail_{side}.png"
        if p.exists():
            shutil.copy2(p, dst / f"hand_{side}.png")
            labels.add(f"hand_{side}")


def run_trial(baseline: str, reference: str, config: str, policy_path: str, slot: int, output_dir: str) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    width_scale, length_scale, contour_strength = _variant(slot)

    plan = plan_gaps(
        baseline, reference, config, str(root / "gap_plan.json"),
        width_scale=width_scale, length_scale=length_scale,
    )
    if not plan.get("ready"):
        raise RuntimeError("La referencia no produjo huecos utilizables para dedos")

    repo = Path.cwd().resolve()
    alth_python = ensure_runtime(repo)
    carved_model = root / "carved_model.glb"
    carve_report = root / "carve_report.json"
    subprocess.run([
        alth_python, str((repo / "copox" / "adapters" / "finger_gap_carve.py").resolve()),
        "--input", str(Path(baseline).resolve()),
        "--plan", str((root / "gap_plan.json").resolve()),
        "--output", str(carved_model.resolve()),
        "--report", str(carve_report.resolve()),
    ], cwd=repo, check=True)
    carve = _read(carve_report)

    # Segunda fase: una vez que las bandas ya no están pegadas topológicamente,
    # ajustamos el borde distal de cada fila a la silueta real. Antes de los huecos,
    # este mismo fit sólo deformaba una manopla continua.
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

    labels: set[str] = {"learning", "finger_detail", "topology_report"}
    _copy_hand_evidence(root, labels)
    semantic_ready = bool(detail.get("summary", {}).get("definition_match", False))
    topology_ok = bool(topology.get("summary", {}).get("dominant_welds_to_closed_manifold", False))
    uv_ok = bool(carve.get("uv_layers_preserved", False) and topology.get("summary", {}).get("dominant_has_uv_seams", False))
    scope_ok = bool(carve.get("scope_safe", False) and contour.get("outside_scope_exact", False))
    regression_ok = bool(not failures and uv_ok and topology_ok)

    flags: list[str] = []
    if not semantic_ready:
        flags.append("mitten_shape")
    if not topology_ok or not uv_ok:
        flags.append("finger_merge_regression")

    learning = {
        "mode": "reference_gap_plus_contour_learning",
        "strategy": "KEEP_DIRECTION" if float(target.get("delta_pp", 0.0)) > 0 and semantic_ready else "ROTATE_TECHNIQUE",
        "target_delta_pp": float(target.get("delta_pp", 0.0)),
        "definition_match": semantic_ready,
        "cutter_count": int(plan.get("cutter_count", 0)),
        "width_scale": width_scale,
        "length_scale": length_scale,
        "contour_strength": contour_strength,
        "frozen_region_failures": failures,
        "note": "Primero se abren valles derivados de la referencia y después se reconstruye el borde distal por fila. El gate sigue vetando cualquier candidato que conserve mitten_shape o dañe topología/UV.",
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
            "technique": "reference_gap_plus_contour",
            "width_scale": width_scale,
            "length_scale": length_scale,
            "contour_strength": contour_strength,
        },
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    policy = _read(policy_path)
    gate = evaluate(policy, result, baseline_model=baseline)
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trial = {
        "slot": slot,
        "plan": plan,
        "carve": carve,
        "contour": contour,
        "hand_detail": detail,
        "topology": topology,
        "result": result,
        "gate": gate,
        "promotion_executed": False,
    }
    (root / "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="Torneo experimental gap+contour de dedos; nunca promociona")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    trial = run_trial(args.baseline, args.reference, args.config, args.policy, args.slot, args.output_dir)
    print(json.dumps({
        "slot": args.slot,
        "promotion_allowed": trial["gate"]["promotion_allowed"],
        "reasons": trial["gate"]["reasons"],
        "definition_match": trial["result"]["semantic_ready"],
        "target_gain_pp": trial["result"]["target_gain_pp"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
