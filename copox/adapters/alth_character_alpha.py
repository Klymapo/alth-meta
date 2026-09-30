from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from copox.adapters.alth_character import cmd_capture as legacy_capture
from copox.adapters.alth_character import cmd_learn as legacy_learn
from copox.adapters.alth_character import cmd_mutate as legacy_mutate
from copox.adapters.alth_character import ensure_runtime, read_json, write_json
from copox.adapters.alth_glb_character import apply_structured_hair
from copox.state_bundle import load_bundle, save_bundle


def cmd_prepare(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    baseline_seed = (repo / args.baseline_params).resolve()
    model_seed = (repo / args.baseline_model).resolve()
    run_dir = Path(args.run_dir).resolve()
    baseline_dir = run_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    runtime_params = baseline_dir / "params.json"
    runtime_model = baseline_dir / "model.glb"

    if args.state_branch:
        source = load_bundle(repo, args.state_branch, runtime_params, runtime_model, baseline_seed, model_seed)
    else:
        shutil.copy2(baseline_seed, runtime_params)
        shutil.copy2(model_seed, runtime_model)
        source = {
            "source": "seed_bundle",
            "fallback_baseline": str(baseline_seed),
            "fallback_model": str(model_seed),
        }
    write_json(run_dir / "baseline_source.json", source)
    write_json(run_dir / "search_state.json", {
        "tournament": 0,
        "failure_history": [],
        "parameter_cursor": 0,
        "baseline_source": source,
    })
    return 0


def cmd_mutate(args: argparse.Namespace) -> int:
    return legacy_mutate(args)


def _render(repo: Path, model: Path, candidate: Path):
    alth_python = ensure_runtime(repo)
    render_dir = candidate / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    script = repo / "copox" / "adapters" / "alth_glb_render.py"
    subprocess.run([
        alth_python, str(script), "--input", str(model), "--output-dir", str(render_dir),
        "--title", f"COPOX · {candidate.name} · Theo Alpha",
    ], cwd=repo, check=True)
    shutil.copy2(render_dir / "hoja.png", candidate / "hoja.png")
    return read_json(render_dir / "reporte.json")


def cmd_execute(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    candidate = Path(args.candidate_dir).resolve()
    baseline_model = Path(args.baseline_model).resolve()
    config = (repo / args.edit_config).resolve() if not Path(args.edit_config).is_absolute() else Path(args.edit_config)
    model = candidate / "model.glb"
    technical_path = candidate / "technical.json"
    technical = apply_structured_hair(baseline_model, candidate / "params.json", config, model, technical_path)
    render = _render(repo, model, candidate)
    report = dict(render)
    report["verificacion"] = technical["verificacion"]
    report["technical"] = technical["technical"]
    report["structure"] = technical["structure"]
    report["params"] = technical["params"]
    write_json(candidate / "reporte.json", report)
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    rc = legacy_capture(args)
    candidate = Path(args.candidate_dir).resolve()
    metrics_path = candidate / "metrics.json"
    report = read_json(candidate / "reporte.json")
    metrics = read_json(metrics_path)
    metrics["structure"] = report.get("structure", {})
    write_json(metrics_path, metrics)
    return rc


def cmd_learn(args: argparse.Namespace) -> int:
    return legacy_learn(args)


def cmd_promote(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    candidate = Path(args.candidate_dir).resolve()
    neutral_baseline = (repo / args.baseline_params).resolve()
    state_commit = None
    candidate_params = read_json(candidate / "params.json")
    if args.state_branch:
        state_commit = save_bundle(
            repo,
            args.state_branch,
            neutral_baseline,
            candidate / "model.glb",
            {
                "cassette_id": args.cassette_id or args.target,
                "target": args.target,
                "candidate": candidate.name,
                "candidate_params": candidate_params,
                "seed_model": args.baseline_model,
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "github_run_number": os.environ.get("GITHUB_RUN_NUMBER"),
            },
        )
    write_json(candidate / "promotion.json", {
        "candidate": candidate.name,
        "state_branch": args.state_branch,
        "state_commit": state_commit,
        "state_format": "baseline+model-v1",
        "seed_model": args.baseline_model,
        "persist_main": False,
    })
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Adaptador COPOX para Theo Alpha basado en GLB aprobado")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("prepare")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--baseline-params", required=True)
    a.add_argument("--baseline-model", required=True)
    a.add_argument("--state-branch")
    a.add_argument("--run-dir", required=True)
    a.set_defaults(func=cmd_prepare)

    a = sub.add_parser("mutate")
    a.add_argument("--baseline-params", required=True)
    a.add_argument("--search-space", required=True)
    a.add_argument("--run-dir", required=True)
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--candidate-id", required=True)
    a.set_defaults(func=cmd_mutate)

    a = sub.add_parser("execute")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--baseline-model", required=True)
    a.add_argument("--edit-config", required=True)
    a.set_defaults(func=cmd_execute)

    a = sub.add_parser("capture")
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--evidence-dir", required=True)
    a.add_argument("--run-dir", required=True)
    a.add_argument("--reference", required=True)
    a.add_argument("--audit-config", required=True)
    a.add_argument("--focus", default="hair,profile")
    a.set_defaults(func=cmd_capture)

    a = sub.add_parser("learn")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--tournament", required=True)
    a.set_defaults(func=cmd_learn)

    a = sub.add_parser("promote")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--baseline-params", required=True)
    a.add_argument("--baseline-model", required=True)
    a.add_argument("--state-branch")
    a.add_argument("--cassette-id")
    a.add_argument("--target", required=True)
    a.set_defaults(func=cmd_promote)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
