from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.adapters.finger_gap_full_depth_plan import plan_gaps as full_depth_plan
from copox.production import finger_gap_trial as base
from copox.production.module_gate import evaluate


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    original = base.plan_gaps
    try:
        base.plan_gaps = full_depth_plan
        trial = base.run_trial(baseline, reference, config, policy, slot, output_dir)
    finally:
        base.plan_gaps = original

    # Esta fase responde una pregunta visual/geométrica. Hasta crear un gate de scope
    # que pruebe formalmente el barrido completo en Y, no puede promocionarse aunque
    # los demás checks pasaran.
    root = Path(output_dir)
    trial["result"]["scope_safe"] = False
    trial["result"].setdefault("flags", []).append("full_depth_scope_unvalidated")
    trial["result"]["flags"] = sorted(set(trial["result"]["flags"]))
    (root / "module_result.json").write_text(json.dumps(trial["result"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = evaluate(base._read(policy), trial["result"], baseline_model=baseline)
    trial["gate"] = gate
    trial["promotion_executed"] = False
    (root / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="Trial experimental fingers full-depth; nunca promociona")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    t = run_trial(args.baseline, args.reference, args.config, args.policy, args.slot, args.output_dir)
    print(json.dumps({
        "slot": args.slot,
        "definition_match": t["result"]["semantic_ready"],
        "target_gain_pp": t["result"]["target_gain_pp"],
        "global_gain_pp": t["result"]["global_gain_pp"],
        "scope_safe": t["result"]["scope_safe"],
        "promotion_allowed": t["gate"]["promotion_allowed"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
