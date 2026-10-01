from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from copox.adapters.alth_character_audit import audit as audit_full
from copox.adapters.finger_reference_fit import fit_fingers
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_process import run_process
from copox.adapters.regional_reference_audit import audit_regions
from copox.adapters.uv_region_probe import probe as uv_probe
from copox.production.module_gate import evaluate


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _variant(module: str, slot: int, tournament: int = 1) -> dict[str, Any]:
    if module == "ears":
        scales = ([0.70, 0.70, 0.70], [0.40, 0.40, 0.40], [0.10, 0.10, 0.10])
        return {"scale": list(scales[(slot - 1) % 3]), "shift_mm": [0.0, 0.0, 0.0]}
    if module == "fingers":
        strengths = (0.35, 0.65, 1.00) if tournament % 2 else (0.50, 0.80, 1.15)
        return {"strength": float(strengths[(slot - 1) % 3])}
    variants = [
        [0.98, 1.00, 1.00],
        [1.02, 1.00, 1.00],
        [1.00, 0.98 if tournament % 2 else 1.02, 1.00],
    ]
    return {"scale": list(variants[(slot - 1) % 3]), "shift_mm": [0.0, 0.0, 0.0]}


def _copy_region_evidence(root: Path, module: str, labels: set[str]) -> None:
    ev = root / "evidence"
    for view in ("front", "side", "back", "threeq"):
        hits = sorted(ev.glob(f"region_{module}_{view}_*.png"))
        if hits:
            shutil.copy2(hits[0], ev / f"region_{view}.png")
            labels.add(f"region_{view}")


