from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from copox.state import load_state, save_state


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_dotted(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        cur = cur[part]
    return cur


def set_dotted(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def ensure_runtime(repo_root: Path) -> str:
    alth_python = shutil.which("alth-python")
    if not alth_python:
        subprocess.run(["bash", "tools/ensure_blender.sh", "--strict"], cwd=repo_root, check=True)
        alth_python = shutil.which("alth-python")
    if not alth_python:
        raise RuntimeError("alth-python no quedó disponible")
    required = ["numpy", "PIL", "scipy", "trimesh"]
    missing: list[str] = []
    for module in required:
        try:
            __import__(module)
        except ImportError:
            missing.append("pillow" if module == "PIL" else module)
    if missing:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], cwd=repo_root, check=True)
    return alth_python


def build(repo_root: Path, asset_dir: Path, params: Path, export_glb: Path, mode: str = "iteracion") -> tuple[Path, Path]:
    alth_python = ensure_runtime(repo_root)
    env = os.environ.copy()
    env["COPOX_PARAMS"] = str(params.resolve())
    env["COPOX_EXPORT_GLTF"] = str(export_glb.resolve())
    cmd = [alth_python, str((asset_dir / "build.py").resolve())]
    if mode == "final":
        cmd.append("final")
    subprocess.run(cmd, cwd=repo_root, env=env, check=True)
    render_dir = repo_root / "renders" / asset_dir.name / mode
    sheet = render_dir / "hoja.png"
    report = render_dir / "reporte.json"
    if not sheet.exists() or not report.exists() or not export_glb.exists():
        raise RuntimeError(f"Build incompleto: hoja={sheet.exists()} reporte={report.exists()} glb={export_glb.exists()}")
    return sheet, report


