from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from copox.adapters.regional_reference_audit import audit_regions
from copox.production.diagnostics import build as build_diagnostics
from copox.production.module_router import choose as choose_module
from copox.production.regional_trial import run_trial
from copox.state_bundle import load_bundle, save_bundle


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: str | Path, data: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _slot(candidate_id: str) -> int:
    try:
        return int(candidate_id.split("-c", 1)[1])
    except Exception as exc:
        raise ValueError(f"candidate_id inválido: {candidate_id}") from exc


def _tournament(candidate_id: str) -> int:
    try:
        return int(candidate_id.split("-c", 1)[0].lstrip("t"))
    except Exception as exc:
        raise ValueError(f"candidate_id inválido: {candidate_id}") from exc


def _route_supported(diagnostics: dict[str, Any], config: dict[str, Any], cooldown: set[str]) -> dict[str, Any]:
    supported = set((config.get("morph_regions") or {}).keys())
    for module, row in (diagnostics.get("modules") or {}).items():
        if module not in supported:
            row["actionable"] = False
            row["reason"] = str(row.get("reason") or "") + "; dispatcher_pending"
        if module in cooldown:
            row["actionable"] = False
            row["reason"] = str(row.get("reason") or "") + "; cooldown"
    return diagnostics


def cmd_prepare(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    baseline_dir = run_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    runtime_params = baseline_dir / "params.json"
    runtime_model = baseline_dir / "model.glb"
    fallback_params = (repo / args.baseline_params).resolve()
    fallback_model = (repo / args.baseline_model).resolve()

    if args.state_branch:
        source = load_bundle(repo, args.state_branch, runtime_params, runtime_model, fallback_params, fallback_model)
    else:
        shutil.copy2(fallback_params, runtime_params)
        shutil.copy2(fallback_model, runtime_model)
        source = {"source": "seed_bundle", "fallback_model": str(fallback_model)}
    _write(run_dir / "baseline_source.json", source)

    diagnosis_dir = run_dir / "diagnosis"
    regional = audit_regions(
        str(runtime_model), str(runtime_model), str((repo / args.reference).resolve()),
        str((repo / args.config).resolve()), str(diagnosis_dir / "regional_metrics.json"),
        str(diagnosis_dir / "evidence"),
    )
    diagnostics = build_diagnostics(regional)
    learning_meta = dict(source.get("learning") or {})
    cooldown = set(str(x) for x in learning_meta.get("cooldown_modules", []))
    cfg = _read((repo / args.config).resolve())
    diagnostics = _route_supported(diagnostics, cfg, cooldown)
    policy = _read((repo / args.policy).resolve())
    route = choose_module(policy, diagnostics)
    if not route.get("selected"):
        # Si el cooldown deja cero candidatos, se consume y se reintenta sin él.
        diagnostics = build_diagnostics(regional)
        diagnostics = _route_supported(diagnostics, cfg, set())
        route = choose_module(policy, diagnostics)
        cooldown = set()
    _write(run_dir / "diagnostics.json", diagnostics)
    _write(run_dir / "route.json", route)
    _write(run_dir / "learning_state.json", {
        "source_learning": learning_meta,
        "cooldown_applied": sorted(cooldown),
        "selected": route.get("selected"),
    })
    if not route.get("selected"):
        raise RuntimeError("No hay módulo regional accionable para el cassette M5")
    return 0


def cmd_mutate(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    candidate = Path(args.candidate_dir).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    route = _read(run_dir / "route.json")
    spec = {
        "module": route["selected"],
        "candidate_id": args.candidate_id,
        "slot": _slot(args.candidate_id),
        "tournament": _tournament(args.candidate_id),
    }
    _write(candidate / "module_spec.json", spec)
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    candidate = Path(args.candidate_dir).resolve()
    spec = _read(candidate / "module_spec.json")
    trial = run_trial(
        str(run_dir / "baseline" / "model.glb"),
        str((repo / args.reference).resolve()),
        str((repo / args.config).resolve()),
        str((repo / args.policy).resolve()),
        str(spec["module"]), int(spec["slot"]), str(candidate), int(spec["tournament"]),
    )
    result = trial["result"]
    gate = trial["gate"]
    metrics = {
        "production": {
            "module": result["module"],
            "gate_pass": bool(gate["promotion_allowed"]),
            "target_gain_pp": float(result["target_gain_pp"]),
            "global_gain_pp": float(result["global_gain_pp"]),
            "worst_view_delta_pp": float(result["worst_view_delta_pp"]),
            "reasons": list(gate.get("reasons") or []),
        },
        "technical": {
            "mesh_integrity": bool(result["mesh_integrity"]),
            "scope_safe": bool(result["scope_safe"]),
        },
        "regression": {"ok": bool(result["regression_ok"])},
        "evidence": {"complete": bool(result["evidence_complete"])},
        "semantic": {"ready": bool(result["semantic_ready"])},
    }
    _write(candidate / "metrics.json", metrics)
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ("gate.json", "module_result.json", "trial.json", "metrics.json"):
        src = candidate / name
        if src.exists():
            shutil.copy2(src, evidence / name)
    # El engine exige al menos una evidencia visual; copiamos closeups regionales existentes.
    for src in (candidate / "evidence").glob("*.png"):
        # si evidence_dir coincide con candidate/evidence no hace falta copiar sobre sí mismo
        dst = evidence / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
    return 0


def _reroute(run_dir: Path, policy_path: Path, config_path: Path, failed_module: str) -> dict[str, Any]:
    diagnostics = _read(run_dir / "diagnostics.json")
    row = (diagnostics.get("modules") or {}).get(failed_module)
    if row:
        row["actionable"] = False
        row["reason"] = str(row.get("reason") or "") + "; plateau_this_run"
    route = choose_module(_read(policy_path), diagnostics)
    if route.get("selected"):
        _write(run_dir / "route.json", route)
        _write(run_dir / "diagnostics.json", diagnostics)
    return route


def cmd_learn(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    route = _read(run_dir / "route.json")
    failed_module = str(route.get("selected"))
    new_route = _reroute(run_dir, (repo / args.policy).resolve(), (repo / args.config).resolve(), failed_module)

    learning = {
        "failed_module": failed_module,
        "next_module": new_route.get("selected"),
        "tournament": int(args.tournament),
        "cooldown_modules": [failed_module],
        "reason": "Ningún hermano obtuvo gate M5; rotar módulo/técnica, no promover baseline.",
    }
    _write(run_dir / f"learning_t{int(args.tournament):02d}.json", learning)

    if args.state_branch:
        # Persistimos únicamente aprendizaje y el MISMO GLB de baseline.
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


def cmd_promote(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    candidate = Path(args.candidate_dir).resolve()
    gate = _read(candidate / "gate.json")
    if gate.get("promotion_allowed") is not True:
        raise RuntimeError("Intento de promote sin gate M5 PASS")
    result = _read(candidate / "module_result.json")
    state_commit = None
    if args.state_branch:
        state_commit = save_bundle(
            repo, args.state_branch,
            Path(args.baseline_params).resolve() if Path(args.baseline_params).is_absolute() else (repo / args.baseline_params).resolve(),
            candidate / "model.glb",
            {
                "cassette_id": args.cassette_id,
                "target": args.target,
                "module": result["module"],
                "candidate": candidate.name,
                "promotion": True,
                "gate": gate,
                "learning": {"cooldown_modules": []},
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            },
        )
    _write(candidate / "promotion.json", {
        "promotion_allowed": True,
        "state_branch": args.state_branch,
        "state_commit": state_commit,
        "module": result["module"],
    })
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Adapter M5 de modelo completo; routing regional inicial")
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
    a.set_defaults(func=cmd_prepare)

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
    a.set_defaults(func=cmd_capture)

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
    a.set_defaults(func=cmd_promote)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
