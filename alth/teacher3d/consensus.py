"""Teacher-mesh consensus and confidence estimation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
import numpy as np


@dataclass
class TeacherMesh:
    name: str
    vertices: np.ndarray
    faces: np.ndarray | None = None
    source_path: str | None = None
    weight: float = 1.0

    @classmethod
    def from_trimesh(cls, name, mesh, source_path=None, weight=1.0):
        return cls(
            name=name,
            vertices=np.asarray(mesh.vertices, dtype=np.float64),
            faces=np.asarray(mesh.faces, dtype=np.int64) if getattr(mesh, "faces", None) is not None else None,
            source_path=str(source_path) if source_path is not None else None,
            weight=float(weight),
        )


def _sample_points(vertices: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    vertices = np.asarray(vertices, dtype=np.float64)
    if len(vertices) <= n:
        return vertices.copy()
    idx = rng.choice(len(vertices), size=n, replace=False)
    return vertices[idx]


def _nearest_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    try:
        from scipy.spatial import cKDTree
        return cKDTree(b).query(a, k=1)[0]
    except Exception:
        # Portable fallback for small samples.
        out=[]
        chunk=1024
        for i in range(0,len(a),chunk):
            aa=a[i:i+chunk]
            d=((aa[:,None,:]-b[None,:,:])**2).sum(axis=2)
            out.append(np.sqrt(d.min(axis=1)))
        return np.concatenate(out)


def pairwise_teacher_distance(teachers: Sequence[TeacherMesh], sample_points: int = 6000, seed: int = 42) -> np.ndarray:
    """Symmetric nearest-neighbor surface proxy between every pair of teachers."""
    if len(teachers) < 2:
        return np.zeros((len(teachers), len(teachers)), dtype=float)
    rng=np.random.default_rng(seed)
    samples=[_sample_points(t.vertices, sample_points, rng) for t in teachers]
    n=len(teachers)
    mat=np.zeros((n,n),dtype=float)
    for i in range(n):
        for j in range(i+1,n):
            dij=_nearest_distance(samples[i],samples[j]).mean()
            dji=_nearest_distance(samples[j],samples[i]).mean()
            d=0.5*(dij+dji)
            mat[i,j]=mat[j,i]=d
    return mat


def consensus_confidence(
    teachers: Sequence[TeacherMesh],
    *,
    sample_points: int = 6000,
    scale_reference: float | None = None,
    seed: int = 42,
) -> dict:
    """Estimate teacher agreement; high agreement means higher confidence.

    Confidence = exp(-mean_pair_distance / scale_reference). If no explicit scale
    is provided, the median diagonal of combined bbox extents is used.
    """
    if not teachers:
        raise ValueError("At least one teacher is required")
    mat=pairwise_teacher_distance(teachers, sample_points=sample_points, seed=seed)
    if len(teachers)==1:
        return {"global_confidence":0.5,"pairwise_distance":mat.tolist(),"note":"single teacher; confidence capped"}

    pair=mat[np.triu_indices(len(teachers),k=1)]
    mean_d=float(pair.mean())
    if scale_reference is None:
        extents=[]
        for t in teachers:
            bb=t.vertices.max(axis=0)-t.vertices.min(axis=0)
            extents.append(float(np.linalg.norm(bb)))
        scale_reference=float(np.median(extents)) or 1.0
    confidence=float(np.exp(-mean_d/max(scale_reference,1e-9)))
    per_teacher=[]
    for i,t in enumerate(teachers):
        others=np.delete(mat[i],i)
        md=float(others.mean()) if len(others) else 0.0
        per_teacher.append({"name":t.name,"mean_distance_to_others":md,"relative_confidence":float(np.exp(-md/max(scale_reference,1e-9)))})
    return {
        "global_confidence":confidence,
        "mean_pair_distance":mean_d,
        "scale_reference":scale_reference,
        "pairwise_distance":mat.tolist(),
        "teachers":per_teacher,
    }


def robust_consensus_points(teachers: Sequence[TeacherMesh], samples_per_teacher: int = 4000, seed: int = 42) -> np.ndarray:
    """Return a pooled point cloud after trimming gross outliers per teacher.

    This is intentionally conservative: it is a measurement cloud, not a mesh.
    """
    rng=np.random.default_rng(seed)
    clouds=[]
    for t in teachers:
        pts=_sample_points(t.vertices,samples_per_teacher,rng)
        center=np.median(pts,axis=0)
        r=np.linalg.norm(pts-center,axis=1)
        cutoff=np.quantile(r,0.995)
        clouds.append(pts[r<=cutoff])
    return np.concatenate(clouds,axis=0)
