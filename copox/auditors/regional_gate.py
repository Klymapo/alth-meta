from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    p = argparse.ArgumentParser(description="Gate genérico para métricas regionales")
    p.add_argument("--metrics", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--min-delta-pp", type=float, default=0.0)
    p.add_argument("--min-visible-delta-pct", type=float, default=0.0)
    p.add_argument("--max-error-score", type=float)
    p.add_argument("--critical", action="store_true")
    args = p.parse_args()

    data: dict[str, Any] = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
    region = (data.get("regions") or {}).get(args.region)
    reasons: list[str] = []
    if not isinstance(region, dict):
        reasons.append("region_missing")
        region = {}
    delta = float(region.get("delta_pp", 0.0))
    visible = float(region.get("visible_delta_pct", 0.0))
    error_score = float(region.get("error_score", 100.0))
    if delta < args.min_delta_pp:
        reasons.append(f"delta_pp<{args.min_delta_pp}")
    if visible < args.min_visible_delta_pct:
        reasons.append(f"visible_delta_pct<{args.min_visible_delta_pct}")
    if args.max_error_score is not None and error_score > args.max_error_score:
        reasons.append(f"error_score>{args.max_error_score}")

    result = {
        "id": f"RegionalGate:{args.region}",
        "status": "PASS" if not reasons else "FAIL",
        "critical": bool(args.critical),
        "region": args.region,
        "score": max(0.0, 100.0 - error_score),
        "metrics": {
            "delta_pp": delta,
            "visible_delta_pct": visible,
            "error_score": error_score,
        },
        "reasons": reasons,
    }
    out = Path(args.result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
