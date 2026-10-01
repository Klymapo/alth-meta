from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

GLOBAL_MODULES = {"whole_body_silhouette", "global_proportions", "orientation"}


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def choose(policy: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
    registered = set((policy.get("modules") or {}).keys())
    router = policy.get("router") or {}
    priority = list(router.get("priority_order") or [])
    priority_index = {name: i for i, name in enumerate(priority)}
    rows = diagnostics.get("modules") or {}
    candidates: list[dict[str, Any]] = []
    for module, row in rows.items():
        if module not in registered:
            continue
        if not bool(row.get("actionable", True)):
            continue
        error = max(0.0, float(row.get("error", 0.0)))
        confidence = min(1.0, max(0.0, float(row.get("confidence", 1.0))))
        learning_need = min(1.0, max(0.0, float(row.get("learning_need", 0.0))))
        score = error * confidence + learning_need * 0.25
        candidates.append({
            "module": module,
            "score": score,
            "error": error,
            "confidence": confidence,
            "learning_need": learning_need,
            "priority": priority_index.get(module, 999),
            "reason": row.get("reason"),
        })

    regional = [x for x in candidates if x["module"] not in GLOBAL_MODULES]
    if router.get("global_modules_only_when_regional_explanation_insufficient", True) and regional:
        pool = regional
        global_suppressed = True
    else:
        pool = candidates
        global_suppressed = False

    if not pool:
        return {"selected": None, "status": "NO_ACTIONABLE_MODULE", "ranking": [], "global_suppressed": global_suppressed}

    ranking = sorted(pool, key=lambda x: (-x["score"], x["priority"], x["module"]))
    selected = ranking[0]
    return {
        "selected": selected["module"],
        "status": "SELECTED",
        "selected_score": selected["score"],
        "selected_reason": selected.get("reason"),
        "ranking": ranking,
        "global_suppressed": global_suppressed,
        "one_primary_module_per_campaign": True,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="COPOX router de módulos M5")
    p.add_argument("--policy", required=True)
    p.add_argument("--diagnostics", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = choose(_read(args.policy), _read(args.diagnostics))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["selected"] else 6


if __name__ == "__main__":
    raise SystemExit(main())
