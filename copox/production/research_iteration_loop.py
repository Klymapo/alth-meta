"""Bounded research-first sibling campaigns. No promotion or parent replacement."""
from __future__ import annotations

import json
import math
from pathlib import Path

from copox.production.research_gate import require_research


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def metric(row, name):
    value = row.get(name)
    return float(value) if value is not None else -math.inf


def run_generations(*, parent_sha, module, specs, output, mutate_and_audit, max_generations=3):
    if not 1 <= max_generations <= 3:
        raise ValueError("max_generations debe estar en 1..3")
    root = Path(output)
    records = []
    stop = "TECHNIQUE_EXHAUSTED"
    failures_in_a_row = 0
    for generation, spec in enumerate(specs[:max_generations], 1):
        generation_id = f"g{generation:02d}"
        directory = root / generation_id
        directory.mkdir(parents=True, exist_ok=True)
        try:
            research = require_research(spec["brief"], module, output=directory / "research_gate.json", technique=spec["technique"])
        except RuntimeError as exc:
            stop = "RESEARCH_REQUIRED"
            write_json(directory / "generation.json", {"generation_id": generation_id, "parent_sha": parent_sha,
                       "status": stop, "error": str(exc), "promotion_executed": False})
            break
        parameters = spec["parameters"]
        if len(parameters) != 3:
            raise ValueError("Cada generación debe declarar exactamente tres hermanos")
        # Research is always before mutation. Callbacks receive immutable parent SHA.
        rows = []
        for slot, params in enumerate(parameters, 1):
            row = mutate_and_audit(directory / f"c{slot:02d}", params, parent_sha)
            if row.get("parent_sha") != parent_sha:
                raise RuntimeError("PARENT_MISMATCH: candidato no es hermano")
            rows.append(row)
        ranked = sorted(rows, key=lambda row: (bool(row.get("audit_passed")),
                        bool(row.get("semantic_ready")), bool(row.get("mesh_integrity")),
                        metric(row, "target_gain_pp"), metric(row, "global_gain_pp")), reverse=True)
        eligible = [row for row in ranked if row.get("audit_passed") and row.get("visual_review", "PASS") == "PASS"]
        pending_visual = [row["candidate"] for row in ranked if row.get("audit_passed") and row.get("visual_review") == "PENDING"]
        winner = eligible[0]["candidate"] if eligible else None
        rejected = [row["candidate"] for row in rows if not row.get("audit_passed") or row.get("visual_review") == "REJECTED"]
        gains = [metric(row, "parent_target_delta_pp") for row in rows]
        improved = any(math.isfinite(gain) and gain > float(spec.get("significant_gain_pp", 0.10)) for gain in gains)
        mesh_failed = any(not row.get("mesh_integrity") for row in rows)
        regression = all(not row.get("regression_ok") for row in rows)
        failures_in_a_row = failures_in_a_row + 1 if regression else 0
        learning = {
            "preserve_parent": True,
            "significant_parent_improvement": improved,
            "all_candidates_regressed": regression,
            "mesh_integrity_failed": mesh_failed,
            "next_hypothesis": spec["next_hypothesis"],
            "visual_review_required": True,
        }
        record = {
            "generation_id": generation_id, "parent_sha": parent_sha,
            "research_id": research["research_id"], "module": module, "technique": spec["technique"],
            "parameters": parameters, "candidate_metrics": rows, "winner": winner,
            "best_diagnostic_candidate": ranked[0]["candidate"],
            "rejected_candidates": rejected, "pending_visual_candidates": pending_visual, "learning": learning,
            "next_hypothesis": spec["next_hypothesis"],
            "stages": ["RESEARCH", "DIAGNOSTIC", "SELECT_MODULE", "GENERATE_3_SIBLINGS", "AUDIT", "RANK", "LEARN"],
            "promotion_allowed": False, "promotion_executed": False,
        }
        if eligible:
            stop = "CANDIDATE_PASSED_GATES"
        elif pending_visual:
            stop = "VISUAL_REVIEW_REQUIRED"
        elif mesh_failed:
            stop = "MESH_INTEGRITY_FAILED"
        elif failures_in_a_row >= 2:
            stop = "REPEATED_REGRESSION"
        elif not improved:
            stop = "NO_SIGNIFICANT_IMPROVEMENT"
        elif generation >= max_generations:
            stop = "ITERATION_LIMIT"
        elif generation >= len(specs):
            stop = "TECHNIQUE_EXHAUSTED"
        else:
            stop = "NEXT_ITERATION"
        record["stop_reason"] = stop
        write_json(directory / "generation.json", record)
        records.append(record)
        if stop != "NEXT_ITERATION":
            break
    result = {"parent_sha": parent_sha, "generations": records, "stop_reason": stop,
              "max_generations": max_generations, "promotion_allowed": False, "promotion_executed": False}
    write_json(root / "loop.json", result)
    return result
