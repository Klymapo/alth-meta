from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


class StateError(RuntimeError):
    pass


def _git(repo: Path, *args: str, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _remote_ref(branch: str) -> str:
    return f"refs/remotes/origin/{branch}"


def fetch_state_ref(repo: Path, branch: str) -> str | None:
    remote_ref = _remote_ref(branch)
    result = _git(
        repo,
        "fetch",
        "-q",
        "origin",
        f"refs/heads/{branch}:{remote_ref}",
        check=False,
    )
    if result.returncode != 0:
        return None
    probe = _git(repo, "rev-parse", "--verify", remote_ref, check=False)
    return probe.stdout.strip() if probe.returncode == 0 else None


def load_state(repo: Path, branch: str, output: Path, fallback: Path | None = None) -> dict[str, Any]:
    repo = repo.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    head = fetch_state_ref(repo, branch)
    if head:
        baseline = _git(repo, "show", f"{head}:baseline.json", check=False)
        if baseline.returncode == 0:
            output.write_text(baseline.stdout, encoding="utf-8")
            meta_result = _git(repo, "show", f"{head}:state.json", check=False)
            metadata = json.loads(meta_result.stdout) if meta_result.returncode == 0 and meta_result.stdout.strip() else {}
            metadata.update({"source": "state_branch", "branch": branch, "commit": head})
            return metadata
    if fallback is None or not fallback.exists():
        raise StateError(f"No existe estado remoto ni fallback para {branch}")
    shutil.copy2(fallback, output)
    return {"source": "fallback", "branch": branch, "commit": None, "fallback": str(fallback)}


def save_state(repo: Path, branch: str, baseline: Path, metadata: dict[str, Any] | None = None) -> str:
    repo = repo.resolve()
    baseline = baseline.resolve()
    if not baseline.exists():
        raise StateError(f"Baseline inexistente: {baseline}")

    parent = fetch_state_ref(repo, branch)
    metadata = dict(metadata or {})
    metadata.update({
        "branch": branch,
        "parent": parent,
        "saved_at": int(time.time()),
        "engine": "copox-loop-engine",
    })

    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "copox-loop-engine")
    env.setdefault("GIT_AUTHOR_EMAIL", "copox-loop-engine@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])

    baseline_blob = subprocess.run(
        ["git", "hash-object", "-w", str(baseline)], cwd=repo, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env,
    ).stdout.strip()

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        metadata_path = Path(fh.name)
    try:
        metadata_blob = subprocess.run(
            ["git", "hash-object", "-w", str(metadata_path)], cwd=repo, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env,
        ).stdout.strip()
    finally:
        metadata_path.unlink(missing_ok=True)

    tree_input = (
        f"100644 blob {baseline_blob}\tbaseline.json\n"
        f"100644 blob {metadata_blob}\tstate.json\n"
    )
    tree = subprocess.run(
        ["git", "mktree"], cwd=repo, text=True, input=tree_input,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env,
    ).stdout.strip()

    commit_cmd = ["git", "commit-tree", tree]
    if parent:
        commit_cmd += ["-p", parent]
    commit = subprocess.run(
        commit_cmd,
        cwd=repo,
        text=True,
        input=f"copox state: {metadata.get('cassette_id', branch)}\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        env=env,
    ).stdout.strip()

    push = subprocess.run(
        ["git", "push", "origin", f"{commit}:refs/heads/{branch}"],
        cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if push.returncode != 0:
        raise StateError(f"No se pudo guardar state branch {branch}: {push.stderr.strip()}")
    return commit


def main() -> int:
    p = argparse.ArgumentParser(description="Estado persistente COPOX en rama Git por cassette")
    sub = p.add_subparsers(dest="command", required=True)

    load = sub.add_parser("load")
    load.add_argument("--repo-root", default=".")
    load.add_argument("--branch", required=True)
    load.add_argument("--output", required=True)
    load.add_argument("--fallback")

    save = sub.add_parser("save")
    save.add_argument("--repo-root", default=".")
    save.add_argument("--branch", required=True)
    save.add_argument("--baseline", required=True)
    save.add_argument("--metadata-json", default="{}")

    args = p.parse_args()
    repo = Path(args.repo_root)
    if args.command == "load":
        meta = load_state(repo, args.branch, Path(args.output), Path(args.fallback) if args.fallback else None)
        print(json.dumps(meta, ensure_ascii=False))
        return 0
    metadata = json.loads(args.metadata_json)
    commit = save_state(repo, args.branch, Path(args.baseline), metadata)
    print(json.dumps({"branch": args.branch, "commit": commit}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
