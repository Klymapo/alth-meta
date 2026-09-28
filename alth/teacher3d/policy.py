"""Hard policy: teacher-3D integration must remain local, free and quota-free."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os


@dataclass(frozen=True)
class ModelPolicy:
    name: str
    repo: str
    license: str
    allowed: bool
    notes: str


FREE_LOCAL_MODELS: Mapping[str, ModelPolicy] = {
    "pixal3d": ModelPolicy(
        "Pixal3D", "https://github.com/TencentARC/Pixal3D", "MIT", True,
        "Primary multiview teacher. Run locally from cloned source and local weights.",
    ),
    "trellis2": ModelPolicy(
        "TRELLIS.2", "https://github.com/microsoft/TRELLIS.2", "MIT", True,
        "High-quality local image-to-3D backbone / secondary teacher.",
    ),
    "trellis": ModelPolicy(
        "TRELLIS", "https://github.com/microsoft/TRELLIS", "MIT", True,
        "Architectural reference / secondary teacher.",
    ),
    "instantmesh": ModelPolicy(
        "InstantMesh", "https://github.com/TencentARC/InstantMesh", "Apache-2.0", True,
        "Independent sparse-view reconstructor for teacher consensus.",
    ),
    "triposr": ModelPolicy(
        "TripoSR", "https://github.com/VAST-AI-Research/TripoSR", "MIT", True,
        "Fast single-view sanity teacher.",
    ),
    "hunyuan3d": ModelPolicy(
        "Hunyuan3D", "https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1", "Community License", False,
        "Excluded from the default pipeline because its license is materially more restrictive.",
    ),
}

_FORBIDDEN_ENV_PREFIXES = (
    "OPENAI_", "ANTHROPIC_", "REPLICATE_", "FAL_", "RUNPOD_", "TOGETHER_",
    "STABILITY_API", "TRIPO_API", "MESHY_", "HYPER3D_",
)


def ensure_local_only(model_name: str, repo_path: str | Path | None = None, weights_path: str | Path | None = None) -> None:
    """Fail closed if a provider is not approved for the local-only pipeline.

    This deliberately does not accept remote API endpoints. Public model-weight
    downloads may be performed separately, but inference must run from local files.
    """
    key = model_name.lower().replace(".", "")
    policy = FREE_LOCAL_MODELS.get(key)
    if policy is None or not policy.allowed:
        raise RuntimeError(f"Model '{model_name}' is not allowed by the free-local policy.")

    for env_name in os.environ:
        if any(env_name.upper().startswith(prefix) for prefix in _FORBIDDEN_ENV_PREFIXES):
            # Presence alone is not fatal globally; only reject if callers try to
            # route teacher inference through this module while API credentials exist.
            raise RuntimeError(
                f"Refusing teacher inference while API credential variable '{env_name}' is present. "
                "Run this pipeline with local model files only."
            )

    if repo_path is not None and not Path(repo_path).exists():
        raise FileNotFoundError(f"Local source repo not found: {repo_path}")
    if weights_path is not None and not Path(weights_path).exists():
        raise FileNotFoundError(f"Local weights not found: {weights_path}")


def allowed_model_names() -> tuple[str, ...]:
    return tuple(k for k, v in FREE_LOCAL_MODELS.items() if v.allowed)
