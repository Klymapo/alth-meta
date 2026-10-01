from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import traceback
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from copox.adapters.alth_character import ensure_runtime
from copox.adapters.alth_character_audit import audit as audit_full, crop_norm
from copox.adapters.finger_micro_valley_plan import plan_micro_valleys
from copox.adapters.hand_detail_probe import probe as hand_probe
from copox.adapters.mesh_topology_probe import probe as topology_probe
from copox.adapters.regional_reference_audit import audit_regions
from copox.production.finger_gap_trial import _read, _sha256
from copox.production.finger_valley_sculpt_trial import run_trial as valley_trial
from copox.production.module_gate import evaluate
from copox.production.research_gate import require_research
from copox.production.research_iteration_loop import run_generations, write_json

ALPHA_SHA = "ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b"
TECHNIQUE = "micro_valley_cut_local_sections"


def protect(alpha, parent=None, expected_parent=None):
    if _sha256(alpha) != ALPHA_SHA:
        raise RuntimeError("PROTECTED_BASELINE: SHA de Alpha incorrecto")
    if parent and _sha256(parent) != expected_parent:
        raise RuntimeError("PARENT_MISMATCH: working parent modificado")


def run_script(python, script, **kwargs):
    command = [python, str(Path("copox/adapters", script).resolve())]
    for name, value in kwargs.items():
        command += ["--" + name.replace("_", "-"), str(value)]
    subprocess.run(command, check=True, timeout=1800)


def render(python, model, config, directory):
    run_script(python, "finger_micro_valley_render.py", input=Path(model).resolve(),
               config=Path(config).resolve(), output_dir=directory.resolve())


