from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


HAIR_TOKENS = ("fleco", "mechon", "mechón", "capa_", "corona", "hair", "pelo")
EAR_TOKENS = ("oreja", "ear")


def _group(name: str) -> str:
    low = name.lower()
    if any(x in low for x in EAR_TOKENS):
        return "ears"
    if any(x in low for x in HAIR_TOKENS):
        return "hair"
    return "body_or_head"


def _texture_uv_stats(geom: trimesh.Trimesh) -> dict[str, Any] | None:
    visual = getattr(geom, "visual", None)
    uv = getattr(visual, "uv", None)
    material = getattr(visual, "material", None)
    image = getattr(material, "baseColorTexture", None) if material is not None else None
    if uv is None or image is None:
        return None
    arr = np.asarray(image.convert("RGB"))
    uv_arr = np.asarray(uv, dtype=float)
    h, w = arr.shape[:2]
    x = np.clip(np.rint(uv_arr[:, 0] * (w - 1)).astype(int), 0, w - 1)
    y = np.clip(np.rint((1.0 - uv_arr[:, 1]) * (h - 1)).astype(int), 0, h - 1)
    colors = arr[y, x]
    return {
        "texture_size": [int(w), int(h)],
        "uv_vertices": int(len(uv_arr)),
        "median_rgb": [int(x) for x in np.median(colors, axis=0)],
        "mean_rgb": [round(float(x), 2) for x in np.mean(colors, axis=0)],
    }


def inventory(path: str | Path) -> dict[str, Any]:
    scene = trimesh.load(str(path), force="scene")
    rows: list[dict[str, Any]] = []
    for node_name in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph.get(node_name)
        geom = scene.geometry[geometry_name]
        vertices = trimesh.transformations.transform_points(np.asarray(geom.vertices), transform)
        mn = vertices.min(axis=0)
        mx = vertices.max(axis=0)
        dims = mx - mn
        center = (mn + mx) / 2.0
        material = getattr(getattr(geom, "visual", None), "material", None)
        row = {
            "node": str(node_name),
            "geometry": str(geometry_name),
            "group": _group(str(node_name)),
            "vertices": int(len(geom.vertices)),
            "faces": int(len(geom.faces)),
            "center": [round(float(x), 6) for x in center],
            "dimensions": [round(float(x), 6) for x in dims],
            "bounds_min": [round(float(x), 6) for x in mn],
            "bounds_max": [round(float(x), 6) for x in mx],
            "material": getattr(material, "name", None),
            "uv_texture": _texture_uv_stats(geom),
        }
        rows.append(row)
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row["node"])
    materials = sorted({str(x["material"]) for x in rows if x.get("material")})
    return {
        "format": "copox-model-inventory-v1",
        "source": str(path),
        "node_count": len(rows),
        "geometry_count": len(scene.geometry),
        "groups": groups,
        "group_counts": {k: len(v) for k, v in groups.items()},
        "materials": materials,
        "nodes": rows,
        "notes": [
            "La clasificación usa sólo nombres explícitos de nodos; body_or_head no infiere subregiones internas.",
            "Los colores UV son estadísticos de muestreo de vértices y sirven como evidencia diagnóstica, no como segmentación semántica definitiva."
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Inventario semántico y material de un GLB")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = inventory(args.input)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"node_count": result["node_count"], "group_counts": result["group_counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
