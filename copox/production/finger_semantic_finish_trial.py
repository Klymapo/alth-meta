from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.production import regional_trial as base


STRENGTHS = (1.15, 1.20, 1.25)


def _semantic_variant(module: str, slot: int, tournament: int = 4):
    if module != "fingers":
        return base._variant(module, slot, tournament)
    if slot not in (1, 2, 3):
        raise ValueError("slot debe ser 1..3")
    return {
        "strength": float(STRENGTHS[slot - 1]),
        "topology_refine": True,
        "refine_cuts": 1,
        "semantic_finish": True,
    }


def run_trial(baseline: str, reference: str, config: str, policy: str, slot: int, output_dir: str):
    """Torneo experimental estrecho para cerrar la última separación visible.

    Reusa exactamente el proceso/gate M5 normal. Sólo sustituye la familia de
    parámetros por tres strengths cercanos al mejor candidato g2-c03 (1.10),
    manteniendo una sola subdivisión porque dos cortes no mejoraron la semántica.
    Nunca promociona por sí mismo.
    """
    original = base._variant
    try:
        base._variant = _semantic_variant
        trial = base.run_trial(
            baseline, reference, config, policy,
            module="fingers", slot=slot, output_dir=output_dir, tournament=4,
        )
    finally:
        base._variant = original
    trial["semantic_finish_experiment"] = True
    trial["promotion_executed"] = False
    root = Path(output_dir)
    (root / "trial.json").write_text(json.dumps(trial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trial


def main() -> int:
    p = argparse.ArgumentParser(description="COPOX finger semantic finish; nunca promociona")
    p.add_argument("--baseline", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    t = run_trial(a.baseline, a.reference, a.config, a.policy, a.slot, a.output_dir)
    detail = t["extra"]["hand_detail"]["summary"]
    print(json.dumps({
        "slot": a.slot,
        "strength": STRENGTHS[a.slot - 1],
        "semantic_ready": t["result"]["semantic_ready"],
        "vertical_run_gap": detail.get("mean_vertical_run_gap"),
        "valley_gap": detail.get("mean_valley_count_gap"),
        "target_gain_pp": t["result"]["target_gain_pp"],
        "global_gain_pp": t["result"]["global_gain_pp"],
        "worst_view_delta_pp": t["result"]["worst_view_delta_pp"],
        "promotion_allowed": t["gate"]["promotion_allowed"],
        "reasons": t["gate"]["reasons"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
