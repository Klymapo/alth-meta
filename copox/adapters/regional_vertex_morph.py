from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dominant_geometry(scene: trimesh.Scene) -> tuple[str, trimesh.Trimesh]:
    items = [(name, geom) for name, geom in scene.geometry.items() if hasattr(geom, "vertices")]
    if not items:
        raise RuntimeError("GLB sin geometría editable")
    return max(items, key=lambda item: len(item[1].vertices))


def _smoothstep01(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _box_weights(norm_vertices: np.ndarray, box: list[float], feather: float) -> np.ndarray:
    lo = np.asarray(box[:3], dtype=float)
    hi = np.asarray(box[3:], dtype=float)
    if np.any(hi <= lo):
        raise ValueError(f"Caja anatómica inválida: {box}")
    inside = np.all((norm_vertices >= lo) & (norm_vertices <= hi), axis=1)
    weights = np.zeros(len(norm_vertices), dtype=float)
    if not np.any(inside):
        return weights
    if feather <= 0:
        weights[inside] = 1.0
        return weights
    span = np.maximum(hi - lo, 1e-9)
    local = (norm_vertices - lo) / span
    edge = np.minimum(local, 1.0 - local).min(axis=1)
    weights = _smoothstep01(edge / max(feather, 1e-6))
    weights[~inside] = 0.0
    return weights


def _named_node_morph(scene: trimesh.Scene, nodes: list[str], scale: list[float], shift: list[float]) -> dict[str, Any]:
    available = set(scene.graph.nodes_geometry)
    missing = sorted(set(nodes) - available)
    if missing:
        raise RuntimeError(f"Nodos requeridos ausentes: {missing}")
    points: list[np.ndarray] = []
    for node in nodes:
        matrix, geom_name = scene.graph.get(node)
        geom = scene.geometry[geom_name]
        corners = np.column_stack([np.asarray(geom.bounding_box.vertices), np.ones(8)])
        world = (np.asarray(matrix) @ corners.T).T[:, :3]
        points.append(world)
    all_points = np.vstack(points)
    center = (all_points.min(axis=0) + all_points.max(axis=0)) / 2.0
    s = np.eye(4)
    s[0, 0], s[1, 1], s[2, 2] = [float(x) for x in scale]
    t0 = np.eye(4); t0[:3, 3] = -center
    t1 = np.eye(4); t1[:3, 3] = center + np.asarray(shift, dtype=float)
    transform = t1 @ s @ t0
    before = {}
    for node in nodes:
        matrix, geom_name = scene.graph.get(node)
        before[node] = np.asarray(matrix).copy()
        scene.graph.update(frame_to=node, matrix=transform @ np.asarray(matrix), geometry=geom_name)
    return {"mode": "named_nodes", "nodes": nodes, "center": center.tolist(), "changed": len(nodes), "before": {k: v.tolist() for k, v in before.items()}}


def _vertex_region_morph(scene: trimesh.Scene, boxes: list[list[float]], scale: list[float], shift: list[float], feather: float) -> dict[str, Any]:
    geom_name, geom = _dominant_geometry(scene)
    vertices = np.asarray(geom.vertices, dtype=float).copy()
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    norm = (vertices - lo) / span
    weights = np.zeros(len(vertices), dtype=float)
    for box in boxes:
        weights = np.maximum(weights, _box_weights(norm, box, feather))
    selected = weights > 0.0
    if not np.any(selected):
        raise RuntimeError("La región anatómica no seleccionó vértices")
    center = np.average(vertices[selected], axis=0, weights=np.maximum(weights[selected], 1e-9))
    scale_vec = np.asarray(scale, dtype=float)
    shift_vec = np.asarray(shift, dtype=float)
    target = center + (vertices - center) * scale_vec + shift_vec
    updated = vertices + weights[:, None] * (target - vertices)
    untouched_ok = bool(np.array_equal(updated[~selected], vertices[~selected]))
    geom.vertices = updated
    return {
        "mode": "vertex_region",
        "geometry": geom_name,
        "selected_vertices": int(selected.sum()),
        "total_vertices": int(len(vertices)),
        "selected_ratio": float(selected.mean()),
        "center": center.tolist(),
        "untouched_vertices_unchanged": untouched_ok,
    }


def morph(
    baseline: str | Path,
    config_path: str | Path,
    params_path: str | Path,
    output: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    cfg = _read_json(config_path)
    params = _read_json(params_path)
    region_id = str(params["region"])
    regions = cfg.get("morph_regions") or {}
    if region_id not in regions:
        raise RuntimeError(f"Región no definida para morph: {region_id}")
    spec = regions[region_id]
    scene = trimesh.load(str(baseline), force="scene")
    scale = [float(x) for x in params.get("scale", [1.0, 1.0, 1.0])]
    shift_mm = np.asarray(params.get("shift_mm", [0.0, 0.0, 0.0]), dtype=float)
    shift_model = (shift_mm / float(cfg.get("mesh_to_mm", 1000.0))).tolist()

    if spec.get("nodes"):
        detail = _named_node_morph(scene, [str(x) for x in spec["nodes"]], scale, shift_model)
    else:
        boxes = [[float(v) for v in box] for box in spec.get("boxes", [])]
        detail = _vertex_region_morph(scene, boxes, scale, shift_model, float(spec.get("feather", 0.15)))

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb")
    check = trimesh.load(str(out), force="scene").to_geometry()
    mesh_ok = bool(len(check.vertices) and len(check.faces) and np.isfinite(check.vertices).all())
    report = {
        "region": region_id,
        "mesh_integrity": mesh_ok,
        "params": params,
        "detail": detail,
        "safe_scope": bool(detail.get("untouched_vertices_unchanged", True)),
    }
    rp = Path(report_path)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Mutador regional anatómico con falloff")
    p.add_argument("--baseline", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--params", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()
    result = morph(args.baseline, args.config, args.params, args.output, args.report)
    print(json.dumps({"region": result["region"], "mesh_integrity": result["mesh_integrity"], "detail": result["detail"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
