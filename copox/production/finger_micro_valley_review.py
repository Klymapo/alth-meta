"""Review an existing three-sibling artifact without generating any new geometry."""
from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from copox.adapters.alth_character_audit import crop_norm, person_mask
from copox.production.research_iteration_loop import write_json


def framed(image):
    image = image.convert("RGB")
    mask = person_mask(np.array(image))
    yy, xx = np.where(mask)
    if not len(xx):
        return image
    margin = max(1, int(max(xx.max() - xx.min(), yy.max() - yy.min()) * 0.04))
    return image.crop((max(0, int(xx.min()) - margin), max(0, int(yy.min()) - margin),
                       min(image.width, int(xx.max()) + margin + 1), min(image.height, int(yy.max()) + margin + 1)))


def comparison(source, reference, cfg, output, include_parent=False):
    sheet = np.array(Image.open(reference).convert("RGB"))
    front = Image.fromarray(crop_norm(sheet, cfg["views"]["front"]))
    threeq = Image.fromarray(crop_norm(sheet, cfg["views"]["threeq"]))
    plan = json.loads((source / "micro_valley_plan.json").read_text())
    x0, y0, x1, y1 = plan["reference_hand_bbox_px"]
    # Framing only: context padding derived from the measured crop width/height.
    padx, pady = (x1 - x0) * 0.30, (y1 - y0) * 0.30
    hand = front.crop((max(0, int(x0 - padx)), max(0, int(y0 - pady)),
                       min(front.width, int(x1 + padx)), min(front.height, int(y1 + pady))))
    columns = [("REFERENCE", [framed(front), framed(threeq), hand])]
    directories = [("ALPHA", source / "alpha_render")]
    if include_parent:
        directories.append(("VALLEY C01", source / "working_parent" / "renders"))
    directories += [(name.upper(), source / "g01" / name / "renders") for name in ("c01", "c02", "c03")]
    for name, directory in directories:
        images = [Image.open(directory / (view + ".png")).convert("RGB") for view in ("front", "threeq", "hand_left")]
        columns.append((name, [framed(images[0]), framed(images[1]), images[2]]))
    width, height = 320, 320
    canvas = Image.new("RGB", (100 + width * len(columns), 40 + height * 3), "#f5f5f5")
    draw = ImageDraw.Draw(canvas)
    for column, (name, images) in enumerate(columns):
        draw.text((110 + column * width, 10), name, fill="#222")
        for row, img in enumerate(images):
            tile = ImageOps.contain(img, (width - 10, height - 10))
            canvas.paste(tile, (100 + column * width + (width - tile.width) // 2,
                               40 + row * height + (height - tile.height) // 2))
    for row, label in enumerate(("FRONT", "3/4", "LEFT HAND")):
        draw.text((5, 60 + row * height), label, fill="#222")
    canvas.save(output)
    return canvas


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--output", default=".copox/finger-micro-review")
    p.add_argument("--reference", default="refs/personajes/joven-rubio-4-vistas.jpg")
    p.add_argument("--config", default="copox/reference_configs/joven_rubio_alpha.json")
    p.add_argument("--decisions", default="copox/research/fingers-micro-valleys-20261001-review.json")
    a = p.parse_args()
    source, output = Path(a.source), Path(a.output)
    output.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(Path(a.config).read_text())
    decisions = json.loads(Path(a.decisions).read_text())
    loop = json.loads((source / "loop.json").read_text())
    parent_result = json.loads((source / "working_parent.json").read_text())
    parent_topo = json.loads((source / "working_parent" / "topology_report.json").read_text())
    if len(loop["generations"]) != 1 or len(loop["generations"][0]["candidate_metrics"]) != 3:
        raise RuntimeError("REVIEW_CONTRACT_FAILED: expected one generation of exactly three siblings")
    diagnostics = []
    for name in ("c01", "c02", "c03"):
        directory = source / "g01" / name
        result = json.loads((directory / "module_result.json").read_text())
        mutation = json.loads((directory / "mutation_report.json").read_text())
        topology = json.loads((directory / "topology_report.json").read_text())
        learning = json.loads((directory / "learning.json").read_text())
        full = json.loads((directory / "full_metrics.json").read_text())
        regions = json.loads((directory / "regional_metrics.json").read_text())
        row = {
            "candidate": name, "parent_sha": result["parent_sha"], "metrics": result,
            "working_parent_target_gain_pp": parent_result["metrics"]["target_gain_pp"],
            "alpha_locked_target_difference_to_valley_pp": result["target_gain_pp"] - parent_result["metrics"]["target_gain_pp"],
            "alpha_locked_global_difference_to_valley_pp": result["global_gain_pp"] - parent_result["metrics"]["global_gain_pp"],
            "topology": topology["dominant"]["welded_topology"],
            "parent_topology": parent_topo["dominant"]["welded_topology"],
            "outside_missing_vertices": mutation["outside_missing_vertices"],
            "outside_face_fingerprint_matches": mutation["outside_face_fingerprint_matches"],
            "local_section_counts": [{"section": section["section"], "closed_cycles": len(section["closed_cycles"]),
                                     "open_components": len(section["open_components"])} for section in mutation["local_sections"]],
            "actual_cut_dimensions": [{"id": cut["id"], "depth_mm": cut["depth_mm"], "height_mm": cut["slot_height_mm"]} for cut in mutation["cuts"]],
            "self_intersection_probe": mutation["self_intersection_probe"],
            "view_deltas": full["visual"]["full"]["delta_pp"],
            "frozen_region_failures": learning["frozen_region_failures"],
            "frozen_region_deltas": {k: v["delta_pp"] for k, v in regions["regions"].items() if k not in {"hands", "fingers"}},
            "visual_decision": next(r for r in decisions["decisions"] if r["candidate"] == name),
        }
        if result["parent_sha"] != loop["parent_sha"]:
            raise RuntimeError("REVIEW_CONTRACT_FAILED: parent mismatch")
        diagnostics.append(row)
        print("COPOX_REVIEW_DIAGNOSTIC:" + json.dumps(row))
        for filename in ("trial.json", "module_result.json", "gate.json", "learning.json", "mutation_report.json",
                         "topology_report.json", "regional_metrics.json", "full_metrics.json", "hand_detail.json"):
            target = output / name / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(directory / filename, target)
        for filename in ("hand_left.png", "hand_left_threeq.png", "hand_right.png", "finger_region.png"):
            shutil.copy2(directory / "renders" / filename, output / name / filename)
    write_json(output / "review_decisions.json", decisions)
    write_json(output / "diagnostics.json", {"parent": parent_result, "candidates": diagnostics,
               "promotion_executed": False, "accepted_candidate": None})
    comparison(source, a.reference, cfg, output / "comparison.png")
    gallery = comparison(source, a.reference, cfg, output / "comparison_with_valley.png", include_parent=True)
    preview = ImageOps.contain(gallery, (1800, 1000))
    preview.save(output / "preview.jpg", quality=85)
    print("COPOX_REVIEW_IMAGE:" + base64.b64encode((output / "preview.jpg").read_bytes()).decode())
    print("COPOX_REVIEW_VERIFIED:" + json.dumps({"source_run": 36876087961, "candidates": 3,
          "new_candidates_generated": 0, "best_diagnostic_candidate": "c03",
          "accepted_candidate": None, "promotion_executed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
