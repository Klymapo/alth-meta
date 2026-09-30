"""Bootstrap approved third-party source trees locally with plain git clone.

This module clones SOURCE CODE only. It never calls a paid inference service and
never requests API keys/tokens. Model weights remain separate local artifacts.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

from .policy import FREE_LOCAL_MODELS


DEFAULT_REPOS = {
    "pixal3d": ("https://github.com/TencentARC/Pixal3D.git", "master"),
    "trellis2": ("https://github.com/microsoft/TRELLIS.2.git", "main"),
    "trellis": ("https://github.com/microsoft/TRELLIS.git", "main"),
    "instantmesh": ("https://github.com/TencentARC/InstantMesh.git", "main"),
    "triposr": ("https://github.com/VAST-AI-Research/TripoSR.git", "main"),
}


def clone_repo(name: str, root: str | Path = "_vendor/teacher3d", *, update: bool = False) -> Path:
    key=name.lower().replace(".", "")
    policy=FREE_LOCAL_MODELS.get(key)
    if policy is None or not policy.allowed:
        raise RuntimeError(f"'{name}' is not approved by the local-free policy")
    url, branch=DEFAULT_REPOS[key]
    root=Path(root)
    root.mkdir(parents=True, exist_ok=True)
    dest=root/key
    if dest.exists():
        if update:
            subprocess.run(["git","-C",str(dest),"pull","--ff-only"],check=True)
        return dest
    subprocess.run([
        "git","clone","--depth","1","--branch",branch,"--recurse-submodules",url,str(dest)
    ],check=True)
    return dest


def bootstrap_all(root: str | Path = "_vendor/teacher3d") -> dict[str, str]:
    return {name:str(clone_repo(name,root)) for name in DEFAULT_REPOS}


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description="Clone free/open-source local teacher-3D sources")
    parser.add_argument("models", nargs="*", default=list(DEFAULT_REPOS))
    parser.add_argument("--root", default="_vendor/teacher3d")
    parser.add_argument("--update", action="store_true")
    args=parser.parse_args()
    for model in args.models:
        print(f"{model}: {clone_repo(model,args.root,update=args.update)}")
