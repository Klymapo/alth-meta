from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from copox.contracts import Cassette, ContractError, load_cassette\nfrom copox.production import load_policy, module_gate


def _expand(value: str, ctx: dict[str, str]) -> str:
    out = value
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", val)
    return out


def _run_command(command: list[str], ctx: dict[str, str], cwd: Path, env: dict[str, str]) -> None:
    argv = [_expand(str(x), ctx) for x in command]
    if not argv:
        return
    print("[copox] $", " ".join(shlex.quote(x) for x in argv), flush=True)
    subprocess.run(argv, cwd=cwd, env=env, check=True)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _base_context(cassette: Cassette, run_dir: Path) -> dict[str, str]:
    ctx = {
        "cassette_id": cassette.id,
        "cassette_path": str(cassette.path),
        "baseline": str(cassette.data["baseline"]),
        "target": str(cassette.data["target"]),
        "repo_root": str(Path.cwd()),
        "run_dir": str(run_dir),
    }
    for key, value in cassette.data.get("variables", {}).items():
        if isinstance(value, (str, int, float, bool)):
            ctx[str(key)] = str(value)
    return ctx


def _candidate_context(cassette: Cassette, run_dir: Path, candidate_id: str) -> dict[str, str]:
    candidate_dir = run_dir / "candidates" / candidate_id
    evidence_dir = candidate_dir / "evidence"
    audit_dir = candidate_dir / "audit"
    for p in (candidate_dir, evidence_dir, audit_dir):
        p.mkdir(parents=True, exist_ok=True)
    ctx = _base_context(cassette, run_dir)
    ctx.update({
        "candidate_id": candidate_id,
        "candidate_dir": str(candidate_dir),
        "evidence_dir": str(evidence_dir),
        "audit_dir": str(audit_dir),
    })
    return ctx


