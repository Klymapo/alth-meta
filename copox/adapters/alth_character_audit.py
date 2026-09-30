from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import scipy.ndimage as ndi
import trimesh
from PIL import Image, ImageDraw


DEFAULT_CONFIG: dict[str, Any] = {
    "mesh_to_mm": 1000.0,
    "views": {
        "front": [0.0, 0.0, 0.5, 0.5],
        "side": [0.5, 0.0, 1.0, 0.5],
        "back": [0.0, 0.5, 0.5, 1.0],
        "threeq": [0.5, 0.5, 1.0, 1.0],
    },
    "weights": {"front": 0.4, "side": 0.3, "back": 0.15, "threeq": 0.15},
    "regions_front": {
        "hair": [0.18, 0.00, 0.82, 0.33],
        "face": [0.28, 0.17, 0.72, 0.48],
        "torso": [0.34, 0.40, 0.66, 0.69],
        "arms_hands_left": [0.00, 0.39, 0.36, 0.63],
        "arms_hands_right": [0.64, 0.39, 1.00, 0.63],
        "legs_feet": [0.33, 0.64, 0.67, 1.00],
    },
    "approval": {
        "weighted_gain_min_pp": 0.05,
        "max_single_view_drop_pp": -0.10,
        "relevant_region_gain_min_pp": 0.10,
        "relevant_visible_delta_min_pct": 0.50,
        "landmark_error_improvement_min_headwidth_pct": 0.15,
        "freeze_tolerance_pp": -0.20,
    },
    "landmarks": {
        "head_width_px": 60.0,
        "reference": {},
        "model_name_contains": {},
    },
}


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    return deep_merge(DEFAULT_CONFIG, json.loads(Path(path).read_text(encoding="utf-8")))


def person_mask(arr: np.ndarray, threshold: float = 40.0) -> np.ndarray:
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]], axis=0)
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(arr.astype(float) - bg.astype(float), axis=2)
    mask = dist > threshold
    labels, count = ndi.label(mask)
    if count == 0:
        return mask
    sizes = ndi.sum(mask, labels, range(1, count + 1))
    largest = int(np.argmax(sizes)) + 1
    return ndi.binary_fill_holes(labels == largest)


def crop_norm(image: np.ndarray, box: list[float]) -> np.ndarray:
    h, w = image.shape[:2]
    x0, y0, x1, y1 = box
    return image[int(round(y0 * h)): int(round(y1 * h)), int(round(x0 * w)): int(round(x1 * w))]


def load_scene(path: str, scale: float) -> tuple[trimesh.Scene, trimesh.Trimesh]:
    scene = trimesh.load(path, force="scene")
    dumped = scene.dump(concatenate=True)
    if isinstance(dumped, list):
        mesh = trimesh.util.concatenate(dumped)
    else:
        mesh = dumped
    mesh = mesh.copy()
    mesh.vertices *= scale
    return scene, mesh


def bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if not len(xs):
        raise ValueError("La referencia no contiene una silueta detectable")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def raster_silhouette(mesh: trimesh.Trimesh, view: str, out_shape: tuple[int, int], ref_mask: np.ndarray) -> np.ndarray:
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    if view == "front":
        horizontal = vertices[:, 0]
    elif view == "side":
        horizontal = vertices[:, 1]
    elif view == "back":
        horizontal = -vertices[:, 0]
    elif view == "threeq":
        angle = np.deg2rad(45.0)
        horizontal = vertices[:, 0] * np.cos(angle) + vertices[:, 1] * np.sin(angle)
    else:
        raise ValueError(f"Vista no soportada: {view}")
    z = vertices[:, 2]
    x0, y0, x1, y1 = bbox(ref_mask)
    z_span = max(1e-6, float(z.max() - z.min()))
    scale = (y1 - y0 + 1) / z_span
    center_x = (x0 + x1) / 2
    center_h = (float(horizontal.min()) + float(horizontal.max())) / 2
    px = center_x + (horizontal - center_h) * scale
    py = y1 - (z - float(z.min())) * scale
    canvas = Image.new("1", (out_shape[1], out_shape[0]), 0)
    draw = ImageDraw.Draw(canvas)
    for tri in faces:
        draw.polygon([(float(px[i]), float(py[i])) for i in tri], fill=1)
    return np.array(canvas, dtype=bool)


def iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / max(1, (a | b).sum()))


def xor_ratio(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.logical_xor(a, b).sum() / max(1, np.logical_or(a, b).sum()))


def region_mask(ref_mask: np.ndarray, norm: list[float]) -> np.ndarray:
    x0, y0, x1, y1 = bbox(ref_mask)
    rx0 = x0 + int(round(norm[0] * (x1 - x0 + 1)))
    ry0 = y0 + int(round(norm[1] * (y1 - y0 + 1)))
    rx1 = x0 + int(round(norm[2] * (x1 - x0 + 1)))
    ry1 = y0 + int(round(norm[3] * (y1 - y0 + 1)))
    out = np.zeros_like(ref_mask, dtype=bool)
    out[max(0, ry0):min(out.shape[0], ry1), max(0, rx0):min(out.shape[1], rx1)] = True
    return out


def project_front(point_mm: np.ndarray, mesh: trimesh.Trimesh, ref_mask: np.ndarray) -> list[float]:
    vertices = np.asarray(mesh.vertices)
    x0, y0, x1, y1 = bbox(ref_mask)
    z_span = max(1e-6, float(vertices[:, 2].max() - vertices[:, 2].min()))
    scale = (y1 - y0 + 1) / z_span
    center_x = (x0 + x1) / 2
    center_mesh_x = (float(vertices[:, 0].min()) + float(vertices[:, 0].max())) / 2
    px = center_x + (float(point_mm[0]) - center_mesh_x) * scale
    py = y1 - (float(point_mm[2]) - float(vertices[:, 2].min())) * scale
    return [float(px), float(py)]


def scene_landmarks(scene: trimesh.Scene, mesh: trimesh.Trimesh, ref_mask: np.ndarray, cfg: dict[str, Any]) -> dict[str, list[float]]:
    patterns = cfg.get("landmarks", {}).get("model_name_contains", {})
    if not patterns:
        return {}
    result: dict[str, list[float]] = {}
    scale = float(cfg.get("mesh_to_mm", 1000.0))
    for landmark, fragments in patterns.items():
        fragments = [str(x).lower() for x in (fragments if isinstance(fragments, list) else [fragments])]
        centers: list[np.ndarray] = []
        for node_name in scene.graph.nodes_geometry:
            transform, geometry_name = scene.graph.get(node_name)
            haystack = f"{node_name} {geometry_name}".lower()
            if not any(fragment in haystack for fragment in fragments):
                continue
            geometry = scene.geometry[geometry_name]
            center_local = np.append(np.asarray(geometry.bounding_box.centroid), 1.0)
            center_world = np.asarray(transform) @ center_local
            centers.append(center_world[:3] * scale)
        if centers:
            result[str(landmark)] = project_front(np.mean(np.vstack(centers), axis=0), mesh, ref_mask)
    return result


def landmark_metrics(model: dict[str, list[float]], reference: dict[str, list[float]], head_width_px: float) -> tuple[dict[str, float], float | None]:
    errors: dict[str, float] = {}
    for key, ref in reference.items():
        if key in model:
            errors[key] = float(np.linalg.norm(np.asarray(model[key]) - np.asarray(ref)) / head_width_px * 100.0)
    return errors, (float(np.mean(list(errors.values()))) if errors else None)


def save_overlay(path: Path, reference: np.ndarray, baseline: np.ndarray, candidate: np.ndarray) -> None:
    ref_rgb = np.array(reference, copy=True)
    out = ref_rgb.astype(np.float32)
    base_only = baseline & ~candidate
    cand_only = candidate & ~baseline
    overlap = candidate & baseline
    out[base_only] = 0.55 * out[base_only] + 0.45 * np.array([255, 70, 70])
    out[cand_only] = 0.55 * out[cand_only] + 0.45 * np.array([70, 210, 110])
    out[overlap] = 0.8 * out[overlap] + 0.2 * np.array([80, 140, 255])
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(path)


