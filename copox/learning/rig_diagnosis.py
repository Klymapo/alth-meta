from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def diagnose(candidate_report: str, structure_path: str, regional_path: str, output: str) -> dict:
    candidate = json.loads(Path(candidate_report).read_text(encoding="utf-8"))
    structure = json.loads(Path(structure_path).read_text(encoding="utf-8"))
    regional = json.loads(Path(regional_path).read_text(encoding="utf-8"))
    expected = set(candidate.get("bone_names") or [])
    exported = set(structure.get("rig", {}).get("joint_names") or [])
    skin_ok = bool(expected and expected <= exported and structure.get("counts", {}).get("skins", 0) > 0)
    coverage = float(candidate.get("weight_coverage", 0.0))
    weights_ok = bool(math.isfinite(coverage) and coverage == 1.0 and candidate.get("vertex_count", 0) > 0)
    pose = candidate.get("pose_test") or {}
    displacement = float(pose.get("max_displacement", 0.0))
    pose_ok = bool(pose.get("finite") and pose.get("moved_vertices", 0) > 0 and math.isfinite(displacement) and displacement > 0)
    deltas = [float(v["delta_pp"]) for d in regional.get("regions", {}).values() for v in d.get("views", [d])]
    rest_ok = bool(deltas and all(math.isfinite(x) and abs(x) < 0.10 for x in deltas))
    if not skin_ok:
        action = "FIX_SKIN_EXPORT"
    elif not weights_ok:
        action = "FIX_WEIGHT_COVERAGE"
    elif not pose_ok:
        action = "FIX_DEFORMATION_TEST"
    elif not rest_ok:
        action = "REPAIR_REST_POSE"
    else:
        action = "REVIEW_ADDITIONAL_JOINT_POSES"
    result = {
        "mode": "rig_learning",
        "ready_for_m4_process": bool(skin_ok and weights_ok and pose_ok and rest_ok),
        "action": action,
        "skin_export_ok": skin_ok,
        "weight_coverage_ok": weights_ok,
        "pose_test_ok": pose_ok,
        "rest_regression_ok": rest_ok,
        "missing_exported_joints": sorted(expected - exported),
        "max_rest_delta_pp": max((abs(x) for x in deltas), default=None),
        "promotion_allowed": False,
        "learning": "La prueba demuestra skin y una deformación corporal real. Revisar otras articulaciones y su semántica antes de aprobar el rig final.",
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnóstico de skin, deformación y regresión en rest pose")
    p.add_argument("--candidate-report", required=True)
    p.add_argument("--structure", required=True)
    p.add_argument("--regional", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = diagnose(args.candidate_report, args.structure, args.regional, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ready_for_m4_process"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