def cmd_prepare(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    asset = (repo / args.asset_dir).resolve()
    baseline_seed = (repo / args.baseline_params).resolve()
    run_dir = Path(args.run_dir).resolve()
    baseline_dir = run_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    runtime_params = baseline_dir / "params.json"

    if args.state_branch:
        source = load_state(repo, args.state_branch, runtime_params, baseline_seed)
    else:
        shutil.copy2(baseline_seed, runtime_params)
        source = {"source": "seed", "fallback": str(baseline_seed)}
    write_json(run_dir / "baseline_source.json", source)

    sheet, report = build(repo, asset, runtime_params, baseline_dir / "model.glb")
    shutil.copy2(sheet, baseline_dir / "hoja.png")
    shutil.copy2(report, baseline_dir / "reporte.json")
    write_json(run_dir / "search_state.json", {
        "tournament": 0,
        "failure_history": [],
        "parameter_cursor": 0,
        "baseline_source": source,
    })
    return 0


def choose_parameters(space: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    params = list(space.get("parameters", []))
    preferred = state.get("preferred_tags", [])
    if preferred:
        tagged = [p for p in params if set(p.get("tags", [])) & set(preferred)]
        if tagged:
            params = tagged + [p for p in params if p not in tagged]
    return params


def cmd_mutate(args: argparse.Namespace) -> int:
    baseline = read_json(args.baseline_params)
    space = read_json(args.search_space)
    state_path = Path(args.run_dir) / "search_state.json"
    state = read_json(state_path) if state_path.exists() else {"parameter_cursor": 0}
    params = choose_parameters(space, state)
    if not params:
        raise RuntimeError("El espacio paramétrico no contiene parameters")

    try:
        tournament = int(args.candidate_id.split("-")[0][1:])
        slot = int(args.candidate_id.split("-")[1][1:])
    except Exception as exc:
        raise RuntimeError(f"candidate_id inesperado: {args.candidate_id}") from exc

    out = json.loads(json.dumps(baseline))
    cursor = int(state.get("parameter_cursor", 0)) % len(params)
    offsets = (-1.0, 1.0, 2.0)
    slot_index = max(0, slot - 1)
    chosen_index = (cursor + (1 if slot_index == 2 and len(params) > 1 else 0)) % len(params)
    spec = params[chosen_index]
    path = str(spec["path"])
    current = float(get_dotted(out, path))
    multiplier = float(state.get("step_multiplier", 1.0))
    offset = offsets[slot_index % len(offsets)]
    step = float(spec["step"]) * multiplier
    value = clamp(current + step * offset, float(spec["min"]), float(spec["max"]))
    if spec.get("type") == "int":
        value = int(round(value))
    set_dotted(out, path, value)
    out.setdefault("_copox", {})
    out["_copox"].update({
        "candidate_id": args.candidate_id,
        "tournament": tournament,
        "mutated_parameter": path,
        "baseline_value": current,
        "candidate_value": value,
        "step": step,
    })
    write_json(Path(args.candidate_dir) / "params.json", out)
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    asset = (repo / args.asset_dir).resolve()
    candidate = Path(args.candidate_dir).resolve()
    sheet, report = build(repo, asset, candidate / "params.json", candidate / "model.glb")
    shutil.copy2(sheet, candidate / "hoja.png")
    shutil.copy2(report, candidate / "reporte.json")
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    candidate = Path(args.candidate_dir).resolve()
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    if (candidate / "hoja.png").exists():
        shutil.copy2(candidate / "hoja.png", evidence / "hoja.png")
    from copox.adapters.alth_character_audit import audit
    audit(
        str(Path(args.run_dir).resolve() / "baseline" / "model.glb"),
        str(candidate / "model.glb"),
        args.reference,
        args.focus,
        args.audit_config,
        str(candidate / "reporte.json"),
        str(candidate / "metrics.json"),
        str(evidence),
    )
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    state_path = run_dir / "search_state.json"
    state = read_json(state_path) if state_path.exists() else {"failure_history": [], "parameter_cursor": 0}
    metrics_files = sorted((run_dir / "candidates").glob(f"t{int(args.tournament):02d}-*/metrics.json"))
    issues: list[str] = []
    budgets: list[dict[str, Any]] = []
    for path in metrics_files:
        data = read_json(path)
        issues.extend(data.get("learning", {}).get("unresolved", []))
        budgets.extend(data.get("error_budget", []))
    top_issue = None
    if issues:
        top_issue = max(set(issues), key=issues.count)
    elif budgets:
        top_issue = max(budgets, key=lambda x: float(x.get("error_score", 0.0))).get("area")
    history = list(state.get("failure_history", []))
    if top_issue:
        history.append(str(top_issue))
    repeated = len(history) >= 2 and history[-1] == history[-2]
    state.update({
        "tournament": int(args.tournament),
        "failure_history": history[-6:],
        "preferred_tags": [top_issue] if top_issue else [],
        "parameter_cursor": int(state.get("parameter_cursor", 0)) + (1 if repeated else 0),
        "step_multiplier": 1.35 if repeated else 1.0,
        "action": "ROTATE_TECHNIQUE" if repeated else "REFINE",
        "escalate_after_campaign": bool(repeated and int(args.tournament) >= 2),
    })
    write_json(state_path, state)
    write_json(run_dir / f"learning_t{int(args.tournament):02d}.json", state)
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    candidate = Path(args.candidate_dir).resolve()
    seed_path = (repo / args.baseline_params).resolve()
    state_commit = None

    if args.state_branch:
        state_commit = save_state(
            repo,
            args.state_branch,
            candidate / "params.json",
            {
                "cassette_id": args.cassette_id or args.target,
                "target": args.target,
                "candidate": candidate.name,
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "github_run_number": os.environ.get("GITHUB_RUN_NUMBER"),
            },
        )

    promotion = {
        "candidate": candidate.name,
        "seed_params": str(seed_path.relative_to(repo)),
        "state_branch": args.state_branch,
        "state_commit": state_commit,
        "persist_main": bool(args.persist),
        "finalized": bool(args.finalize),
    }
    write_json(candidate / "promotion.json", promotion)

    if args.finalize:
        asset = (repo / args.asset_dir).resolve()
        build(repo, asset, candidate / "params.json", asset / f"{asset.name}.glb", mode="final")

    # Compatibilidad/override manual: sólo cuando se pide explícitamente se toca la rama actual.
    if args.persist:
        shutil.copy2(candidate / "params.json", seed_path)
        subprocess.run(["git", "config", "user.name", "copox-loop-engine"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "copox-loop-engine@users.noreply.github.com"], cwd=repo, check=True)
        paths = [str(seed_path.relative_to(repo))]
        if args.finalize:
            paths.append(args.asset_dir)
        subprocess.run(["git", "add", "--", *paths], cwd=repo, check=True)
        status = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
        if status.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"copox: publica {args.target} desde {candidate.name}"], cwd=repo, check=True)
            ref = os.environ.get("GITHUB_REF_NAME")
            if ref:
                subprocess.run(["git", "push", "origin", f"HEAD:{ref}"], cwd=repo, check=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Adaptador ALTH Character para COPOX")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("prepare")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--asset-dir", required=True)
    a.add_argument("--baseline-params", required=True)
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
    a.add_argument("--asset-dir", required=True)
    a.add_argument("--candidate-dir", required=True)
    a.set_defaults(func=cmd_execute)

    a = sub.add_parser("capture")
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--evidence-dir", required=True)
    a.add_argument("--run-dir", required=True)
    a.add_argument("--reference", required=True)
    a.add_argument("--audit-config", required=True)
    a.add_argument("--focus", default="head,face,hair")
    a.set_defaults(func=cmd_capture)

    a = sub.add_parser("learn")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--tournament", required=True)
    a.set_defaults(func=cmd_learn)

    a = sub.add_parser("promote")
    a.add_argument("--repo-root", default=".")
    a.add_argument("--asset-dir", required=True)
    a.add_argument("--candidate-dir", required=True)
    a.add_argument("--baseline-params", required=True)
    a.add_argument("--state-branch")
    a.add_argument("--cassette-id")
    a.add_argument("--target", required=True)
    a.add_argument("--persist", action="store_true")
    a.add_argument("--finalize", action="store_true")
    a.set_defaults(func=cmd_promote)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
