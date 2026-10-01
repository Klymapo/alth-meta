from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.production import finger_valley_sculpt_trial as base


LEFT_FINGER_X1 = (0.085, 0.100, 0.115)
SCULPT_STRENGTH = 0.55


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(Path(config).read_text(encoding="utf-8"))
    boxes = cfg["morph_regions"]["fingers"]["boxes"]
    original_x1 = float(boxes[0][3])
    expanded_x1 = LEFT_FINGER_X1[slot - 1]
    hand_x1 = float(cfg["morph_regions"]["hands"]["boxes"][0][3])
    if not (original_x1 < expanded_x1 < hand_x1):
        raise RuntimeError(f"Scope experimental inválido: {expanded_x1} fuera de ({original_x1}, {hand_x1})")
    boxes[0][3] = expanded_x1
    experimental_config = root / "expanded_config.json"
    experimental_config.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    original_strengths = base.SCULPT_STRENGTHS
    try:
        base.SCULPT_STRENGTHS = (SCULPT_STRENGTH, SCULPT_STRENGTH, SCULPT_STRENGTH)
        trial = base.run_trial(baseline, reference, str(experimental_config), policy, slot, output_dir)
    finally:
        base.SCULPT_STRENGTHS = original_strengths

    trial["scope_expand_experiment"] = True
    trial["canonical_finger_x1"] = original_x1
    trial["experimental_finger_x1"] = expanded_x1
    trial["hand_x1_limit"] = hand_x1
    trial["promotion_executed"] = False
    trial["result"]["params"]["experimental_finger_x1"] = expanded_x1
    trial["learning"]["experimental_finger_x1"] = expanded_x1
    Path(output_dir, "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="Prueba learning-only de alcance proximal de fingers")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    first=(t['sculpt'].get('targets') or [{}])[0]
    d=t['hand_detail']['summary']; r=t['result']
    print(json.dumps({
        "slot":a.slot,
        "experimental_finger_x1":LEFT_FINGER_X1[a.slot-1],
        "first_valley_selected_vertices":first.get('selected_vertices',0),
        "model_valleys":d.get('model_valleys'),
        "semantic_ready":r['semantic_ready'],
        "target_gain_pp":r['target_gain_pp'],
        "global_gain_pp":r['global_gain_pp'],
        "worst_view_delta_pp":r['worst_view_delta_pp'],
        "scope_safe":r['scope_safe'],
        "regression_ok":r['regression_ok'],
        "promotion_allowed":t['gate']['promotion_allowed'],
        "reasons":t['gate']['reasons'],
    },ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
