from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def lookup(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def compare(value: Any, op: str, threshold: str) -> bool:
    if op == "true":
        return value is True
    if op == "false":
        return value is False
    if op == "eq":
        return str(value) == threshold
    number = float(value)
    target = float(threshold)
    if op == "ge":
        return number >= target
    if op == "gt":
        return number > target
    if op == "le":
        return number <= target
    if op == "lt":
        return number < target
    raise ValueError(f"Operador no soportado: {op}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--agent", required=True)
    p.add_argument("--metrics", required=True)
    p.add_argument("--metric", required=True)
    p.add_argument("--op", required=True, choices=["ge", "gt", "le", "lt", "eq", "true", "false"])
    p.add_argument("--threshold", default="")
    p.add_argument("--result", required=True)
    p.add_argument("--critical", action="store_true")
    args = p.parse_args()

    result_path = Path(args.result)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        metrics = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
        value = lookup(metrics, args.metric)
        passed = compare(value, args.op, args.threshold)
        payload = {
            "id": args.agent,
            "status": "PASS" if passed else "FAIL",
            "critical": args.critical,
            "metric": args.metric,
            "observed": value,
            "operator": args.op,
            "threshold": args.threshold,
            "feedback": "cumple criterio" if passed else "ajustar el productor o estrategia para mover esta métrica hacia el criterio",
        }
        # bool es subtipo de int en Python: un gate True/False nunca debe influir en el ranking.
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            payload["score"] = float(value)
    except Exception as exc:
        payload = {
            "id": args.agent,
            "status": "FAIL",
            "critical": args.critical,
            "reason": f"metric_gate_error: {exc}",
        }
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
