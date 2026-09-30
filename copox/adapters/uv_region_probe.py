from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


def _world_vertices(scene: trimesh.Scene, node: str) -> tuple[np.ndarray, trimesh.Trimesh]:
    matrix, geometry_name = scene.graph.get(node)
    geometry = scene.geometry[geometry_name]
    vertices = np.asarray(geometry.vertices, dtype=float)
    hom = np.column_stack([vertices, np.ones(len(vertices))])
    return (np.asarray(matrix, dtype=float) @ hom.T).T[:, :3], geometry


def _sample_pixels(geometry: trimesh.Trimesh, mask: np.ndarray | None = None) -> np.ndarray:
    uv = np.asarray(getattr(geometry.visual, "uv", []), dtype=float)
    material = getattr(geometry.visual, "material", None)
    image = getattr(material, "baseColorTexture", None)
    if uv.ndim != 2 or uv.shape[1] != 2 or image is None:
        return np.empty((0, 3), dtype=float)
    if mask is not None:
        uv = uv[np.asarray(mask, dtype=bool)]
    if len(uv) == 0:
        return np.empty((0, 3), dtype=float)
    arr = np.asarray(image.convert("RGB"))
    h, w = arr.shape[:2]
    x = np.clip(np.rint(uv[:, 0] * (w - 1)).astype(int), 0, w - 1)
    y = np.clip(np.rint((1.0 - uv[:, 1]) * (h - 1)).astype(int), 0, h - 1)
    return arr[y, x].astype(float)


def _stats(pixels: np.ndarray) -> dict[str, Any]:
    if len(pixels) == 0:
        return {"count": 0, "mean_rgb": None, "median_rgb": None}
    return {
        "count": int(len(pixels)),
        "mean_rgb": np.mean(pixels, axis=0).tolist(),
        "median_rgb": np.median(pixels, axis=0).tolist(),
        "q10_rgb": np.quantile(pixels, 0.10, axis=0).tolist(),
        "q90_rgb": np.quantile(pixels, 0.90, axis=0).tolist(),
    }


def _mean_rgb(pixels: np.ndarray) -> np.ndarray | None:
    return np.mean(pixels, axis=0) if len(pixels) else None


def probe(path: str | Path, output: str | Path, padding_ratio: float = 0.60) -> dict[str, Any]:
    scene = trimesh.load(str(path), force="scene")
    node_names = [str(x) for x in scene.graph.nodes_geometry]
    hair_nodes = [x for x in node_names if any(k in x.lower() for k in ("fleco", "mechon", "capa_", "corona", "pelo", "hair"))]
    ear_nodes = [x for x in node_names if "oreja" in x.lower() or "ear" in x.lower()]
    if not ear_nodes:
        raise RuntimeError("No hay nodos explícitos de oreja para comparar")

    hair_pixels = []
    explicit_ear_pixels = []
    ear_world_boxes: list[tuple[np.ndarray, np.ndarray]] = []
    for node in hair_nodes:
        _, geom = _world_vertices(scene, node)
        p = _sample_pixels(geom)
        if len(p):
            hair_pixels.append(p)
    for node in ear_nodes:
        world, geom = _world_vertices(scene, node)
        ear_world_boxes.append((world.min(axis=0), world.max(axis=0)))
        p = _sample_pixels(geom)
        if len(p):
            explicit_ear_pixels.append(p)

    hair_pixels_arr = np.vstack(hair_pixels) if hair_pixels else np.empty((0, 3))
    explicit_ear_arr = np.vstack(explicit_ear_pixels) if explicit_ear_pixels else np.empty((0, 3))

    dominant_node = max(node_names, key=lambda n: len(scene.geometry[scene.graph.get(n)[1]].vertices))
    body_world, body_geom = _world_vertices(scene, dominant_node)
    embedded_parts = []
    selected_counts = []
    for lo, hi in ear_world_boxes:
        pad = (hi - lo) * float(padding_ratio)
        selected = np.all((body_world >= lo - pad) & (body_world <= hi + pad), axis=1)
        selected_counts.append(int(selected.sum()))
        p = _sample_pixels(body_geom, selected)
        if len(p):
            embedded_parts.append(p)
    embedded_arr = np.vstack(embedded_parts) if embedded_parts else np.empty((0, 3))

    hair_mean = _mean_rgb(hair_pixels_arr)
    explicit_mean = _mean_rgb(explicit_ear_arr)
    embedded_mean = _mean_rgb(embedded_arr)
    distance_to_hair = None
    distance_to_explicit = None
    embedded_hair_like = None
    if embedded_mean is not None and hair_mean is not None and explicit_mean is not None:
        distance_to_hair = float(np.linalg.norm(embedded_mean - hair_mean))
        distance_to_explicit = float(np.linalg.norm(embedded_mean - explicit_mean))
        embedded_hair_like = bool(distance_to_hair < distance_to_explicit)

    result = {
        "mode": "uv_region_material_probe",
        "dominant_body_node": dominant_node,
        "hair_nodes": hair_nodes,
        "explicit_ear_nodes": ear_nodes,
        "body_vertices_sampled_near_explicit_ears": selected_counts,
        "samples": {
            "hair": _stats(hair_pixels_arr),
            "explicit_ears": _stats(explicit_ear_arr),
            "body_ear_neighborhood": _stats(embedded_arr),
        },
        "comparison": {
            "body_ear_neighborhood_distance_to_hair_rgb": distance_to_hair,
            "body_ear_neighborhood_distance_to_explicit_ear_rgb": distance_to_explicit,
            "body_ear_neighborhood_is_closer_to_hair": embedded_hair_like,
        },
        "learning": {
            "interpretation": "Si la zona de oreja embebida en la malla principal se parece cromáticamente más al pelo que a las orejas explícitas, investigar UV/atlas de esa zona antes de añadir geometría nueva.",
            "automatic_fix_allowed": False,
        },
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnóstico UV/material de regiones semánticas")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--padding-ratio", type=float, default=0.60)
    args = p.parse_args()
    result = probe(args.input, args.output, args.padding_ratio)
    print(json.dumps(result["comparison"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
