from __future__ import annotations

import argparse
import json

from copox.adapters.finger_gap_hands_plan import plan_gaps as hand_context_plan
from copox.production import finger_gap_trial as base


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    # Reutilizamos exactamente el mismo carve+contour+auditor+gate; sólo sustituimos
    # el detector de valles. Esto hace que la comparación A/B aisle una sola variable.
    original = base.plan_gaps
    try:
        base.plan_gaps = hand_context_plan
        return base.run_trial(baseline, reference, config, policy, slot, output_dir)
    finally:
        base.plan_gaps = original


def main() -> int:
    p = argparse.ArgumentParser(description="Trial fingers: detección hands, edición fingers")
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
        "cutters": trial["plan"]["cutter_count"],
        "promotion_allowed": trial["gate"]["promotion_allowed"],
        "definition_match": trial["result"]["semantic_ready"],
        "target_gain_pp": trial["result"]["target_gain_pp"],
        "global_gain_pp": trial["result"]["global_gain_pp"],
        "reasons": trial["gate"]["reasons"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
