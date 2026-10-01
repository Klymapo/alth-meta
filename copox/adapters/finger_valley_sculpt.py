from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image

from copox.adapters.alth_character_audit import (
    crop_norm,
    load_config,
    load_scene,
    person_mask,
    region_mask,
    registration_from_baseline,
)
from copox.adapters.finger_gap_plan import _pixel_to_norm
from copox.adapters.finger_valley_probe import _valleys


def _to_h(points: np.ndarray) -> np.ndarray:
    return np.column_stack([points, np.ones(len(points), dtype=float)])


def _dominant(scene: trimesh.Scene):
    rows = []
    for node in scene.graph.nodes_geometry:
        matrix, geom_name = scene.graph.get(node)
        geom = scene.geometry[geom_name]
        if hasattr(geom, "vertices"):
            rows.append((str(node), str(geom_name), np.asarray(matrix, dtype=float), geom))
    if not rows:
        raise RuntimeError("GLB sin geometría editable")
    return max(rows, key=lambda x: len(x[3].vertices))


def sculpt_valleys(
    baseline: str,
    input_model: str,
    reference_sheet: str,
    config_path: str,
    output: str,
    report_path: str,
    strength: float = 0.75,
    length_scale: float = 1.0,
) -> dict[str, Any]:
    if not (0.20 <= strength <= 1.0):
        raise ValueError("strength debe estar en [0.20, 1.0]")
    if not (0.75 <= length_scale <= 1.25):
        raise ValueError("length_scale debe estar en [0.75, 1.25]")

    cfg = load_config(config_path)
    scale_mm = float(cfg.get("mesh_to_mm", 1000.0))
    _, baseline_mesh = load_scene(baseline, scale_mm)
    bounds = np.asarray(baseline_mesh.bounds, dtype=float) / scale_mm
    lo, hi = bounds[0], bounds[1]
    span = np.maximum(hi - lo, 1e-12)

    sheet = np.array(Image.open(reference_sheet).convert("RGB"))
    front = crop_norm(sheet, cfg["views"]["front"])
    ref_mask = person_mask(front)
    registration = registration_from_baseline(baseline_mesh, "front", ref_mask, cfg)
    hand_specs = [s for s in ((cfg.get("regions_by_view") or {}).get("hands") or []) if str(s.get("view", "front")) == "front"]
    finger_boxes = ((cfg.get("morph_regions") or {}).get("fingers") or {}).get("boxes") or []
    if len(hand_specs) < 2 or len(finger_boxes) < 2:
        raise RuntimeError("Se requieren dos ROIs de manos y dos cajas de fingers")

    targets: list[dict[str, Any]] = []
    for spec, morph_box in zip(hand_specs[:2], finger_boxes[:2]):
        box = [float(v) for v in spec["box"]]
        side = "left" if (box[0] + box[2]) / 2.0 < 0.5 else "right"
        roi = region_mask(ref_mask, box)
        ref = ref_mask & roi
        valleys = _valleys(ref, roi, side)
        mb = np.asarray(morph_box, dtype=float)
        for idx, valley in enumerate(valleys):
            x0, y0, x1, y1 = [float(v) for v in valley["bbox_px"]]
            _, nz_top = _pixel_to_norm(x0, y0, registration, lo, span, scale_mm)
            _, nz_bottom = _pixel_to_norm(x1 + 1.0, y1 + 1.0, registration, lo, span, scale_mm)
            za, zb = sorted((nz_bottom, nz_top))
            cz = (za + zb) * 0.5
            half_z = max((zb - za) * 0.5 * length_scale, 0.001)
            za = max(cz - half_z, float(mb[2]))
            zb = min(cz + half_z, float(mb[5]))
            if zb <= za:
                continue

            # _valleys reporta width_px sobre X (penetración horizontal del hueco)
            # y depth_px sobre Y de imagen (altura vertical). Para tallar la muesca
            # necesitamos width_px, convertido a distancia normalizada del modelo.
            gap_px = max(1.0, float(valley.get("width_px", x1 - x0 + 1.0)))
            gap_mm = gap_px / max(float(registration["scale"]), 1e-9)
            gap_norm_x = float((gap_mm / scale_mm) / max(float(span[0]), 1e-12))
            targets.append({
                "id": f"{side}_valley_{idx + 1}",
                "side": side,
                "z_range": [float(za), float(zb)],
                "gap_width_px": gap_px,
                "gap_width_normalized_x": gap_norm_x,
                "morph_box": [float(v) for v in mb],
                "source": valley,
            })

    scene = trimesh.load(str(input_model), force="scene")
    node_name, geom_name, node_matrix, geom = _dominant(scene)
    vertices_local = np.asarray(geom.vertices, dtype=float).copy()
    world = (node_matrix @ _to_h(vertices_local).T).T[:, :3]
    norm = (world - lo) / span
    updated = world.copy()
    moved = np.zeros(len(world), dtype=bool)
    per_target = []
    max_shift = 0.0

    for target in targets:
        side = target["side"]
        za, zb = target["z_range"]
        mb = np.asarray(target["morph_box"], dtype=float)
        cz = (za + zb) * 0.5
        half_z = max((zb - za) * 0.5, 1e-9)
        gap = float(target["gap_width_normalized_x"]) * float(strength)

        # Tomamos el borde ACTUAL del contorno a esta altura y tallamos hacia la
        # palma una profundidad derivada del ancho horizontal del valle de referencia.
        # Así no dependemos de una X absoluta registrada con otra silueta.
        in_yz = (
            (norm[:, 1] >= mb[1] - 0.01) & (norm[:, 1] <= mb[4] + 0.01) &
            (norm[:, 2] >= za) & (norm[:, 2] <= zb)
        )
        active = np.where(in_yz)[0]
        if not len(active):
            per_target.append({**target, "selected_vertices": 0, "max_shift_mm": 0.0, "reason": "no_vertices_in_yz_band"})
            continue

        xs = norm[active, 0]
        if side == "left":
            distal_x = float(xs.min())
            proximal_x = min(distal_x + gap, float(mb[3]))
            select = in_yz & (norm[:, 0] <= proximal_x) & (norm[:, 0] >= distal_x - 0.004)
            direction = proximal_x - norm[:, 0]
        else:
            distal_x = float(xs.max())
            proximal_x = max(distal_x - gap, float(mb[0]))
            select = in_yz & (norm[:, 0] >= proximal_x) & (norm[:, 0] <= distal_x + 0.004)
            direction = proximal_x - norm[:, 0]

        if not np.any(select):
            per_target.append({
                **target,
                "distal_x_current": distal_x,
                "proximal_x_target": proximal_x,
                "selected_vertices": 0,
                "max_shift_mm": 0.0,
                "reason": "no_boundary_vertices_selected",
            })
            continue

        zphase = np.clip(np.abs(norm[:, 2] - cz) / half_z, 0.0, 1.0)
        # Conserva cierre suave arriba/abajo del valle, máxima profundidad al centro.
        zfall = np.cos(zphase * math.pi * 0.5) ** 2
        delta_norm = direction * zfall * select.astype(float)
        delta_world = delta_norm * span[0]
        updated[:, 0] += delta_world
        changed = select & (np.abs(delta_world) > 1e-12)
        moved |= changed
        local_max = float(np.max(np.abs(delta_world[select])) * scale_mm)
        max_shift = max(max_shift, local_max)
        per_target.append({
            **target,
            "distal_x_current": distal_x,
            "proximal_x_target": proximal_x,
            "selected_vertices": int(select.sum()),
            "moved_vertices": int(changed.sum()),
            "max_shift_mm": local_max,
        })

    inv_node = np.linalg.inv(node_matrix)
    updated_local = (inv_node @ _to_h(updated).T).T[:, :3]
    updated_local[~moved] = vertices_local[~moved]
    outside_exact = bool(np.array_equal(updated_local[~moved], vertices_local[~moved]))
    geom.vertices = updated_local

    before_faces = int(len(geom.faces))
    before_vertices = int(len(vertices_local))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb")
    check_scene = trimesh.load(str(out), force="scene")
    _, _, _, check_geom = _dominant(check_scene)
    topology_counts_preserved = bool(len(check_geom.faces) == before_faces and len(check_geom.vertices) == before_vertices)
    mesh_integrity = bool(
        len(check_geom.vertices) and len(check_geom.faces)
        and np.isfinite(np.asarray(check_geom.vertices)).all()
        and topology_counts_preserved
    )

    result = {
        "mode": "finger_reference_valley_surface_sculpt_v2_relative_depth",
        "object": node_name,
        "geometry": geom_name,
        "reference_driven": True,
        "invented_finger_count": False,
        "reference_valley_count": len(targets),
        "targets": per_target,
        "strength": float(strength),
        "length_scale": float(length_scale),
        "moved_vertices": int(moved.sum()),
        "total_vertices": before_vertices,
        "max_shift_mm": max_shift,
        "outside_scope_exact": outside_exact,
        "topology_counts_preserved": topology_counts_preserved,
        "mesh_integrity": mesh_integrity,
        "promotion_allowed": False,
        "learning": "Forma muescas desde el borde actual usando profundidad horizontal derivada de width_px; no agrega/elimina caras, no suelda y no ejecuta booleanos.",
    }
    Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Esculpe valles de dedos desde referencia sin booleans")
    p.add_argument("--baseline", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--strength", type=float, default=0.75)
    p.add_argument("--length-scale", type=float, default=1.0)
    a = p.parse_args()
    r = sculpt_valleys(a.baseline, a.input, a.reference, a.config, a.output, a.report, a.strength, a.length_scale)
    print(json.dumps({
        "reference_valley_count": r["reference_valley_count"],
        "moved_vertices": r["moved_vertices"],
        "max_shift_mm": r["max_shift_mm"],
        "topology_counts_preserved": r["topology_counts_preserved"],
        "mesh_integrity": r["mesh_integrity"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
