from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from copox.adapters import alth_model_m5 as base
from copox.production.research_gate import require_research
from copox.state_bundle import save_bundle


def _attempts(run_dir: Path) -> tuple[dict[str, int], set[str]]:
    state = base._read(run_dir / "learning_state.json")
    source_learning = dict(state.get("source_learning") or {})
    attempts = {str(k): int(v) for k, v in (source_learning.get("attempt_counts") or {}).items()}
    cooldown = set(str(x) for x in source_learning.get("cooldown_modules", []))
    for previous in base._learning_files(run_dir):
        for key, value in (previous.get("attempt_counts") or {}).items():
            attempts[str(key)] = max(attempts.get(str(key), 0), int(value))
        for module in previous.get("cooldown_modules") or []:
            cooldown.add(str(module))
    return attempts, cooldown


def _policy(run_dir: Path) -> dict[str, Any]:
    manifest = base._read(run_dir / "manifest.json")
    rel = str((manifest.get("variables") or {}).get("production_policy") or "copox/production/theo_m5_policy.json")
    path = Path(rel)
    if not path.is_absolute():
        path = Path.cwd() / path
    return base._read(path)


def _technique_budget(policy: dict[str, Any], module: str) -> int:
    row = (policy.get("modules") or {}).get(module) or {}
    return max(1, int(row.get("technique_rounds", 1)))


def cmd_mutate(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    candidate = Path(args.candidate_dir).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    route = base._read(run_dir / "route.json")
    module = str(route["selected"])
    attempts, _ = _attempts(run_dir)
    technique_round = int(attempts.get(module, 0)) + 1
    budget = _technique_budget(_policy(run_dir), module)
    technique_round = min(technique_round, budget)

    # Research preflight obligatorio. El loop no puede ni siquiera preparar una
    # mutación si la técnica de esta ronda no fue investigada previamente.
    repo = Path.cwd().resolve()
    brief = repo / "copox" / "research" / f"{module}.json"
    research = require_research(
        brief,
        module,
        technique_round=technique_round,
        output=candidate / "research_gate.json",
    )

    spec = {
        "module": module,
        "candidate_id": args.candidate_id,
        "slot": base._slot(args.candidate_id),
        "tournament": 1,
        "engine_tournament": base._tournament(args.candidate_id),
        "technique_round": technique_round,
        "technique_budget": budget,
        "research_ready": True,
        "research_brief": str(brief.relative_to(repo)),
        "research_direction": research.get("chosen_direction"),
    }
    base._write(candidate / "module_spec.json", spec)
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    route = base._read(run_dir / "route.json")
    failed_module = str(route.get("selected"))
    policy_path = (repo / args.policy).resolve()
    policy = base._read(policy_path)
    budget = _technique_budget(policy, failed_module)

    attempts, cooldown = _attempts(run_dir)
    attempted = int(attempts.get(failed_module, 0)) + 1
    attempts[failed_module] = attempted

    if attempted < budget:
        next_module = failed_module
        reason = (
            f"Ningún hermano obtuvo gate M5; mantener módulo y avanzar técnica "
            f"{attempted + 1}/{budget} antes de cooldown."
        )
    else:
        cooldown.add(failed_module)
        new_route = base._reroute(run_dir, policy_path, failed_module)
        next_module = new_route.get("selected")
        reason = (
            f"Módulo agotó {budget} técnica(s) sin gate M5; entrar en cooldown "
            "y rotar sin promover baseline."
        )

    learning = {
        "failed_module": failed_module,
        "next_module": next_module,
        "tournament": int(args.tournament),
        "cooldown_modules": sorted(cooldown),
        "attempt_counts": attempts,
        "technique_budget": budget,
        "attempted_techniques": attempted,
        "next_technique_round": attempted + 1 if attempted < budget else None,
        "reason": reason,
    }
    base._write(run_dir / f"learning_t{int(args.tournament):02d}.json", learning)

    if args.state_branch:
        save_bundle(
            repo, args.state_branch,
            run_dir / "baseline" / "params.json",
            run_dir / "baseline" / "model.glb",
            {
                "cassette_id": args.cassette_id,
                "target": args.target,
                "learning": learning,
                "promotion": False,
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            },
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Adapter M5 con ciclos de técnica antes de cooldown")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("prepare")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--baseline-params", required=True)
    a.add_argument("--baseline-model", required=True)
    a.add_argument("--state-branch")
    a.add_argument("--reference", required=True)
    a.add_argument("--config", required=True)
    a.add_argument("--policy", required=True)
    a.add_argument("--run-dir", required=True)
    a.set_defaults(func=base.cmd_prepare)

    a = sub.add_parser("mutate")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--candidate-id", required=True)
    a.set_defaults(func=cmd_mutate)

    a = sub.add_parser("capture")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--evidence-dir", required=True)
    a.add_argument("--reference", required=True)
    a.add_argument("--config", required=True)
    a.add_argument("--policy", required=True)
    a.set_defaults(func=base.cmd_capture)

    a = sub.add_parser("learn")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--tournament", required=True)
    a.add_argument("--state-branch")
    a.add_argument("--cassette-id", required=True)
    a.add_argument("--target", required=True)
    a.add_argument("--config", required=True)
    a.add_argument("--policy", required=True)
    a.set_defaults(func=cmd_learn)

    a = sub.add_parser("promote")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--baseline-params", required=True)
    a.add_argument("--state-branch")
    a.add_argument("--cassette-id", required=True)
    a.add_argument("--target", required=True)
    a.set_defaults(func=base.cmd_promote)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
