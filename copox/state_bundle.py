from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


class StateBundleError(RuntimeError):
    pass


def _run(repo: Path, *args: str, check: bool = True, text: bool = True, input_data=None):
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, text=text, input=input_data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def fetch_state_ref(repo: Path, branch: str) -> str | None:
    remote_ref = f"refs/remotes/origin/{branch}"
    result = _run(repo, "fetch", "-q", "origin", f"refs/heads/{branch}:{remote_ref}", check=False)
    if result.returncode != 0:
        return None
    probe = _run(repo, "rev-parse", "--verify", remote_ref, check=False)
    return probe.stdout.strip() if probe.returncode == 0 else None


def load_bundle(
    repo: Path,
    branch: str,
    baseline_output: Path,
    model_output: Path,
    fallback_baseline: Path,
    fallback_model: Path,
) -> dict[str, Any]:
    repo = repo.resolve()
    baseline_output = baseline_output.resolve()
    model_output = model_output.resolve()
    baseline_output.parent.mkdir(parents=True, exist_ok=True)
    model_output.parent.mkdir(parents=True, exist_ok=True)
    head = fetch_state_ref(repo, branch)
    if head:
        baseline = _run(repo, "show", f"{head}:baseline.json", check=False)
        model = _run(repo, "show", f"{head}:model.glb", check=False, text=False)
        if baseline.returncode == 0 and model.returncode == 0:
            baseline_output.write_text(baseline.stdout, encoding="utf-8")
            model_output.write_bytes(model.stdout)
            meta_result = _run(repo, "show", f"{head}:state.json", check=False)
            metadata = json.loads(meta_result.stdout) if meta_result.returncode == 0 and meta_result.stdout.strip() else {}
            metadata.update({"source": "state_bundle", "branch": branch, "commit": head})
            return metadata
    if not fallback_baseline.exists() or not fallback_model.exists():
        raise StateBundleError(f"No existe bundle remoto ni fallbacks completos para {branch}")
    shutil.copy2(fallback_baseline, baseline_output)
    shutil.copy2(fallback_model, model_output)
    return {
        "source": "fallback_bundle",
        "branch": branch,
        "commit": None,
        "fallback_baseline": str(fallback_baseline),
        "fallback_model": str(fallback_model),
        "legacy_state_ignored": bool(head),
    }


def save_bundle(
    repo: Path,
    branch: str,
    baseline: Path,
    model: Path,
    metadata: dict[str, Any] | None = None,
) -> str:
    repo = repo.resolve()
    baseline = baseline.resolve()
    model = model.resolve()
    if not baseline.exists() or not model.exists():
        raise StateBundleError(f"Bundle incompleto: baseline={baseline.exists()} model={model.exists()}")
    parent = fetch_state_ref(repo, branch)
    metadata = dict(metadata or {})
    metadata.update({
        "branch": branch,
        "parent": parent,
        "saved_at": int(time.time()),
        "engine": "copox-loop-engine",
        "state_format": "baseline+model-v1",
    })
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "copox-loop-engine")
    env.setdefault("GIT_AUTHOR_EMAIL", "copox-loop-engine@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])

    def hash_file(path: Path) -> str:
        return subprocess.run(
            ["git", "hash-object", "-w", str(path)], cwd=repo, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env,
        ).stdout.strip()

    baseline_blob = hash_file(baseline)
    model_blob = hash_file(model)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        meta_path = Path(fh.name)
    try:
        meta_blob = hash_file(meta_path)
    finally:
        meta_path.unlink(missing_ok=True)

    tree_input = (
        f"100644 blob {baseline_blob}\tbaseline.json\n"
        f"100644 blob {model_blob}\tmodel.glb\n"
        f"100644 blob {meta_blob}\tstate.json\n"
    )
    tree = subprocess.run(
        ["git", "mktree"], cwd=repo, text=True, input=tree_input,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env,
    ).stdout.strip()
    cmd = ["git", "commit-tree", tree]
    if parent:
        cmd += ["-p", parent]
    commit = subprocess.run(
        cmd, cwd=repo, text=True,
        input=f"copox state bundle: {metadata.get('cassette_id', branch)}\n",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env,
    ).stdout.strip()
    push = subprocess.run(
        ["git", "push", "origin", f"{commit}:refs/heads/{branch}"], cwd=repo, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if push.returncode != 0:
        raise StateBundleError(f"No se pudo guardar bundle {branch}: {push.stderr.strip()}")
    return commit
