from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import trimesh


def morph(input_glb: str, output_glb: str, report_path: str, scale_xyz: list[float]) -> dict:
    scene = trimesh.load(input_glb, force="scene")
    before = np.asarray(scene.bounds, dtype=float)
    center = before.mean(axis=0)
    factors = np.asarray(scale_xyz, dtype=float)
    if factors.shape != (3,) or np.any(factors <= 0):
        raise ValueError("scale_xyz debe contener tres factores positivos")

    to_origin = np.eye(4); to_origin[:3, 3] = -center
    scale = np.eye(4); scale[0,0], scale[1,1], scale[2,2] = factors
    back = np.eye(4); back[:3, 3] = center
    transform = back @ scale @ to_origin
    scene.apply_transform(transform)
    after = np.asarray(scene.bounds, dtype=float)

    out = Path(output_glb)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb")
    check = trimesh.load(str(out), force="scene")
    mesh = check.to_geometry()
    mesh_ok = bool(len(mesh.vertices) and len(mesh.faces) and np.isfinite(mesh.vertices).all())
    result = {
        "mode": "global_axis_morph",
        "scale_xyz": factors.tolist(),
        "center": center.tolist(),
        "bounds_before": before.tolist(),
        "bounds_after": after.tolist(),
        "mesh_integrity": mesh_ok,
        "geometry_count_before": len(scene.geometry),
        "geometry_count_after": len(check.geometry),
        "promotion_allowed": False,
    }
    Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p=argparse.ArgumentParser(description="Escala global coherente de un GLB por ejes")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--scale-x", type=float, default=1.0)
    p.add_argument("--scale-y", type=float, default=1.0)
    p.add_argument("--scale-z", type=float, default=1.0)
    args=p.parse_args()
    result=morph(args.input,args.output,args.report,[args.scale_x,args.scale_y,args.scale_z])
    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
