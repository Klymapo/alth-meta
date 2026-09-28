"""Visibility-aware multiview feature fusion.

Pixal3D's public multiview path averages per-view projected features. This module
implements the stricter variant we want for Theo: invalid projections must not
contribute, and optional view-confidence / facing-angle weights may downweight
ambiguous evidence.
"""

from __future__ import annotations

from typing import Optional
import numpy as np


def _broadcast_weight(weight: np.ndarray, target_ndim: int) -> np.ndarray:
    w = np.asarray(weight, dtype=np.float32)
    while w.ndim < target_ndim:
        w = np.expand_dims(w, axis=-1)
    return w


def visibility_aware_fusion(
    features: np.ndarray,
    valid_mask: np.ndarray,
    *,
    confidence: Optional[np.ndarray] = None,
    facing: Optional[np.ndarray] = None,
    eps: float = 1e-8,
    return_weight_sum: bool = False,
):
    """Fuse features across views while ignoring invisible/invalid projections.

    Parameters
    ----------
    features:
        Array shaped [..., V, C] or [V, ..., C]. The view axis is inferred from
        valid_mask: whichever features dimension matches valid_mask's last dim
        is treated as V when possible.
    valid_mask:
        Boolean/0-1 visibility shaped [..., V].
    confidence:
        Optional per-view or per-point confidence broadcastable to valid_mask.
    facing:
        Optional nonnegative facing-angle weight broadcastable to valid_mask.
    """
    f = np.asarray(features, dtype=np.float32)
    vm = np.asarray(valid_mask, dtype=np.float32)

    if f.ndim < 2:
        raise ValueError("features must have at least view and channel dimensions")
    if vm.ndim < 1:
        raise ValueError("valid_mask must include a view dimension")

    V = vm.shape[-1]
    candidate_axes = [i for i, s in enumerate(f.shape[:-1]) if s == V]
    if not candidate_axes:
        raise ValueError(f"Could not find view axis of size {V} in features shape {f.shape}")
    view_axis = candidate_axes[-1]

    # Move view axis next to channel: [..., V, C]
    if view_axis != f.ndim - 2:
        f = np.moveaxis(f, view_axis, -2)

    w = vm.astype(np.float32)
    if confidence is not None:
        w = w * np.asarray(confidence, dtype=np.float32)
    if facing is not None:
        w = w * np.clip(np.asarray(facing, dtype=np.float32), 0.0, None)

    w = np.broadcast_to(w, f.shape[:-1])
    weighted = f * w[..., None]
    denom = np.sum(w, axis=-1, keepdims=True)
    fused = np.sum(weighted, axis=-2) / np.maximum(denom, eps)

    if return_weight_sum:
        return fused, denom[..., 0]
    return fused


def masked_average_torch(features, valid_mask, confidence=None, facing=None, eps: float = 1e-8):
    """Torch equivalent, imported lazily so core ALTH does not require torch."""
    import torch

    f = features
    w = valid_mask.to(dtype=f.dtype)
    if confidence is not None:
        w = w * confidence.to(dtype=f.dtype)
    if facing is not None:
        w = w * torch.clamp(facing.to(dtype=f.dtype), min=0)

    while w.ndim < f.ndim:
        w = w.unsqueeze(-1)
    numerator = (f * w).sum(dim=-2)
    denominator = w.sum(dim=-2).clamp_min(eps)
    return numerator / denominator


def pixal3d_average_patch_description() -> str:
    """Human-readable guidance for patching Pixal3D locally.

    We intentionally keep this project-side integration small instead of vendoring
    Tencent's complete implementation. The local patch should carry the original
    MIT attribution when applied to a cloned Pixal3D checkout.
    """
    return (
        "In DinoV3ProjMultiViewFeatureExtractor.forward, retain each view's valid_mask "
        "from ProjGridMV/project_points_to_image_batch; accumulate z_view * valid_mask "
        "and divide by accumulated valid weights instead of unconditional V. Optionally "
        "multiply by per-view confidence/facing-angle weights."
    )
