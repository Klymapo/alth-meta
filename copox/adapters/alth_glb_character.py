from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _node_geometry(scene: trimesh.Scene) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in scene.graph.nodes_geometry:
        _, geometry = scene.graph.get(node)
        out[str(node)] = str(geometry)
    return out


def _world_corners(scene: trimesh.Scene, node: str) -> np.ndarray:
    matrix, geometry_name = scene.graph.get(node)
    geometry = scene.geometry[geometry_name]
    corners = np.asarray(geometry.bounding_box.vertices, dtype=float)
    hom = np.column_stack([corners, np.ones(len(corners))])
    return (np.asarray(matrix, dtype=float) @ hom.T).T[:, :3]


def _group_center(scene: trimesh.Scene, nodes: list[str]) -> np.ndarray:
    points = np.vstack([_world_corners(scene, node) for node in nodes])
    return (points.min(axis=0) + points.max(axis=0)) / 2.0


def _axis_scale_matrix(center: np.ndarray, factors: dict[int, float]) -> np.ndarray:
    scale = np.eye(4)
    for axis, value in factors.items():
        scale[int(axis), int(axis)] = float(value)
    to_origin = np.eye(4)
    to_origin[:3, 3] = -center
    back = np.eye(4)
    back[:3, 3] = center
    return back @ scale @ to_origin


def _translation_matrix(vector: np.ndarray) -> np.ndarray:
    out = np.eye(4)
    out[:3, 3] = np.asarray(vector, dtype=float)
    return out


def _apply_world(scene: trimesh.Scene, nodes: list[str], transform: np.ndarray) -> None:
    for node in nodes:
        matrix, geometry_name = scene.graph.get(node)
        scene.graph.update(frame_to=node, matrix=transform @ np.asarray(matrix), geometry=geometry_name)


def _get(data: dict[str, Any], dotted: str, default: float) -> float:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return float(default)
        cur = cur[part]
    return float(cur)


def _validate_nodes(scene: trimesh.Scene, groups: dict[str, list[str]]) -> None:
    available = set(_node_geometry(scene))
    missing = sorted({node for nodes in groups.values() for node in nodes if node not in available})
    if missing:
        raise RuntimeError(f"El GLB no contiene los nodos requeridos por la campaña: {missing}")


def _matrix_snapshot(scene: trimesh.Scene, nodes: list[str]) -> dict[str, np.ndarray]:
    return {node: np.asarray(scene.graph.get(node)[0], dtype=float).copy() for node in nodes}


def _pair_symmetry_error_mm(scene: trimesh.Scene, pairs: list[list[str]], horizontal_axis: int, mesh_to_mm: float) -> float:
    errors: list[float] = []
    for pair in pairs:
        if len(pair) != 2:
            continue
        a, b = pair
        ca, cb = _group_center(scene, [a]), _group_center(scene, [b])
        errors.append(abs(abs(float(ca[horizontal_axis])) - abs(float(cb[horizontal_axis]))) * mesh_to_mm)
    return float(max(errors, default=0.0))


