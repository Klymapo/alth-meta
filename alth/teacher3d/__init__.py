"""Local-only teacher-3D utilities for ALTH.

This package integrates free/open-source image-to-3D tooling without paid APIs,
usage quotas, token systems, or weekly limits. External model repositories are
expected to be cloned locally and run from local weights.
"""

from .policy import FREE_LOCAL_MODELS, ensure_local_only
from .camera import CameraSpec, orbit_camera_matrix, build_transforms_json
from .fusion import visibility_aware_fusion
from .consensus import TeacherMesh, consensus_confidence
from .audit3d import chamfer_distance, signed_surface_error, regional_depth_report

__all__ = [
    "FREE_LOCAL_MODELS",
    "ensure_local_only",
    "CameraSpec",
    "orbit_camera_matrix",
    "build_transforms_json",
    "visibility_aware_fusion",
    "TeacherMesh",
    "consensus_confidence",
    "chamfer_distance",
    "signed_surface_error",
    "regional_depth_report",
]