def compare_sheet(root, reference, config):
    """True renders, not metric masks; consistent column/row labels."""
    cfg = _read(config)
    sheet = Image.open(reference).convert("RGB")
    ref_front = Image.fromarray(crop_norm(__import__("numpy").array(sheet), cfg["views"]["front"]))
    ref_threeq = Image.fromarray(crop_norm(__import__("numpy").array(sheet), cfg["views"]["threeq"]))
    # Image ROI is anchored to the detected person's bounding box, as in region_mask.
    from copox.adapters.alth_character_audit import person_mask, region_mask
    import numpy as np
    roi = region_mask(person_mask(np.array(ref_front)), cfg["regions_by_view"]["hands"][0]["box"])
    yy, xx = np.where(roi)
    ref_hand = ref_front.crop((int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1))
    columns = [("REFERENCE", [ref_front, ref_threeq, ref_hand]),
               ("ALPHA", [Image.open(root / "alpha_render" / f"{view}.png") for view in ("front", "threeq", "hand_left")])]
    for candidate in ("c01", "c02", "c03"):
        directory = root / "g01" / candidate / "renders"
        images = []
        for view in ("front", "threeq", "hand_left"):
            path = directory / (view + ".png")
            images.append(Image.open(path) if path.exists() else Image.new("RGB", (400, 400), "#efe6e6"))
        columns.append((candidate.upper(), images))
    cell, label = 300, 30
    canvas = Image.new("RGB", (cell * 5 + 100, (cell + label) * 3 + 45), "#f5f5f5")
    draw = ImageDraw.Draw(canvas)
    for column, (name, images) in enumerate(columns):
        draw.text((110 + column * cell, 10), name, fill="#222")
        for row, img in enumerate(images):
            tile = ImageOps.contain(img.convert("RGB"), (cell - 10, cell - 10))
            canvas.paste(tile, (100 + column * cell + (cell - tile.width) // 2, 45 + row * (cell + label) + (cell - tile.height) // 2))
    for row, name in enumerate(("FRONT", "3/4", "LEFT HAND")):
        draw.text((5, 65 + row * (cell + label)), name, fill="#222")
    canvas.save(root / "comparison.png")
    preview = ImageOps.contain(canvas, (1400, 1000))
    preview.save(root / "comparison_preview.jpg", quality=80)
    print("COPOX_REVIEW_IMAGE:" + base64.b64encode((root / "comparison_preview.jpg").read_bytes()).decode())


def audit_candidate(root, params, parent_sha, *, alpha, parent, reference, config, policy_path, plan_path, brief, python):
    root.mkdir(parents=True, exist_ok=True)
    candidate = root.name
    model = root / "model.glb"
    protect(alpha, parent, parent_sha)
    require_research(brief, "fingers", output=root / "research_gate.json", technique=TECHNIQUE)
    mutation_report = root / "mutation_report.json"
    try:
        run_script(python, "finger_micro_valley_edit.py", input=Path(parent).resolve(), alpha=Path(alpha).resolve(),
                   plan=plan_path.resolve(), research=Path(brief).resolve(), depth_scale=params["depth_scale"],
                   output=model.resolve(), report=mutation_report.resolve())
        mutation = _read(mutation_report)
        regional = audit_regions(alpha, str(model), reference, config, str(root / "regional_metrics.json"), str(root / "evidence"))
        parent_regions = audit_regions(parent, str(model), reference, config, str(root / "parent_regional_metrics.json"), str(root / "parent_evidence"))
        full = audit_full(alpha, str(model), reference, "hands,fingers", config, None, str(root / "full_metrics.json"), str(root / "full_evidence"))
        parent_full = audit_full(parent, str(model), reference, "hands,fingers", config, None, str(root / "parent_full_metrics.json"), str(root / "parent_full_evidence"))
        detail = hand_probe(str(model), reference, config, str(root / "hand_detail.json"), str(root / "hand_detail_evidence"))
        topo = topology_probe(str(model), str(root / "topology_report.json"))
        parent_topo = _read(Path(parent).parent / "topology_report.json")
        render(python, model, config, root / "renders")
        protect(alpha, parent, parent_sha)
        reference_valleys = detail["summary"]["reference_valleys"]
        model_valleys = detail["summary"]["model_valleys"]
        semantic = bool(detail["summary"]["definition_match"] and reference_valleys == model_valleys == {"left": 2, "right": 0})
        before = parent_topo["dominant"]["welded_topology"]
        after = topo["dominant"]["welded_topology"]
        topology_ok = bool(topo["dominant"]["valid"] and after["degenerate_faces"] == 0 and
                           after["nonmanifold_edges"] <= before["nonmanifold_edges"] and
                           after["boundary_edges"] <= before["boundary_edges"])
        frozen = [{"region": region, "delta_pp": data["delta_pp"]}
                  for region, data in regional["regions"].items()
                  if region not in {"fingers", "hands"} and float(data["delta_pp"]) < -0.20]
        parent_frozen = [{"region": region, "delta_pp": data["delta_pp"]}
                         for region, data in parent_regions["regions"].items()
                         if region not in {"fingers", "hands"} and float(data["delta_pp"]) < -0.20]
        target = float(regional["regions"]["fingers"]["delta_pp"])
        parent_target = float(parent_regions["regions"]["fingers"]["delta_pp"])
        global_gain = float(full["visual"]["weighted_gain_pp"])
        parent_global = float(parent_full["visual"]["weighted_gain_pp"])
        worst = min(float(x) for x in full["visual"]["full"]["delta_pp"].values())
        parent_worst = min(float(x) for x in parent_full["visual"]["full"]["delta_pp"].values())
        # Declared tolerances, not measured claims. Preserve Valley's strong structural advantage.
        valley_advantage = parent_target >= -0.20 and parent_global >= -0.05 and parent_worst >= -0.10
        uv_ok = mutation["uv_layers_preserved"] and topo["dominant"]["uv"]["available"]
        mesh_ok = bool(mutation["mesh_integrity"] and topology_ok and uv_ok)
        regression_ok = bool(not frozen and not parent_frozen and worst >= -0.10 and global_gain >= 0.05 and valley_advantage)
        files = ["model.glb", "topology_report.json", "regional_metrics.json", "full_metrics.json", "hand_detail.json"]
        files += ["renders/" + name + ".png" for name in ("front", "side", "back", "threeq", "hand_left", "hand_right", "finger_region")]
        evidence_complete = all((root / path).is_file() and (root / path).stat().st_size > 0 for path in files)
        labels = ["hand_left", "hand_right", "finger_detail", "topology_report", "learning"]
        flags = ([] if semantic else ["mitten_shape"]) + ([] if mesh_ok else ["finger_merge_regression"])
        learning = {"module": "fingers", "technique": TECHNIQUE, "parent_sha": parent_sha,
                    "research_id": "fingers-micro-valleys-20261001", "parameters": params,
                    "reference_valleys": reference_valleys, "model_valleys": model_valleys,
                    "frozen_region_failures": frozen, "parent_frozen_region_failures": parent_frozen,
                    "valley_structural_advantage_preserved": valley_advantage,
                    "local_sections_closed": mutation["loops_ready"], "bridge_ready": mutation["bridge_ready"],
                    "rig_ready": False, "visual_review": "PENDING",
                    "next_hypothesis": "Si cortes no conservan silueta/topología, sustituir sólo el patch de raíz de valles por quads emparejados al borde medido; investigar antes de bridge.",
                    "promotion_executed": False}
        write_json(root / "learning.json", learning)
        result = {"module": "fingers", "baseline_sha256": ALPHA_SHA, "parent_sha": parent_sha,
                  "mesh_integrity": mesh_ok, "scope_safe": bool(mutation["outside_scope_exact"]),
                  "regression_ok": regression_ok, "evidence_complete": evidence_complete,
                  "semantic_ready": semantic, "target_gain_pp": target, "global_gain_pp": global_gain,
                  "worst_view_delta_pp": worst, "evidence": labels, "flags": flags, "params": params,
                  "reference_valleys": reference_valleys, "model_valleys": model_valleys,
                  "parent_target_delta_pp": parent_target, "parent_global_delta_pp": parent_global,
                  "parent_worst_view_delta_pp": parent_worst, "local_loops_ready": mutation["loops_ready"],
                  "valley_structural_advantage_preserved": valley_advantage}
        strict_policy = _read(policy_path)
        strict_policy["min_global_gain_pp"] = 0.05
        gate = evaluate(strict_policy, result, baseline_model=alpha)
        gate["checks"].update({"valley_structural_advantage": valley_advantage,
                              "local_loops_ready": mutation["loops_ready"], "exact_valley_counts": semantic})
        gate["reasons"] += [name for name in ("valley_structural_advantage", "local_loops_ready", "exact_valley_counts") if not gate["checks"][name]]
        passed = all(gate["checks"].values())
        gate.update(audit_passed=passed, promotion_allowed=False, promotion_executed=False, visual_review="PENDING")
        write_json(root / "module_result.json", result)
        write_json(root / "gate.json", gate)
        trial = {"candidate": candidate, "parent_sha": parent_sha, "alpha_sha": ALPHA_SHA,
                 "research_id": learning["research_id"], "parameters": params, "result": result,
                 "gate": gate, "learning": learning, "mutation": mutation,
                 "promotion_executed": False, "visual_review": "PENDING"}
        write_json(root / "trial.json", trial)
        row = {**result, "candidate": candidate, "audit_passed": passed, "reasons": gate["reasons"]}
    except Exception as exc:
        protect(alpha, parent, parent_sha)
        error = {"status": "ERROR", "error": str(exc), "traceback": traceback.format_exc()}
        result = {"module": "fingers", "baseline_sha256": ALPHA_SHA, "parent_sha": parent_sha,
                  "mesh_integrity": False, "scope_safe": False, "regression_ok": False,
                  "evidence_complete": False, "semantic_ready": False, "target_gain_pp": None,
                  "global_gain_pp": None, "worst_view_delta_pp": None}
        gate = {"audit_passed": False, "promotion_allowed": False, "promotion_executed": False,
                "reasons": ["candidate_execution_error"], "checks": {k: False for k in ("mesh_integrity", "scope_safe", "regression_ok", "evidence_complete", "semantic_ready")}}
        for filename, data in (("module_result.json", result), ("gate.json", gate), ("learning.json", error),
                               ("trial.json", {**error, "parent_sha": parent_sha, "params": params, "promotion_executed": False})):
            write_json(root / filename, data)
        row = {**result, "candidate": candidate, "audit_passed": False, "parent_target_delta_pp": None, "reasons": gate["reasons"],
               "target_gain_pp": None, "global_gain_pp": None}
    print("COPOX_CANDIDATE:" + json.dumps(row, ensure_ascii=False))
    return row


def main():
    p = argparse.ArgumentParser(description="One researched generation, exactly three siblings, no promotion")
    p.add_argument("--alpha", default="assets/joven_rubio/theo_alpha.glb")
    p.add_argument("--reference", default="refs/personajes/joven-rubio-4-vistas.jpg")
    p.add_argument("--config", default="copox/reference_configs/joven_rubio_alpha.json")
    p.add_argument("--policy", default="copox/production/theo_m5_policy.json")
    p.add_argument("--research", default="copox/research/fingers-micro-valleys-20261001.json")
    p.add_argument("--output", default=".copox/finger-micro-valleys")
    a = p.parse_args()
    root = Path(a.output)
    root.mkdir(parents=True, exist_ok=True)
    protect(a.alpha)
    try:
        for technique in ("semantic_finish", "valley_surface_sculpt", TECHNIQUE):
            require_research(a.research, "fingers", output=root / ("research_" + technique + ".json"), technique=technique)
        python = ensure_runtime(Path.cwd())
        # Reproduce measured Valley Sculpt c01 once; never overwrite or promote it.
        parent_dir = root / "working_parent"
        valley = valley_trial(a.alpha, a.reference, a.config, a.policy, 1, str(parent_dir))
        parent = str(parent_dir / "model.glb")
        parent_sha = _sha256(parent)
        write_json(root / "working_parent.json", {"accepted_baseline_sha": ALPHA_SHA, "working_parent_sha": parent_sha,
                   "origin": "Valley Sculpt c01; trial parent only, not promoted or accepted as new baseline",
                   "metrics": valley["result"], "promotion_executed": False})
        plan_path = root / "micro_valley_plan.json"
        plan_micro_valleys(parent, a.reference, a.config, plan_path)
        render(python, a.alpha, a.config, root / "alpha_render")
        render(python, parent, a.config, parent_dir / "renders")
        spec = {"brief": a.research, "technique": TECHNIQUE,
                "parameters": [{"depth_scale": scale} for scale in (0.75, 1.0, 1.25)],
                "next_hypothesis": "Validar quads locales en raíces de valles sin sustituir la mano; bridge y flexión sólo con research específico."}
        result = run_generations(parent_sha=parent_sha, module="fingers", specs=[spec], output=root,
            mutate_and_audit=lambda directory, params, sha: audit_candidate(directory, params, sha, alpha=a.alpha,
                parent=parent, reference=a.reference, config=a.config, policy_path=a.policy,
                plan_path=plan_path, brief=a.research, python=python), max_generations=3)
        protect(a.alpha, parent, parent_sha)
        compare_sheet(root, a.reference, a.config)
        write_json(root / "summary.json", result)
        print("COPOX_SUMMARY:" + json.dumps({k: v for k, v in result.items() if k != "generations"}))
        return 0
    except Exception as exc:
        protect(a.alpha)
        status = "RESEARCH_REQUIRED" if "RESEARCH_REQUIRED" in str(exc) else "PREPARATION_FAILED"
        write_json(root / "summary.json", {"status": status, "error": str(exc), "promotion_executed": False})
        print(json.dumps({"status": status, "error": str(exc)}))
        return 9


if __name__ == "__main__":
    raise SystemExit(main())