def apply_structured_hair(
    baseline_glb: str | Path,
    params_path: str | Path,
    config_path: str | Path,
    output_glb: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    params = read_json(params_path)
    cfg = read_json(config_path)
    edit = cfg.get("glb_edit") or {}
    groups = {str(k): [str(x) for x in v] for k, v in (edit.get("groups") or {}).items()}
    if not groups:
        raise RuntimeError("glb_edit.groups no está definido")

    scene = trimesh.load(str(baseline_glb), force="scene")
    _validate_nodes(scene, groups)
    nodes = _node_geometry(scene)
    hair_nodes = sorted({node for members in groups.values() for node in members})
    frozen_nodes = sorted(set(nodes) - set(hair_nodes))
    frozen_before = _matrix_snapshot(scene, frozen_nodes)

    coords = cfg.get("coordinates") or {}
    h_axis = int(coords.get("front_horizontal_axis", 0))
    v_axis = int(coords.get("vertical_axis", 2))
    d_axis = int(coords.get("depth_axis", 1))
    mesh_to_mm = float(cfg.get("mesh_to_mm", 1000.0))
    mm_to_model = 1.0 / mesh_to_mm

    def scale_group(group: str, horizontal: float = 1.0, vertical: float = 1.0, depth: float = 1.0) -> None:
        members = groups.get(group, [])
        if not members:
            return
        center = _group_center(scene, members)
        _apply_world(scene, members, _axis_scale_matrix(center, {h_axis: horizontal, v_axis: vertical, d_axis: depth}))

    def translate_group(group: str, horizontal_mm: float = 0.0, vertical_mm: float = 0.0, depth_mm: float = 0.0) -> None:
        members = groups.get(group, [])
        if not members:
            return
        vec = np.zeros(3, dtype=float)
        vec[h_axis] = horizontal_mm * mm_to_model
        vec[v_axis] = vertical_mm * mm_to_model
        vec[d_axis] = depth_mm * mm_to_model
        _apply_world(scene, members, _translation_matrix(vec))

    scale_group("front", horizontal=_get(params, "hair.front_width_scale", 1.0), vertical=_get(params, "hair.front_height_scale", 1.0))
    translate_group("front", depth_mm=_get(params, "hair.front_depth_mm", 0.0))
    scale_group("crown", horizontal=_get(params, "hair.crown_width_scale", 1.0))
    translate_group("crown", vertical_mm=_get(params, "hair.crown_height_mm", 0.0))
    side_width = _get(params, "hair.side_width_scale", 1.0)
    side_height = _get(params, "hair.side_height_scale", 1.0)
    for side in ("side_left", "side_right"):
        scale_group(side, horizontal=side_width, vertical=side_height)
    outward = _get(params, "hair.side_outward_mm", 0.0)
    translate_group("side_left", horizontal_mm=-outward)
    translate_group("side_right", horizontal_mm=outward)
    scale_group("back", vertical=_get(params, "hair.back_height_scale", 1.0))
    translate_group("back", depth_mm=_get(params, "hair.back_depth_mm", 0.0))

    frozen_ok = all(np.allclose(scene.graph.get(node)[0], matrix, atol=1e-12) for node, matrix in frozen_before.items())
    pairs = [[str(x) for x in p] for p in edit.get("symmetry_pairs", [])]
    baseline_scene = trimesh.load(str(baseline_glb), force="scene")
    baseline_symmetry = _pair_symmetry_error_mm(baseline_scene, pairs, h_axis, mesh_to_mm)
    candidate_symmetry = _pair_symmetry_error_mm(scene, pairs, h_axis, mesh_to_mm)
    symmetry_growth = max(0.0, candidate_symmetry - baseline_symmetry)
    tolerance = float(edit.get("symmetry_growth_tolerance_mm", 0.75))

    output_glb = Path(output_glb)
    output_glb.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(output_glb), file_type="glb")
    check_scene = trimesh.load(str(output_glb), force="scene")
    mesh = check_scene.to_geometry()
    mesh_integrity = bool(len(mesh.vertices) and len(mesh.faces) and np.isfinite(mesh.vertices).all())
    degenerate = int(np.sum(np.asarray(mesh.area_faces) <= 1e-14)) if len(mesh.faces) else 0
    structure_ok = bool(frozen_ok and symmetry_growth <= tolerance)

    checks = [
        {"id": "mesh_integrity", "ok": mesh_integrity},
        {"id": "frozen_nodes_unchanged", "ok": frozen_ok, "count": len(frozen_nodes)},
        {"id": "required_hair_groups_present", "ok": True, "count": len(hair_nodes)},
        {"id": "structured_symmetry", "ok": structure_ok, "growth_mm": symmetry_growth, "tolerance_mm": tolerance},
    ]
    report = {
        "verificacion": {"ok": all(bool(c["ok"]) for c in checks), "checks": checks},
        "technical": {
            "mesh_integrity": mesh_integrity,
            "degenerate_triangles": degenerate,
            "frozen_nodes_unchanged": frozen_ok,
            "hair_nodes": hair_nodes,
        },
        "structure": {
            "hair_structure_ok": structure_ok,
            "randomness_penalty_mm": symmetry_growth,
            "baseline_pair_symmetry_error_mm": baseline_symmetry,
            "candidate_pair_symmetry_error_mm": candidate_symmetry,
        },
        "params": params,
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Edición estructurada de un personaje GLB aprobado")
    p.add_argument("--baseline", required=True)
    p.add_argument("--params", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()
    report = apply_structured_hair(args.baseline, args.params, args.config, args.output, args.report)
    print(json.dumps({"ok": report["verificacion"]["ok"], "structure": report["structure"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
