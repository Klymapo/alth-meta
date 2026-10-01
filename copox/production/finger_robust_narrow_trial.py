from __future__ import annotations

import argparse
import json

from copox.production import finger_robust_extrude_trial as base


NARROW_VARIANTS = (
    {"segments": 2, "depth_scale": 0.45, "tip_scale": 0.88, "length_scale": 0.90},
    {"segments": 2, "depth_scale": 0.52, "tip_scale": 0.88, "length_scale": 0.90},
    {"segments": 2, "depth_scale": 0.60, "tip_scale": 0.88, "length_scale": 0.90},
)


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    original = base.VARIANTS
    try:
        base.VARIANTS = NARROW_VARIANTS
        trial = base.run_trial(baseline, reference, config, policy, slot, output_dir)
    finally:
        base.VARIANTS = original
    trial["narrow_depth_experiment"] = True
    trial["promotion_executed"] = False
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="Barrida learning-only de profundidad para robust extrusion")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    d = t["hand_detail"]["summary"]
    r = t["result"]
    print(json.dumps({
        "slot": a.slot,
        "depth_scale": NARROW_VARIANTS[a.slot - 1]["depth_scale"],
        "reference_valleys": d.get("reference_valleys"),
        "model_valleys": d.get("model_valleys"),
        "semantic_ready": r["semantic_ready"],
        "target_gain_pp": r["target_gain_pp"],
        "global_gain_pp": r["global_gain_pp"],
        "worst_view_delta_pp": r["worst_view_delta_pp"],
        "regression_ok": r["regression_ok"],
        "promotion_executed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
