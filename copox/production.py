from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _walk(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k), v
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)


def _tokens(candidate_dir: Path, audit_results: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for p in candidate_dir.rglob("*"):
        if p.is_file():
            rel = str(p.relative_to(candidate_dir)).lower()
            out.add(rel)
            out.add(p.stem.lower())
            out.update(x for x in p.stem.lower().replace("-", "_").split("_") if x)
    for result in audit_results:
        for key, value in _walk(result):
            out.add(key.lower())
            if isinstance(value, str):
                out.add(value.lower())
    return out


def _has_token(token: str, tokens: set[str]) -> bool:
    needle = token.lower().replace("-", "_")
    return any(needle in item.replace("-", "_") for item in tokens)


def _flagged(flag: str, audit_results: list[dict[str, Any]]) -> bool:
    needle = flag.lower()
    for result in audit_results:
        for key, value in _walk(result):
            if key.lower() == needle and bool(value):
                return True
            if isinstance(value, str) and value.lower() == needle:
                return True
    return False


def module_gate(
    *,
    policy: dict[str, Any],
    module_id: str,
    candidate_dir: str | Path,
    audit_results: list[dict[str, Any]],
    score: float | None = None,
) -> dict[str, Any]:
    modules = policy.get("modules") or {}
    if module_id not in modules:
        return {"status": "FAIL", "module": module_id, "reason": "module_not_registered"}

    rule = dict(modules[module_id])
    candidate = Path(candidate_dir)
    tokens = _tokens(candidate, audit_results)
    required = list(rule.get("required_evidence", []))
    missing = [x for x in required if not _has_token(x, tokens)]
    forbidden = list(rule.get("forbidden_flags", []))
    flags = [x for x in forbidden if _flagged(x, audit_results)]

    min_gain = float(rule.get("min_target_gain_pp", policy.get("min_target_gain_pp", 0.10)))
    gains: list[float] = []
    for result in audit_results:
        for key, value in _walk(result):
            if key.lower() in {"target_gain_pp", "weighted_gain_pp", "gain_pp"} and isinstance(value, (int, float)) and not isinstance(value, bool):
                gains.append(float(value))
    observed_gain = max(gains) if gains else None

    reasons: list[str] = []
    if missing:
        reasons.append("missing_evidence")
    if flags:
        reasons.append("forbidden_flag")
    # Sólo exigimos gain numérico cuando el auditor de la región lo produjo.
    if observed_gain is not None and observed_gain < min_gain:
        reasons.append("insufficient_gain")

    status = "PASS" if not reasons else "FAIL"
    return {
        "status": status,
        "module": module_id,
        "reason": ",".join(reasons) if reasons else "production_gate_pass",
        "required_evidence": required,
        "missing_evidence": missing,
        "forbidden_flags": flags,
        "min_target_gain_pp": min_gain,
        "observed_gain_pp": observed_gain,
        "selection_score": score,
    }


def load_policy(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
