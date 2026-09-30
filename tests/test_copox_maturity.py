import json
import tempfile
import unittest
from pathlib import Path

from copox.engine import run_campaign
from copox.maturity import assess_coverage, compute_level


class CopoxMaturityTests(unittest.TestCase):
    def test_levels_are_computed_from_real_capabilities(self):
        self.assertEqual(compute_level({}), "M0")
        self.assertEqual(compute_level({"evidence": True}), "M1")
        self.assertEqual(compute_level({"evidence": True, "auditor": True}), "M2")
        self.assertEqual(compute_level({"evidence": True, "auditor": True, "mutator": True}), "M3")
        self.assertEqual(compute_level({"evidence": True, "auditor": True, "mutator": True, "learning": True, "regression": True}), "M4")
        self.assertEqual(compute_level({"evidence": True, "auditor": True, "mutator": True, "learning": True, "regression": True, "persistence": True, "loop_gate": True}), "M5")

    def test_every_model_area_is_registered(self):
        result = assess_coverage("copox/maturity/theo.json", min_level="M4", critical_only=True)
        ids = {m["id"] for m in result["modules"]}
        expected = {
            "whole_body_silhouette", "global_proportions", "head_shape", "hair", "ears", "face", "neck",
            "torso", "shoulders", "arms", "elbows_forearms", "hands", "fingers", "pelvis_hips", "legs",
            "knees", "ankles", "feet_footwear", "materials_colors", "mesh_topology", "orientation", "rig_readiness",
            "facial_animation_readiness",
        }
        self.assertEqual(ids, expected)
        self.assertFalse(result["ready"])
        blockers = {m["id"] for m in result["blockers"]}
        # Las regiones anatómicas validadas ya deben estar en M4 o M5.
        for mature in ("head_shape", "ears", "hands", "fingers", "legs", "feet_footwear"):
            self.assertNotIn(mature, blockers)
        # El loop completo sigue cerrado por las áreas técnicas/globales todavía inmaduras.
        for blocked in ("whole_body_silhouette", "global_proportions", "materials_colors", "mesh_topology", "orientation", "rig_readiness", "facial_animation_readiness"):
            self.assertIn(blocked, blockers)
        hair = next(m for m in result["modules"] if m["id"] == "hair")
        self.assertEqual(hair["computed_level"], "M5")
        fingers = next(m for m in result["modules"] if m["id"] == "fingers")
        self.assertEqual(fingers["computed_level"], "M4")

    def test_global_module_catalog_also_has_maturity(self):
        result = assess_coverage("copox/maturity/modules.json", min_level="M4", critical_only=False)
        ids = {m["id"] for m in result["modules"]}
        self.assertEqual(ids, {"alth_character_alpha", "alth_character_legacy", "alth_asset", "rig", "texture", "godot_ui", "godot_script", "smoke"})
        self.assertFalse(result["ready"])
        self.assertEqual(next(m for m in result["modules"] if m["id"] == "alth_character_alpha")["computed_level"], "M5")

    def test_model_loop_is_blocked_before_candidates(self):
        with tempfile.TemporaryDirectory(dir=".") as td:
            code = run_campaign("copox/cassettes/examples/theo.json", output_root=td)
            self.assertEqual(code, 4)
            manifests = list(Path(td).rglob("manifest.json"))
            self.assertEqual(len(manifests), 1)
            data = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "MATURITY_BLOCKED")
            self.assertEqual(data["candidates"], [])
            self.assertTrue((manifests[0].parent / "maturity.json").exists())


if __name__ == "__main__":
    unittest.main()
