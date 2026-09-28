"""Local TRELLIS.2 runner generator.

TRELLIS.2's public example loads a local/Hub pretrained pipeline, runs image-to-3D,
and exports through o_voxel. ALTH keeps it as a secondary teacher and requires a
local weights directory at runtime so no hosted inference service is involved.
"""

from pathlib import Path

from .policy import ensure_local_only


def write_trellis2_runner(repo_path: str | Path, path: str | Path) -> Path:
    repo=Path(repo_path)
    ensure_local_only("trellis2", repo)
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    source=r'''import argparse
from pathlib import Path
import sys
from PIL import Image

parser=argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--weights", required=True)
parser.add_argument("--image", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--decimation", type=int, default=300000)
parser.add_argument("--texture-size", type=int, default=1024)
args=parser.parse_args()

repo=Path(args.repo).resolve(); weights=Path(args.weights).resolve()
if not repo.exists(): raise FileNotFoundError(repo)
if not weights.exists(): raise FileNotFoundError(weights)
sys.path.insert(0,str(repo))

from trellis2.pipelines import Trellis2ImageTo3DPipeline
import o_voxel

pipeline=Trellis2ImageTo3DPipeline.from_pretrained(str(weights))
pipeline.cuda()
mesh=pipeline.run(Image.open(args.image))[0]
mesh.simplify(16777216)

glb=o_voxel.postprocess.to_glb(
    vertices=mesh.vertices,
    faces=mesh.faces,
    attr_volume=mesh.attrs,
    coords=mesh.coords,
    attr_layout=mesh.layout,
    voxel_size=mesh.voxel_size,
    aabb=[[-0.5,-0.5,-0.5],[0.5,0.5,0.5]],
    decimation_target=args.decimation,
    texture_size=args.texture_size,
    remesh=True,
    remesh_band=1,
    remesh_project=0,
    verbose=True,
)
glb.export(args.output, extension_webp=True)
'''
    path.write_text(source, encoding="utf-8")
    return path
