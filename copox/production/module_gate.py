from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_RESULT_FIELDS = (
    "module",
    "mesh_integrity",
    "scope_safe",
    "regression_ok",
    "evidence_complete",
    "semantic_ready",
    "target_gain_pp",
    "global_gain_pp",
    "worst_view_delta_pp",
)


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def evaluate(policy: dict[str, Any], result: dict[str, Any], *, baseline_model: str | Path | None = None) -> dict[str, Any]:
    missing = [k for k in REQUIRED_RESULT_FIELDS if k not in result]
    checks: dict[str, bool] = {"contract_complete": not missing}
    reasons: list[str] = []
    if missing:
        reasons.append("missing_fields:" + ",".join(missing))

    module = str(result.get("module", ""))
    modules = policy.get("modules") or {}
    module_policy = modules.get(module)
    checks["module_registered"] = isinstance(module_policy, dict)
    if not checks["module_registered"]:
        reasons.append(f"unregistered_module:{module}")
        module_policy = {}

    expected_hash = str(policy.get("baseline_sha256") or "")
    if baseline_model is not None and expected_hash:
        checks["baseline_hash"] = _sha256(baseline_model) == expected_hash
        if not checks["baseline_hash"]:
            reasons.append("baseline_hash_mismatch")
    else:
        checks["baseline_hash"] = True

    boolean_fields = ("mesh_integrity", "scope_safe", "regression_ok", "evidence_complete", "semantic_ready")
    for field in boolean_fields:
        checks[field] = bool(result.get(field, False))
        if not checks[field]:
            reasons.append(field)

    min_target = float(module_policy.get("min_target_gain_pp", policy.get("min_target_gain_pp", 0.05)))
    min_global = float(module_policy.get("min_global_gain_pp", policy.get("min_global_gain_pp", 0.0)))
    max_view_drop = float(module_policy.get("max_single_view_drop_pp", policy.get("max_single_view_drop_pp", -0.10)))
    checks["target_gain"] = float(result.get("target_gain_pp", -1e9)) >= min_target
    checks["global_gain"] = float(result.get("global_gain_pp", -1e9)) >= min_global
    checks["single_view_regression"] = float(result.get("worst_view_delta_pp", -1e9)) >= max_view_drop
    if not checks["target_gain"]:
        reasons.append("target_gain_below_threshold")
    if not checks["global_gain"]:
        reasons.append("global_gain_below_threshold")
    if not checks["single_view_regression"]:
        reasons.append("single_view_regression")

    required_evidence = list(module_policy.get("required_evidence") or [])
    present_evidence = set(result.get("evidence") or [])
    missing_evidence = [x for x in required_evidence if x not in present_evidence]
    checks["module_evidence"] = not missing_evidence
    if missing_evidence:
        reasons.append("missing_evidence:" + ",".join(missing_evidence))

    forbidden = set(module_policy.get("forbidden_flags") or [])
    flags = set(result.get("flags") or [])
    bad_flags = sorted(forbidden & flags)
    checks["forbidden_flags"] = not bad_flags
    if bad_flags:
        reasons.append("forbidden_flags:" + ",".join(bad_flags))

    promotion_allowed = all(checks.values())
    return {
        "module": module,
        "promotion_allowed": promotion_allowed,
        "checks": checks,
        "thresholds": {
            "min_target_gain_pp": min_target,
            "min_global_gain_pp": min_global,
            "max_single_view_drop_pp": max_view_drop,
        },
        "missing_contract_fields": missing,
        "missing_evidence": missing_evidence,
        "reasons": reasons,
        "policy_version": policy.get("version", 1),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="COPOX M5 module promotion gate")
    p.add_argument("--policy", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--baseline-model")
    p.add_argument("--output", required=True)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    gate = evaluate(_read(args.policy), _read(args.result), baseline_model=args.baseline_model)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False))
    if args.check and not gate["promotion_allowed"]:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
