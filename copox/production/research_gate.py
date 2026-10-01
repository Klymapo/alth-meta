from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_research(brief: dict[str, Any], module: str, technique_round: int | None = None, max_age_days: int = 45) -> dict[str, Any]:
    reasons: list[str] = []
    if str(brief.get("module")) != module:
        reasons.append("module_mismatch")
    if brief.get("status") != "READY":
        reasons.append("status_not_ready")
    if brief.get("internet_checked") is not True:
        reasons.append("internet_not_checked")

    sources = list(brief.get("sources") or [])
    if len(sources) < 2:
        reasons.append("insufficient_sources")
    for i, src in enumerate(sources):
        if not str(src.get("url", "")).startswith(("https://", "http://")):
            reasons.append(f"source_{i+1}_missing_url")
        if not str(src.get("title", "")).strip():
            reasons.append(f"source_{i+1}_missing_title")

    techniques = list(brief.get("techniques") or [])
    applicable = [t for t in techniques if bool(t.get("applicable"))]
    if not applicable:
        reasons.append("no_applicable_technique")

    researched_at = str(brief.get("researched_at") or "")
    age_days = None
    try:
        researched = datetime.fromisoformat(researched_at.replace("Z", "+00:00")).date()
        age_days = (date.today() - researched).days
        if age_days < 0 or age_days > max_age_days:
            reasons.append("research_stale")
    except Exception:
        reasons.append("invalid_researched_at")

    if technique_round is not None:
        rounds = {int(x.get("round")): x for x in (brief.get("technique_rounds") or []) if "round" in x}
        row = rounds.get(int(technique_round))
        if not row:
            reasons.append(f"technique_round_{technique_round}_not_researched")
        elif not bool(row.get("applicable")):
            reasons.append(f"technique_round_{technique_round}_not_applicable")

    return {
        "module": module,
        "technique_round": technique_round,
        "research_ready": not reasons,
        "reasons": reasons,
        "researched_at": researched_at,
        "age_days": age_days,
        "source_count": len(sources),
        "applicable_techniques": [str(t.get("name")) for t in applicable],
        "chosen_direction": brief.get("chosen_direction"),
    }


def require_research(brief_path: str | Path, module: str, technique_round: int | None = None, output: str | Path | None = None) -> dict[str, Any]:
    path = Path(brief_path)
    if not path.exists():
        result = {
            "module": module,
            "technique_round": technique_round,
            "research_ready": False,
            "reasons": ["research_brief_missing"],
            "brief": str(path),
        }
    else:
        result = validate_research(_read(path), module, technique_round=technique_round)
        result["brief"] = str(path)
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not result["research_ready"]:
        raise RuntimeError("Research gate bloqueó mutación: " + ", ".join(result["reasons"]))
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Gate obligatorio de research antes de una mutación COPOX")
    p.add_argument("--brief", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--technique-round", type=int)
    p.add_argument("--output")
    a = p.parse_args()
    try:
        result = require_research(a.brief, a.module, a.technique_round, a.output)
    except RuntimeError as exc:
        print(str(exc))
        return 9
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
