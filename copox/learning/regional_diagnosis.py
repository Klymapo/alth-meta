from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _action(region: str, data: dict[str, Any]) -> dict[str, Any]:
    delta = float(data.get("delta_pp", 0.0))
    visible = float(data.get("visible_delta_pct", 0.0))
    error = float(data.get("error_score", 100.0))
    if visible < 0.10:
        strategy = "CREATE_HYPOTHESIS"
        reason = "El candidato casi no cambió visualmente la región. Probar una intervención distinta o mayor antes de concluir."
    elif delta > 0.0:
        strategy = "KEEP_DIRECTION"
        reason = "La región mejoró contra la referencia; repetir dirección con paso menor y vigilar regresiones."
    else:
        strategy = "ROTATE_TECHNIQUE"
        reason = "Hubo cambio visible sin mejora; revertir esa dirección y probar otra hipótesis."
    return {
        "region": region,
        "error_score": error,
        "delta_pp": delta,
        "visible_delta_pct": visible,
        "strategy": strategy,
        "reason": reason,
    }


def diagnose(metrics_path: str | Path, output: str | Path, focus: list[str] | None = None) -> dict[str, Any]:
    metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    regions = metrics.get("regions") or {}
    selected = regions if not focus else {k: v for k, v in regions.items() if k in set(focus)}
    actions = [_action(name, data) for name, data in selected.items()]
    actions.sort(key=lambda x: float(x["error_score"]), reverse=True)
    result = {
        "mode": "learning_first",
        "principle": "Priorizar comprender el mismatch contra la referencia antes de automatizar más deformaciones.",
        "priority": actions,
        "next_region": actions[0]["region"] if actions else None,
        "ready_for_general_loop": False,
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnóstico/learning regional")
    p.add_argument("--metrics", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--focus", default="")
    args = p.parse_args()
    focus = [x.strip() for x in args.focus.split(",") if x.strip()]
    result = diagnose(args.metrics, args.output, focus or None)
    print(json.dumps({"next_region": result["next_region"], "priority": result["priority"][:5]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
