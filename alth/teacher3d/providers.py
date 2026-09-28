"""Adapters for running free/open-source teacher models locally.

No provider here calls a paid API. Runtime expects cloned source repositories and,
for reproducibility, local model weights. Public downloads can be handled outside
this module once and then cached locally.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import os
import subprocess
import sys

from .policy import ensure_local_only


@dataclass(frozen=True)
class LocalRun:
    provider: str
    command: list[str]
    cwd: str
    output_path: str | None = None
    env: dict[str, str] | None = None

    def execute(self, check: bool = True) -> subprocess.CompletedProcess:
        merged = os.environ.copy()
        if self.env:
            merged.update(self.env)
        return subprocess.run(self.command, cwd=self.cwd, env=merged, check=check)


def _py(repo: Path) -> str:
    # Use current interpreter by default; dedicated conda/venv users can invoke
    # these builders from the target environment.
    return sys.executable


def pixal3d_multiview_run(
    repo_path: str | Path,
    views_dir: str | Path,
    output_glb: str | Path,
    *,
    low_vram: bool = True,
    num_views: int | None = None,
) -> LocalRun:
    repo=Path(repo_path)
    ensure_local_only("pixal3d", repo)
    cmd=[_py(repo), "inference_mv.py", "--views_dir", str(Path(views_dir).resolve()), "--output", str(Path(output_glb).resolve())]
    if num_views is not None:
        cmd += ["--num_views", str(int(num_views))]
    if low_vram:
        cmd.append("--low_vram")
    return LocalRun("pixal3d", cmd, str(repo), str(output_glb), {"ATTN_BACKEND":"sdpa"})


def triposr_run(
    repo_path: str | Path,
    image: str | Path,
    output_dir: str | Path,
    *,
    local_weights: str | Path,
    mc_resolution: int = 256,
    glb: bool = True,
    no_remove_bg: bool = False,
) -> LocalRun:
    repo=Path(repo_path)
    ensure_local_only("triposr", repo, local_weights)
    cmd=[
        _py(repo), "run.py", str(Path(image).resolve()),
        "--pretrained-model-name-or-path", str(Path(local_weights).resolve()),
        "--output-dir", str(Path(output_dir).resolve()),
        "--mc-resolution", str(int(mc_resolution)),
        "--model-save-format", "glb" if glb else "obj",
    ]
    if no_remove_bg:
        cmd.append("--no-remove-bg")
    return LocalRun("triposr", cmd, str(repo), str(output_dir))


def instantmesh_single_image_run(
    repo_path: str | Path,
    config: str | Path,
    image: str | Path,
    output_dir: str | Path,
    *,
    seed: int = 42,
    views: int = 6,
    no_rembg: bool = False,
) -> LocalRun:
    """Run the stock InstantMesh pipeline locally.

    Note: stock run.py first generates views with Zero123++. For Theo we prefer a
    custom direct-known-views adapter later; this stock adapter is retained as an
    independent teacher for consensus.
    """
    repo=Path(repo_path)
    ensure_local_only("instantmesh", repo)
    cmd=[
        _py(repo), "run.py", str(Path(config).resolve()), str(Path(image).resolve()),
        "--output_path", str(Path(output_dir).resolve()),
        "--seed", str(int(seed)),
        "--view", str(int(views)),
    ]
    if no_rembg:
        cmd.append("--no_rembg")
    return LocalRun("instantmesh", cmd, str(repo), str(output_dir))


def trellis_multi_image_script(repo_path: str | Path, output_script: str | Path) -> Path:
    """Create a tiny local TRELLIS runner template using run_multi_image.

    The generated script intentionally requires a LOCAL pretrained model path so it
    cannot silently fetch weights or call a service at runtime.
    """
    repo=Path(repo_path)
    ensure_local_only("trellis", repo)
    output_script=Path(output_script)
    source='''from pathlib import Path\nimport argparse\nfrom PIL import Image\n\nparser=argparse.ArgumentParser()\nparser.add_argument("--repo", required=True)\nparser.add_argument("--weights", required=True)\nparser.add_argument("--output", required=True)\nparser.add_argument("images", nargs="+")\nargs=parser.parse_args()\n\nimport sys\nsys.path.insert(0, args.repo)\nfrom trellis.pipelines import TrellisImageTo3DPipeline\nfrom trellis.utils import postprocessing_utils\n\nweights=Path(args.weights)\nif not weights.exists():\n    raise FileNotFoundError(weights)\npipeline=TrellisImageTo3DPipeline.from_pretrained(str(weights))\npipeline.cuda()\nimgs=[Image.open(p).convert("RGBA") for p in args.images]\noutputs=pipeline.run_multi_image(imgs, seed=1, formats=["gaussian","mesh"], mode="multidiffusion")\nglb=postprocessing_utils.to_glb(outputs["gaussian"][0], outputs["mesh"][0], simplify=0.95, texture_size=1024)\nglb.export(args.output)\n'''
    output_script.parent.mkdir(parents=True, exist_ok=True)
    output_script.write_text(source, encoding="utf-8")
    return output_script


def trellis2_runner_note() -> str:
    return (
        "TRELLIS.2 is integrated as a local secondary teacher. Keep its environment "
        "separate because its compiled sparse/voxel dependencies are heavy; point the "
        "ALTH orchestration layer at its local example/inference entry point and local "
        "weights. Never route it through a hosted API."
    )
