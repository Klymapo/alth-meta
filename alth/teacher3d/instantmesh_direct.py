"""Direct-known-views adapter for a local InstantMesh checkout.

The stock InstantMesh run.py first asks Zero123++ to invent sparse views. Theo already
has real front/side/back/3-quarter references, so this adapter prepares the camera
vector format expected by `forward_planes(images, cameras)` and provides a runner
script generator that skips synthetic-view generation entirely.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
import math
import numpy as np

from .camera import CameraSpec, orbit_camera_matrix


def fov_to_intrinsics4(fov_deg: float) -> np.ndarray:
    """InstantMesh normalized camera intrinsics [fx, fy, cx, cy]."""
    focal = 0.5 / math.tan(math.radians(fov_deg) * 0.5)
    return np.array([focal, focal, 0.5, 0.5], dtype=np.float32)


def instantmesh_camera_vector(view: CameraSpec) -> np.ndarray:
    """Build the 16-D vector used by InstantMesh LRM cameras.

    Layout follows get_zero123plus_input_cameras: first 12 values are the first three
    rows of c2w flattened, followed by normalized [fx, fy, cx, cy].
    """
    c2w = orbit_camera_matrix(view.azimuth_deg, view.elevation_deg, view.distance).astype(np.float32)
    extrinsics = c2w.reshape(-1)[:12]
    intrinsics = fov_to_intrinsics4(view.fov_deg)
    return np.concatenate([extrinsics, intrinsics], axis=0)


def build_camera_batch(views: Sequence[CameraSpec]) -> np.ndarray:
    return np.stack([instantmesh_camera_vector(v) for v in views], axis=0)[None]


def save_camera_npz(path: str | Path, views: Sequence[CameraSpec]) -> Path:
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, cameras=build_camera_batch(views), names=np.array([v.name for v in views]))
    return path


def write_direct_runner(path: str | Path) -> Path:
    """Write an executable helper meant to run *inside* an InstantMesh environment.

    Inputs are real view images plus an NPZ camera batch created above. All model
    source/checkpoints are local. The script mirrors InstantMesh's reconstruction stage
    but intentionally omits Zero123++.
    """
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    source=r'''import argparse
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from torchvision.transforms import v2
from omegaconf import OmegaConf

parser=argparse.ArgumentParser()
parser.add_argument("config")
parser.add_argument("checkpoint")
parser.add_argument("camera_npz")
parser.add_argument("output")
parser.add_argument("images", nargs="+")
args=parser.parse_args()

from src.utils.train_util import instantiate_from_config

config=OmegaConf.load(args.config)
model=instantiate_from_config(config.model_config)
state=torch.load(args.checkpoint, map_location="cpu")
state=state.get("state_dict", state)
if any(k.startswith("lrm_generator.") for k in state):
    state={k[14:]:v for k,v in state.items() if k.startswith("lrm_generator.")}
model.load_state_dict(state, strict=True)
model=model.cuda().eval()

cam=np.load(args.camera_npz)["cameras"].astype("float32")
cameras=torch.from_numpy(cam).cuda()
imgs=[]
for p in args.images:
    im=Image.open(p).convert("RGB")
    t=torch.from_numpy(np.asarray(im).astype("float32")/255.0).permute(2,0,1)
    imgs.append(t)
images=torch.stack(imgs,dim=0)[None].cuda()
images=v2.functional.resize(images,320,interpolation=3,antialias=True).clamp(0,1)
if images.shape[1] != cameras.shape[1]:
    raise ValueError(f"images={images.shape[1]} cameras={cameras.shape[1]}")

with torch.no_grad():
    planes=model.forward_planes(images,cameras)
    mesh=model.extract_mesh(planes,use_texture_map=False,**config.infer_config)

# InstantMesh returns implementation-dependent mesh tuples/objects; support common forms.
out=Path(args.output)
out.parent.mkdir(parents=True,exist_ok=True)
obj=mesh[0] if isinstance(mesh,(list,tuple)) else mesh
if hasattr(obj,"export"):
    obj.export(str(out))
elif isinstance(obj,(list,tuple)) and len(obj)>=2:
    import trimesh
    trimesh.Trimesh(vertices=obj[0],faces=obj[1],process=False).export(str(out))
else:
    raise TypeError(f"Unsupported extract_mesh output: {type(obj)}")
'''
    path.write_text(source,encoding="utf-8")
    return path
