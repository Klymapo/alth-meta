"""Camera calibration helpers for multiview teacher reconstruction.

Pixal3D multiview expects Blender/NeRF-style camera-to-world matrices, Z-up
world coordinates and a horizontal FOV. Theo's turnarounds are near-orthographic,
so this module supports low-FOV / long-distance approximations and FOV sweeps.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence
import json
import math
import numpy as np


@dataclass(frozen=True)
class CameraSpec:
    name: str
    file_path: str
    azimuth_deg: float
    elevation_deg: float = 0.0
    distance: float = 4.0
    fov_deg: float = 10.0

    @property
    def camera_angle_x(self) -> float:
        return math.radians(self.fov_deg)


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n <= 1e-12:
        raise ValueError("Cannot normalize a zero-length vector")
    return v / n


def look_at_c2w(position: Sequence[float], target=(0.0, 0.0, 0.0), world_up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Return a Blender-style camera-to-world matrix.

    Camera local -Z points at the target and local +Y is up.
    """
    pos = np.asarray(position, dtype=float)
    target = np.asarray(target, dtype=float)
    up_hint = np.asarray(world_up, dtype=float)

    forward = _normalize(target - pos)        # desired camera -Z direction
    z_axis = -forward                         # camera local +Z in world
    x_axis = _normalize(np.cross(up_hint, z_axis))
    y_axis = _normalize(np.cross(z_axis, x_axis))

    out = np.eye(4, dtype=float)
    out[:3, 0] = x_axis
    out[:3, 1] = y_axis
    out[:3, 2] = z_axis
    out[:3, 3] = pos
    return out


def orbit_camera_matrix(azimuth_deg: float, elevation_deg: float = 0.0, distance: float = 4.0) -> np.ndarray:
    """Orbit around the origin while keeping Z-up.

    Convention chosen for Theo/Pixal3D:
    azimuth 0°  -> canonical front camera near (0, -d, 0)
    azimuth 90° -> right-side orbit
    azimuth 180°-> back
    azimuth 270°-> left-side orbit
    """
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    horizontal = distance * math.cos(el)
    x = horizontal * math.sin(az)
    y = -horizontal * math.cos(az)
    z = distance * math.sin(el)
    return look_at_c2w((x, y, z))


def make_default_theo_views(
    front: str,
    side: str,
    back: str,
    three_quarter: str,
    *,
    fov_deg: float = 10.0,
    distance: float = 8.0,
) -> list[CameraSpec]:
    """Create a conservative near-orthographic four-view camera set."""
    return [
        CameraSpec("front", front, 0.0, 0.0, distance, fov_deg),
        CameraSpec("side", side, 90.0, 0.0, distance, fov_deg),
        CameraSpec("back", back, 180.0, 0.0, distance, fov_deg),
        CameraSpec("three_quarter", three_quarter, 45.0, 0.0, distance, fov_deg),
    ]


def build_transforms_json(views: Iterable[CameraSpec], mesh_scale: float = 1.0) -> dict:
    frames = []
    for view in views:
        frames.append({
            "name": view.name,
            "file_path": view.file_path,
            "camera_angle_x": view.camera_angle_x,
            "transform_matrix": orbit_camera_matrix(
                view.azimuth_deg, view.elevation_deg, view.distance
            ).tolist(),
        })
    return {"mesh_scale": float(mesh_scale), "frames": frames}


def save_transforms_json(path: str | Path, views: Iterable[CameraSpec], mesh_scale: float = 1.0) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_transforms_json(views, mesh_scale), indent=2), encoding="utf-8")
    return path


def fov_sweep(candidates=(5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0)) -> tuple[float, ...]:
    """Default FOV search for drawings that are close to orthographic."""
    return tuple(float(x) for x in candidates)


def score_fov_by_bbox(
    reference_width_px: float,
    reference_height_px: float,
    object_width: float,
    object_height: float,
    distance: float,
    candidate_fovs: Iterable[float] | None = None,
) -> list[dict]:
    """Cheap camera pre-calibration using projected bounding-box aspect/coverage.

    This does not replace render-based calibration. It is a fast first pass before
    running a full teacher model.
    """
    if candidate_fovs is None:
        candidate_fovs = fov_sweep()
    ref_aspect = reference_width_px / max(reference_height_px, 1e-9)
    obj_aspect = object_width / max(object_height, 1e-9)
    out = []
    for fov in candidate_fovs:
        focal = 0.5 / math.tan(math.radians(fov) / 2.0)
        projected_h = object_height * focal / max(distance, 1e-9)
        projected_w = object_width * focal / max(distance, 1e-9)
        aspect = projected_w / max(projected_h, 1e-9)
        out.append({
            "fov_deg": float(fov),
            "aspect_error": abs(aspect - ref_aspect),
            "reference_aspect": ref_aspect,
            "object_aspect": obj_aspect,
            "relative_projected_height": projected_h,
        })
    return sorted(out, key=lambda row: row["aspect_error"])