def audit(prev_glb: str, curr_glb: str, reference_sheet: str, focus: str, config_path: str | None,
          technical_report: str | None, output: str, evidence_dir: str) -> dict[str, Any]:
    cfg = load_config(config_path)
    scale = float(cfg.get("mesh_to_mm", 1000.0))
    prev_scene, prev_mesh = load_scene(prev_glb, scale)
    curr_scene, curr_mesh = load_scene(curr_glb, scale)
    reference = np.array(Image.open(reference_sheet).convert("RGB"))

    refs = {name: crop_norm(reference, box) for name, box in cfg["views"].items()}
    ref_masks = {name: person_mask(img) for name, img in refs.items()}
    masks: dict[tuple[str, str], np.ndarray] = {}
    scores: dict[str, dict[str, float]] = {"prev": {}, "curr": {}}
    for label, mesh in (("prev", prev_mesh), ("curr", curr_mesh)):
        for view in ("front", "side", "back", "threeq"):
            mask = raster_silhouette(mesh, view, refs[view].shape[:2], ref_masks[view])
            masks[(label, view)] = mask
            scores[label][view] = iou(mask, ref_masks[view])
        scores[label]["weighted"] = sum(scores[label][view] * float(cfg["weights"].get(view, 0.0)) for view in ("front", "side", "back", "threeq"))

    deltas = {key: (scores["curr"][key] - scores["prev"][key]) * 100.0 for key in scores["curr"]}
    regions: dict[str, dict[str, float]] = {}
    for name, norm in cfg["regions_front"].items():
        region = region_mask(ref_masks["front"], norm)
        prev_iou = iou(masks[("prev", "front")] & region, ref_masks["front"] & region)
        curr_iou = iou(masks[("curr", "front")] & region, ref_masks["front"] & region)
        regions[name] = {
            "prev_iou": prev_iou,
            "curr_iou": curr_iou,
            "delta_pp": (curr_iou - prev_iou) * 100.0,
            "visible_delta_pct": xor_ratio(masks[("prev", "front")] & region, masks[("curr", "front")] & region) * 100.0,
        }
    arms = [regions[x] for x in ("arms_hands_left", "arms_hands_right") if x in regions]
    if arms:
        regions["arms_hands"] = {
            key: float(np.mean([x[key] for x in arms])) for key in ("prev_iou", "curr_iou", "delta_pp", "visible_delta_pct")
        }

    tokens = {x.strip().lower() for x in focus.replace("+", ",").replace("/", ",").split(",") if x.strip()}
    relevant: list[str] = []
    if "hair" in tokens:
        relevant.append("hair")
    if "face" in tokens or "head" in tokens:
        relevant.append("face")
    if "arms" in tokens or "hands" in tokens:
        relevant.append("arms_hands")
    if "legs" in tokens or "feet" in tokens or "shoes" in tokens:
        relevant.append("legs_feet")
    if not relevant:
        relevant = [x for x in ("face", "hair") if x in regions]

    rel_gain = float(np.mean([regions[x]["delta_pp"] for x in relevant if x in regions])) if relevant else 0.0
    rel_visible = float(np.mean([regions[x]["visible_delta_pct"] for x in relevant if x in regions])) if relevant else 0.0

    lm_cfg = cfg.get("landmarks", {})
    reference_landmarks = lm_cfg.get("reference", {})
    prev_landmarks = scene_landmarks(prev_scene, prev_mesh, ref_masks["front"], cfg)
    curr_landmarks = scene_landmarks(curr_scene, curr_mesh, ref_masks["front"], cfg)
    _, prev_lm_mean = landmark_metrics(prev_landmarks, reference_landmarks, float(lm_cfg.get("head_width_px", 60.0)))
    _, curr_lm_mean = landmark_metrics(curr_landmarks, reference_landmarks, float(lm_cfg.get("head_width_px", 60.0)))
    lm_improve = (prev_lm_mean - curr_lm_mean) if prev_lm_mean is not None and curr_lm_mean is not None else None

    approval = cfg["approval"]
    max_drop = min(deltas[view] for view in ("front", "side", "back", "threeq"))
    frozen: list[str] = []
    for region_name in ("torso", "arms_hands", "legs_feet"):
        if region_name not in relevant and region_name in regions and regions[region_name]["delta_pp"] < float(approval["freeze_tolerance_pp"]):
            frozen.append(region_name)

    face_ok = True
    if "face" in regions:
        face_ok = regions["face"]["delta_pp"] >= 0.0
        if lm_improve is not None:
            face_ok = face_ok and lm_improve >= float(approval["landmark_error_improvement_min_headwidth_pct"])

    unresolved: list[str] = []
    if "hair" in relevant and "hair" in regions and regions["hair"]["delta_pp"] < float(approval["relevant_region_gain_min_pp"]):
        unresolved.append("hair")
    if "face" in relevant and not face_ok:
        unresolved.append("face")
    if deltas["side"] < 0.0:
        unresolved.append("profile")
    learning_action = "REUSE" if not unresolved else ("CREATE_RESEARCH" if len(unresolved) >= 2 else "EXTEND")

    technical_ok = False
    if technical_report and Path(technical_report).exists():
        technical_data = json.loads(Path(technical_report).read_text(encoding="utf-8"))
        technical_ok = bool((technical_data.get("verificacion") or {}).get("ok"))

    mesh_integrity = bool(len(curr_mesh.vertices) > 0 and len(curr_mesh.faces) > 0 and np.isfinite(curr_mesh.vertices).all())
    metrics = {
        "technical": {
            "mesh_integrity": mesh_integrity,
            "spec_compliance": technical_ok,
        },
        "visual": {
            "full": {"baseline": scores["prev"], "candidate": scores["curr"], "delta_pp": deltas},
            "weighted_gain_pp": deltas["weighted"],
            "relevant_region_gain_pp": rel_gain,
            "visible_delta_pct": rel_visible,
            "organic_silhouette_ok": deltas["side"] >= 0.0 and deltas["threeq"] >= 0.0,
            "anatomy_coherence_ok": max_drop >= float(approval["max_single_view_drop_pp"]) and not frozen,
            "landmark_improvement_headwidth_pct": lm_improve,
        },
        "regions": {
            "head_ok": regions.get("face", {}).get("delta_pp", 0.0) >= 0.0,
            "face_ok": face_ok,
            "hair_ok": regions.get("hair", {}).get("delta_pp", 0.0) >= float(approval["relevant_region_gain_min_pp"]),
            "arms_ok": regions.get("arms_hands", {}).get("delta_pp", 0.0) >= 0.0,
            "legs_ok": regions.get("legs_feet", {}).get("delta_pp", 0.0) >= 0.0,
            "footwear_ok": regions.get("legs_feet", {}).get("delta_pp", 0.0) >= 0.0,
            "detail": regions,
        },
        "regression": {"frozen_regions_ok": not frozen, "failed_regions": frozen},
        "learning": {"ready_to_promote": not unresolved, "action": learning_action, "unresolved": unresolved},
        "error_budget": sorted(
            [
                {"area": name, "error_score": (1.0 - values["curr_iou"]) * 100.0, "curr_iou": values["curr_iou"]}
                for name, values in regions.items() if name in {"hair", "face", "torso", "arms_hands", "legs_feet"}
            ],
            key=lambda x: x["error_score"], reverse=True,
        ),
        "focus": sorted(tokens),
        "landmarks": {"baseline": prev_landmarks, "candidate": curr_landmarks, "reference": reference_landmarks},
    }

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    evidence = Path(evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    for view in ("front", "side", "back", "threeq"):
        save_overlay(evidence / f"overlay_{view}.png", refs[view], masks[("prev", view)], masks[("curr", view)])
    return metrics


def main() -> int:
    p = argparse.ArgumentParser(description="Audit V2 configurable para personajes ALTH")
    p.add_argument("--prev", required=True)
    p.add_argument("--curr", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--focus", default="head,face,hair")
    p.add_argument("--config")
    p.add_argument("--technical-report")
    p.add_argument("--output", required=True)
    p.add_argument("--evidence-dir", required=True)
    args = p.parse_args()
    metrics = audit(args.prev, args.curr, args.reference, args.focus, args.config, args.technical_report, args.output, args.evidence_dir)
    print(json.dumps({"weighted_gain_pp": metrics["visual"]["weighted_gain_pp"], "unresolved": metrics["learning"]["unresolved"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