def _finger_process(baseline: str, reference: str, config: str, params: dict[str, Any], root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    model = root / "model.glb"
    morph = fit_fingers(
        baseline, reference, config, str(model), str(root / "morph.json"),
        float(params.get("strength", 0.65)),
    )
    regional = audit_regions(
        baseline, str(model), reference, config,
        str(root / "regional_metrics.json"), str(root / "evidence"),
    )
    target = regional["regions"]["fingers"]
    cfg = _read(config)
    tolerance = float((cfg.get("approval") or {}).get("freeze_tolerance_pp", -0.20))
    coupled = {"fingers", "hands"}
    failures = []
    for name, data in regional["regions"].items():
        if name in coupled:
            continue
        delta = float(data.get("delta_pp", 0.0))
        if delta < tolerance:
            failures.append({"region": name, "delta_pp": delta})
    regression = {"ok": not failures, "freeze_tolerance_pp": tolerance, "failed_regions": failures, "coupled_regions": sorted(coupled)}
    learning = {
        "mode": "reference_contour_learning",
        "priority": [{
            "region": "fingers",
            "error_score": float(target.get("error_score", 0.0)),
            "delta_pp": float(target.get("delta_pp", 0.0)),
            "visible_delta_pct": float(target.get("visible_delta_pct", 0.0)),
            "strategy": "KEEP_DIRECTION" if float(target.get("delta_pp", 0.0)) > 0 else "ROTATE_TECHNIQUE",
            "reason": "El contorno distal se deriva directamente de la referencia; conservar sólo si mejora fingers sin regresión congelada.",
        }],
        "next_region": "fingers",
        "ready_for_general_loop": False,
    }
    (root / "learning.json").write_text(json.dumps(learning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    process = {
        "mode": "finger_reference_fit_process",
        "region": "fingers",
        "morph": {
            "region": "fingers",
            "mesh_integrity": bool(morph["mesh_integrity"]),
            "safe_scope": bool(morph["outside_scope_exact"]),
            "detail": morph,
            "params": params,
        },
        "target_metrics": target,
        "learning": learning,
        "regression": regression,
        "technically_m4_ready": bool(morph["mesh_integrity"] and morph["outside_scope_exact"] and not failures),
        "promotion_allowed": False,
    }
    (root / "process.json").write_text(json.dumps(process, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "params.json").write_text(json.dumps({"region": "fingers", **params}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return process


def run_trial(
    baseline: str,
    reference: str,
    config: str,
    policy_path: str,
    module: str,
    slot: int,
    output_dir: str,
    tournament: int = 1,
) -> dict[str, Any]:
    policy = _read(policy_path)
    if module not in policy.get("modules", {}):
        raise RuntimeError(f"Módulo no registrado en policy: {module}")
    cfg = _read(config)
    if module not in (cfg.get("morph_regions") or {}):
        raise RuntimeError(f"Trial regional no soporta módulo no-regional: {module}")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    params = _variant(module, slot, tournament)
    process = _finger_process(baseline, reference, config, params, root) if module == "fingers" else run_process(baseline, reference, config, module, params, str(root))
    model = root / "model.glb"

    full = audit_full(
        baseline, str(model), reference, "hair,profile", config,
        None, str(root / "full_metrics.json"), str(root / "full_evidence")
    )
    labels: set[str] = {"learning"}
    _copy_region_evidence(root, module, labels)

    semantic_ready = True
    flags: list[str] = []
    extra: dict[str, Any] = {}

    if module in {"hands", "fingers"}:
        detail = hand_probe(str(model), reference, config, str(root / "hand_detail.json"), str(root / "hand_detail_evidence"))
        extra["hand_detail"] = detail
        left = root / "hand_detail_evidence" / "hand_detail_left.png"
        right = root / "hand_detail_evidence" / "hand_detail_right.png"
        if left.exists():
            shutil.copy2(left, root / "evidence" / "hand_left.png")
            labels.add("hand_left")
        if right.exists():
            shutil.copy2(right, root / "evidence" / "hand_right.png")
            labels.add("hand_right")
        labels.add("hand_detail")
        if module == "fingers":
            topology = topology_probe(str(model), str(root / "topology_report.json"))
            extra["topology"] = topology
            labels.update({"finger_detail", "topology_report"})
        definition_match = bool(detail.get("summary", {}).get("definition_match", False))
        semantic_ready = definition_match
        if not definition_match:
            flags.append("mitten_shape")

    if module == "ears":
        uv = uv_probe(str(model), str(root / "uv_probe.json"))
        extra["uv"] = uv
        labels.add("uv_probe")
        semantic_ready = not bool(uv.get("comparison", {}).get("body_ear_neighborhood_is_closer_to_hair"))
        if not semantic_ready:
            flags.append("phantom_ear")

    target = process.get("target_metrics") or {}
    view_deltas = full["visual"]["full"]["delta_pp"]
    required = set(policy["modules"][module].get("required_evidence") or [])
    evidence_complete = required <= labels
    result = {
        "module": module,
        "baseline_sha256": _sha256(baseline),
        "mesh_integrity": bool(process["morph"].get("mesh_integrity")),
        "scope_safe": bool(process["morph"].get("safe_scope")),
        "regression_ok": bool(process["regression"].get("ok")),
        "evidence_complete": evidence_complete,
        "semantic_ready": semantic_ready,
        "target_gain_pp": float(target.get("delta_pp", 0.0)),
        "global_gain_pp": float(full["visual"].get("weighted_gain_pp", 0.0)),
        "worst_view_delta_pp": float(min(float(view_deltas[v]) for v in ("front", "side", "back", "threeq"))),
        "evidence": sorted(labels),
        "flags": flags,
        "params": params,
    }
    (root / "module_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(policy, result, baseline_model=baseline)
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "module": module,
        "slot": slot,
        "params": params,
        "result": result,
        "gate": gate,
        "extra": extra,
        "promotion_executed": False,
    }
    (root / "trial.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="COPOX M5 regional trial; nunca promociona")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--tournament", type=int, default=1)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    result = run_trial(args.baseline, args.reference, args.config, args.policy, args.module, args.slot, args.output_dir, args.tournament)
    print(json.dumps({"module": args.module, "slot": args.slot, "promotion_allowed": result["gate"]["promotion_allowed"], "reasons": result["gate"]["reasons"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
