"""3D likeness metrics for comparing ALTH procedural meshes to teacher meshes."""

from __future__ import annotations

from typing import Callable, Mapping
import numpy as np


def _nearest_distance(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    try:
        from scipy.spatial import cKDTree
        d, idx = cKDTree(b).query(a, k=1)
        return d, idx
    except Exception:
        ds=[]; ids=[]; chunk=1024
        for i in range(0,len(a),chunk):
            aa=a[i:i+chunk]
            m=((aa[:,None,:]-b[None,:,:])**2).sum(axis=2)
            ids.append(np.argmin(m,axis=1))
            ds.append(np.sqrt(np.min(m,axis=1)))
        return np.concatenate(ds), np.concatenate(ids)


def sample_vertices(vertices: np.ndarray, n: int = 10000, seed: int = 42) -> np.ndarray:
    v=np.asarray(vertices,dtype=np.float64)
    if len(v)<=n: return v.copy()
    rng=np.random.default_rng(seed)
    return v[rng.choice(len(v),size=n,replace=False)]


def chamfer_distance(a_vertices: np.ndarray, b_vertices: np.ndarray, sample_points: int = 10000, seed: int = 42) -> dict:
    """Symmetric Chamfer proxy using sampled vertices."""
    a=sample_vertices(a_vertices,sample_points,seed)
    b=sample_vertices(b_vertices,sample_points,seed+1)
    da,_=_nearest_distance(a,b)
    db,_=_nearest_distance(b,a)
    return {
        "mean_a_to_b":float(da.mean()),
        "mean_b_to_a":float(db.mean()),
        "symmetric_mean":float(0.5*(da.mean()+db.mean())),
        "p95_a_to_b":float(np.quantile(da,0.95)),
        "p95_b_to_a":float(np.quantile(db,0.95)),
    }


def signed_surface_error(candidate_vertices: np.ndarray, teacher_vertices: np.ndarray, center: np.ndarray | None = None) -> dict:
    """Approximate signed radial error against a teacher cloud.

    Positive means candidate samples tend to sit farther from the chosen center than
    their nearest teacher samples; negative means they tend to sit inside.
    """
    c=np.asarray(candidate_vertices,dtype=np.float64)
    t=np.asarray(teacher_vertices,dtype=np.float64)
    if center is None:
        center=np.median(t,axis=0)
    d,idx=_nearest_distance(c,t)
    tc=t[idx]
    rc=np.linalg.norm(c-center,axis=1)
    rt=np.linalg.norm(tc-center,axis=1)
    signed=rc-rt
    return {
        "mean_signed":float(signed.mean()),
        "median_signed":float(np.median(signed)),
        "mean_abs":float(np.abs(signed).mean()),
        "p95_abs":float(np.quantile(np.abs(signed),0.95)),
        "nearest_distance_mean":float(d.mean()),
    }


def bbox_depth(vertices: np.ndarray, axis: int = 1) -> float:
    v=np.asarray(vertices,dtype=float)
    return float(v[:,axis].max()-v[:,axis].min())


def regional_depth_report(
    candidate_vertices: np.ndarray,
    teacher_vertices: np.ndarray,
    regions: Mapping[str, Callable[[np.ndarray], np.ndarray]],
    *,
    depth_axis: int = 1,
) -> dict:
    """Compare candidate vs teacher depth per semantic region.

    Region functions receive Nx3 vertices and return a boolean mask. This keeps
    segmentation policy outside the metric and lets Theo define hair/head/feet zones.
    """
    c=np.asarray(candidate_vertices,dtype=float)
    t=np.asarray(teacher_vertices,dtype=float)
    out={}
    for name, selector in regions.items():
        cm=np.asarray(selector(c),dtype=bool)
        tm=np.asarray(selector(t),dtype=bool)
        if cm.sum()<2 or tm.sum()<2:
            out[name]={"status":"insufficient_points","candidate_points":int(cm.sum()),"teacher_points":int(tm.sum())}
            continue
        cd=bbox_depth(c[cm],depth_axis)
        td=bbox_depth(t[tm],depth_axis)
        out[name]={
            "candidate_depth":cd,
            "teacher_depth":td,
            "delta":cd-td,
            "relative_error":(cd-td)/max(abs(td),1e-9),
            "candidate_points":int(cm.sum()),
            "teacher_points":int(tm.sum()),
        }
    return out


def cross_section_extent(vertices: np.ndarray, z_center: float, half_thickness: float, axes=(0,1)) -> dict:
    v=np.asarray(vertices,dtype=float)
    mask=np.abs(v[:,2]-z_center)<=half_thickness
    pts=v[mask]
    if len(pts)<2:
        return {"status":"insufficient_points","count":int(len(pts))}
    result={"status":"ok","count":int(len(pts))}
    for axis in axes:
        result[f"axis_{axis}_extent"]=float(pts[:,axis].max()-pts[:,axis].min())
    return result
