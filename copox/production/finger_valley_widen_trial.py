from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.adapters.finger_valley_sculpt import sculpt_valleys as real_sculpt
from copox.production import finger_valley_sculpt_trial as base


LENGTH_SCALES = (1.10, 1.20, 1.25)
SCULPT_STRENGTH = 0.55


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    length_scale = LENGTH_SCALES[slot - 1]
    original_sculpt = base.sculpt_valleys
    original_strengths = base.SCULPT_STRENGTHS

    def widened_sculpt(baseline_model, input_model, reference_sheet, config_path, output, report_path, strength=SCULPT_STRENGTH, length_scale=1.0):
        return real_sculpt(
            baseline_model, input_model, reference_sheet, config_path, output, report_path,
            strength=SCULPT_STRENGTH, length_scale=LENGTH_SCALES[slot - 1],
        )

    try:
        base.sculpt_valleys = widened_sculpt
        base.SCULPT_STRENGTHS = (SCULPT_STRENGTH, SCULPT_STRENGTH, SCULPT_STRENGTH)
        trial = base.run_trial(baseline, reference, config, policy, slot, output_dir)
    finally:
        base.sculpt_valleys = original_sculpt
        base.SCULPT_STRENGTHS = original_strengths

    trial["valley_widen_experiment"] = True
    trial["length_scale"] = length_scale
    trial["promotion_executed"] = False
    trial["result"]["params"]["length_scale"] = length_scale
    trial["learning"]["length_scale"] = length_scale
    Path(output_dir, "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="Barrida learning-only de altura vertical para valley sculpt")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    d = t["hand_detail"]["summary"]
    print(json.dumps({
        "slot": a.slot,
        "length_scale": LENGTH_SCALES[a.slot - 1],
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