def _audit_candidate(cassette: Cassette, ctx: dict[str, str], env: dict[str, str]) -> tuple[bool, float, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    applicable_count = 0
    pass_count = 0
    scores: list[float] = []

    for auditor in cassette.auditors:
        if auditor.get("applicable", True) is False:
            results.append({"id": auditor["id"], "status": "N-A", "critical": bool(auditor.get("critical", False))})
            continue
        applicable_count += 1
        local_ctx = dict(ctx)
        local_ctx["auditor_id"] = str(auditor["id"])
        result_path = Path(ctx["audit_dir"]) / f"{auditor['id']}.json"
        local_ctx["audit_result"] = str(result_path)
        _run_command(list(auditor["command"]), local_ctx, Path.cwd(), env)
        if not result_path.exists():
            raise RuntimeError(f"El auditor {auditor['id']} no produjo {result_path}")
        result = _read_json(result_path)
        result.setdefault("id", auditor["id"])
        result.setdefault("critical", bool(auditor.get("critical", False)))
        status = str(result.get("status", "FAIL")).upper()
        result["status"] = status
        results.append(result)
        if status == "PASS":
            pass_count += 1
        score = result.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            scores.append(float(score))

    unanimous = applicable_count > 0 and pass_count == applicable_count
    selection_score = sum(scores) / len(scores) if scores else (1.0 if unanimous else 0.0)
    return unanimous, selection_score, results


def _evidence_ok(cassette: Cassette, candidate_dir: Path) -> tuple[bool, list[str]]:
    missing: list[str] = []
    evidence_dir = candidate_dir / "evidence"
    for pattern in cassette.data["reporting"].get("required_evidence", []):
        if not list(evidence_dir.glob(str(pattern))):
            missing.append(str(pattern))
    return not missing, missing


def run_campaign(cassette_path: str, output_root: str = ".copox/evidence") -> int:
    cassette = load_cassette(cassette_path)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    run_id = f"{cassette.id}-{stamp}-{os.getenv('GITHUB_RUN_NUMBER', 'local')}"
    run_dir = Path(output_root) / cassette.id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    maturity = cassette.maturity
    manifest: dict[str, Any] = {
        "engine": "copox-loop-engine",
        "version": "0.3.0",
        "run_id": run_id,
        "cassette": cassette.id,
        "kind": cassette.kind,
        "target": cassette.data["target"],
        "baseline": cassette.data["baseline"],
        "variables": cassette.data.get("variables", {}),
        "maturity": maturity,
        "started_at": int(time.time()),
        "status": "RUNNING",
        "candidates": [],
    }
    _write_json(run_dir / "manifest.json", manifest)

    if maturity is not None:
        _write_json(run_dir / "maturity.json", maturity)
        if maturity.get("block_execution", True) and not maturity.get("ready", False):
            manifest["status"] = "MATURITY_BLOCKED"
            manifest["finished_at"] = int(time.time())
            _write_json(run_dir / "manifest.json", manifest)
            blockers = ", ".join(f"{x['id']}:{x['computed_level']}" for x in maturity.get("blockers", []))
            print(f"[copox] MATURITY_BLOCKED: {blockers}", flush=True)
            return 4

    env = os.environ.copy()
    prepare = cassette.data.get("commands", {}).get("prepare", [])
    if prepare:
        _run_command(list(prepare), _base_context(cassette, run_dir), Path.cwd(), env)

    passing: list[dict[str, Any]] = []
    generated = 0
    tournament = 0

    while generated < cassette.max_candidates and not passing:
        tournament += 1
        batch = min(cassette.tournament_size, cassette.max_candidates - generated)
        for slot in range(batch):
            generated += 1
            candidate_id = f"t{tournament:02d}-c{slot + 1:02d}"
            ctx = _candidate_context(cassette, run_dir, candidate_id)
            candidate_dir = Path(ctx["candidate_dir"])
            record: dict[str, Any] = {"id": candidate_id, "tournament": tournament, "status": "RUNNING"}
            try:
                for phase in ("mutate", "execute", "capture"):
                    command = cassette.data.get("commands", {}).get(phase, [])
                    if command:
                        _run_command(list(command), ctx, Path.cwd(), env)
                evidence_pass, missing = _evidence_ok(cassette, candidate_dir)
                if not evidence_pass:
                    record.update({"status": "REJECTED", "reason": "missing_evidence", "missing_evidence": missing})
                else:
                    unanimous, score, audit_results = _audit_candidate(cassette, ctx, env)
                    record.update({"audit": audit_results, "score": score})
                    if unanimous:
                        production = cassette.data.get("production") or {}
                        if production:
                            policy_path = Path(str(production["policy"]))
                            if not policy_path.is_absolute():
                                policy_path = Path.cwd() / policy_path
                            gate = module_gate(
                                policy=load_policy(policy_path),
                                module_id=str(production["primary_module"]),
                                candidate_dir=candidate_dir,
                                audit_results=audit_results,
                                score=score,
                            )
                            record["production_gate"] = gate
                            _write_json(candidate_dir / "production_gate.json", gate)
                            if gate["status"] != "PASS":
                                record.update({"status": "REJECTED", "reason": "production_gate_veto"})
                            else:
                                record["status"] = "ELIGIBLE"
                                passing.append(record)
                        else:
                            record["status"] = "ELIGIBLE"
                            passing.append(record)
                    else:
                        record.update({"status": "REJECTED", "reason": "auditor_veto"})
            except Exception as exc:
                record.update({"status": "ERROR", "reason": str(exc)})
            manifest["candidates"].append(record)
            _write_json(candidate_dir / "candidate.json", record)
            _write_json(run_dir / "manifest.json", manifest)

        if not passing:
            learning = cassette.data.get("commands", {}).get("learn", [])
            if learning:
                learn_ctx = _base_context(cassette, run_dir)
                learn_ctx["tournament"] = str(tournament)
                _run_command(list(learning), learn_ctx, Path.cwd(), env)

    if passing:
        winner = sorted(passing, key=lambda x: float(x.get("score", 0.0)), reverse=True)[0]
        manifest["winner"] = winner["id"]
        manifest["status"] = "APPROVED_INTERNAL"
        winner_ctx = _candidate_context(cassette, run_dir, winner["id"])
        promote = cassette.data.get("commands", {}).get("promote", [])
        if promote:
            _run_command(list(promote), winner_ctx, Path.cwd(), env)
        manifest["status"] = "PROMOTED"
        manifest["finished_at"] = int(time.time())
        _write_json(run_dir / "manifest.json", manifest)
        report = cassette.data.get("commands", {}).get("report", [])
        if report:
            _run_command(list(report), winner_ctx, Path.cwd(), env)
        print(f"[copox] PASS: {winner['id']} promovido", flush=True)
        return 0

    manifest["status"] = "PLATEAU"
    manifest["finished_at"] = int(time.time())
    _write_json(run_dir / "manifest.json", manifest)
    print("[copox] PLATEAU: ningún candidato obtuvo unanimidad", flush=True)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="COPOX Loop Engine")
    parser.add_argument("cassette", help="Ruta al cassette JSON")
    parser.add_argument("--output-root", default=".copox/evidence")
    args = parser.parse_args()
    try:
        return run_campaign(args.cassette, args.output_root)
    except ContractError as exc:
        print(f"[copox] CONTRACT ERROR: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
