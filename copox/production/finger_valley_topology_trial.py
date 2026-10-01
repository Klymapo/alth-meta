from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.production import finger_valley_sculpt_trial as base
from copox.production.regional_trial import _refine_finger_topology as real_refine


TOPOLOGY_CUTS = (2, 3, 4)
SCULPT_STRENGTH = 0.55


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    cuts = TOPOLOGY_CUTS[slot - 1]
    original_refine = base._refine_finger_topology
    original_strengths = base.SCULPT_STRENGTHS

    def refined(baseline_model, config_path, root, ignored_cuts):
        return real_refine(baseline_model, config_path, root, cuts)

    try:
        base._refine_finger_topology = refined
        base.SCULPT_STRENGTHS = (SCULPT_STRENGTH, SCULPT_STRENGTH, SCULPT_STRENGTH)
        trial = base.run_trial(baseline, reference, config, policy, slot, output_dir)
    finally:
        base._refine_finger_topology = original_refine
        base.SCULPT_STRENGTHS = original_strengths

    trial["valley_topology_experiment"] = True
    trial["topology_cuts"] = cuts
    trial["promotion_executed"] = False
    trial["result"]["params"]["topology_cuts"] = cuts
    trial["learning"]["topology_cuts"] = cuts
    Path(output_dir, "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="Barrida learning-only de densidad topológica para valley sculpt")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    d = t["hand_detail"]["summary"]
    first=(t['sculpt'].get('targets') or [{}])[0]
    print(json.dumps({
        "slot": a.slot,
        "topology_cuts": TOPOLOGY_CUTS[a.slot - 1],
        "first_valley_selected_vertices": first.get('selected_vertices',0),
        "semantic_ready": t["result"]["semantic_ready"],
        "reference_valleys": d.get("reference_valleys"),
        "model_valleys": d.get("model_valleys"),
        "target_gain_pp": t["result"]["target_gain_pp"],
        "global_gain_pp": t["result"]["global_gain_pp"],
        "worst_view_delta_pp": t["result"]["worst_view_delta_pp"],
        "promotion_allowed": t["gate"]["promotion_allowed"],
        "reasons": t["gate"]["reasons"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
