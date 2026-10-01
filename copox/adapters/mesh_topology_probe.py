from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


def _geometry_report(name: str, geom: trimesh.Trimesh, decimals: int = 7) -> dict[str, Any]:
    vertices = np.asarray(geom.vertices, dtype=float)
    faces = np.asarray(geom.faces, dtype=np.int64)
    if len(vertices) == 0 or len(faces) == 0:
        return {"geometry": name, "vertices": len(vertices), "faces": len(faces), "valid": False}

    rounded = np.round(vertices, decimals=decimals)
    unique_pos, inverse, copies = np.unique(rounded, axis=0, return_inverse=True, return_counts=True)
    welded_faces = inverse[faces]
    welded_degenerate = int(np.sum(
        (welded_faces[:, 0] == welded_faces[:, 1]) |
        (welded_faces[:, 1] == welded_faces[:, 2]) |
        (welded_faces[:, 2] == welded_faces[:, 0])
    ))
    edges = np.sort(np.concatenate([
        welded_faces[:, [0, 1]], welded_faces[:, [1, 2]], welded_faces[:, [2, 0]]
    ], axis=0), axis=1)
    _, edge_counts = np.unique(edges, axis=0, return_counts=True)
    boundary_edges = int(np.sum(edge_counts == 1))
    manifold_edges = int(np.sum(edge_counts == 2))
    nonmanifold_edges = int(np.sum(edge_counts > 2))

    uv = np.asarray(getattr(geom.visual, "uv", []), dtype=float)
    uv_seam_positions = 0
    max_uv_variants = 0
    if uv.ndim == 2 and uv.shape == (len(vertices), 2):
        buckets: dict[int, set[tuple[float, float]]] = {}
        uv_round = np.round(uv, decimals=6)
        for raw_index, welded_index in enumerate(inverse):
            buckets.setdefault(int(welded_index), set()).add((float(uv_round[raw_index, 0]), float(uv_round[raw_index, 1])))
        variants = [len(v) for v in buckets.values()]
        uv_seam_positions = int(sum(n > 1 for n in variants))
        max_uv_variants = int(max(variants, default=0))

    raw_face_corner_expanded = bool(len(vertices) == faces.size and len(np.unique(faces)) == len(vertices))
    welded_manifold_closed = bool(boundary_edges == 0 and nonmanifold_edges == 0 and welded_degenerate == 0)
    return {
        "geometry": name,
        "valid": True,
        "vertices": int(len(vertices)),
        "faces": int(len(faces)),
        "raw_face_corner_expanded": raw_face_corner_expanded,
        "unique_positions_after_exactish_weld": int(len(unique_pos)),
        "weld_compression_ratio": float(len(unique_pos) / len(vertices)),
        "mean_position_copies": float(np.mean(copies)),
        "max_position_copies": int(np.max(copies)),
        "welded_topology": {
            "boundary_edges": boundary_edges,
            "manifold_edges": manifold_edges,
            "nonmanifold_edges": nonmanifold_edges,
            "degenerate_faces": welded_degenerate,
            "closed_manifold": welded_manifold_closed,
        },
        "uv": {
            "available": bool(uv.ndim == 2 and uv.shape == (len(vertices), 2)),
            "positions_with_multiple_uvs": uv_seam_positions,
            "max_uv_variants_at_one_position": max_uv_variants,
            "has_uv_seams": bool(uv_seam_positions > 0),
        },
    }


def probe(path: str | Path, output: str | Path) -> dict[str, Any]:
    scene = trimesh.load(str(path), force="scene")
    reports = [_geometry_report(str(name), geom) for name, geom in scene.geometry.items()]
    valid = [r for r in reports if r.get("valid")]
    dominant = max(valid, key=lambda r: r["vertices"]) if valid else None
    result = {
        "mode": "mesh_topology_probe",
        "geometries": reports,
        "dominant": dominant,
        "summary": {
            "geometry_count": len(valid),
            "dominant_is_face_corner_expanded": bool(dominant and dominant["raw_face_corner_expanded"]),
            "dominant_welds_to_closed_manifold": bool(dominant and dominant["welded_topology"]["closed_manifold"]),
            "dominant_has_uv_seams": bool(dominant and dominant["uv"]["has_uv_seams"]),
        },
        "learning": {
            "naive_vertex_merge_allowed": False,
            "reason": "Una geometría expandida por face-corners puede ser soldable, pero los seams UV/normales deben preservarse. Validar un candidato en Blender con UV por loop y render regression antes de promover limpieza topológica.",
        },
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnóstico de topología GLB y seams UV")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = probe(args.input, args.output)
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
