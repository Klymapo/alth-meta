import json
import tempfile
import unittest
from pathlib import Path

from copox.engine import run_campaign
from copox.maturity import assess_coverage, compute_level


POLICY = "copox/production/theo_m5_policy.json"


class CopoxMaturityTests(unittest.TestCase):
    def test_levels_are_computed_from_real_capabilities(self):
        self.assertEqual(compute_level({}), "M0")
        self.assertEqual(compute_level({"evidence": True}), "M1")
        self.assertEqual(compute_level({"evidence": True, "auditor": True}), "M2")
        self.assertEqual(compute_level({"evidence": True, "auditor": True, "mutator": True}), "M3")
        self.assertEqual(compute_level({"evidence": True, "auditor": True, "mutator": True, "learning": True, "regression": True}), "M4")
        self.assertEqual(compute_level({"evidence": True, "auditor": True, "mutator": True, "learning": True, "regression": True, "persistence": True, "loop_gate": True}), "M5")

    def test_every_model_area_is_registered(self):
        raw = assess_coverage("copox/maturity/theo.json", min_level="M4", critical_only=True)
        ids = {m["id"] for m in raw["modules"]}
        expected = {
            "whole_body_silhouette", "global_proportions", "head_shape", "hair", "ears", "face", "neck",
            "torso", "shoulders", "arms", "elbows_forearms", "hands", "fingers", "pelvis_hips", "legs",
            "knees", "ankles", "feet_footwear", "materials_colors", "mesh_topology", "orientation", "rig_readiness",
            "facial_animation_readiness",
        }
        self.assertEqual(ids, expected)
        self.assertTrue(raw["ready"])
        self.assertEqual(raw["blockers"], [])
        self.assertFalse(assess_coverage("copox/maturity/theo.json", min_level="M5")["ready"])

        product = assess_coverage("copox/maturity/theo.json", min_level="M5", production_policy=POLICY)
        self.assertTrue(product["ready"], product["blockers"])
        self.assertEqual(product["summary"]["M5"], 23)
        self.assertEqual(product["learning_backlog"], [])

    def test_global_module_catalog_also_has_maturity(self):
        result = assess_coverage("copox/maturity/modules.json", min_level="M4", critical_only=False)
        ids = {m["id"] for m in result["modules"]}
        self.assertEqual(ids, {"alth_character_alpha", "alth_character_legacy", "alth_asset", "rig", "texture", "godot_ui", "godot_script", "smoke"})
        self.assertFalse(result["ready"])
        self.assertEqual(next(m for m in result["modules"] if m["id"] == "alth_character_alpha")["computed_level"], "M5")

    def test_model_loop_is_blocked_if_any_m5_prerequisite_regresses(self):
        with tempfile.TemporaryDirectory(dir=".") as td:
            root = Path(td).resolve()
            coverage = json.loads(Path("copox/maturity/theo.json").read_text())
            fingers = next(m for m in coverage["modules"] if m["id"] == "fingers")
            fingers["capabilities"]["regression"] = False
            coverage_path = root / "immature.json"
            coverage_path.write_text(json.dumps(coverage))
            cassette = json.loads(Path("copox/cassettes/examples/theo.json").read_text())
            cassette["maturity"]["coverage"] = str(coverage_path)
            cassette_path = root / "cassette.json"
            cassette_path.write_text(json.dumps(cassette))
            code = run_campaign(cassette_path, output_root=td)
            self.assertEqual(code, 4)
            manifests = list(Path(td).rglob("manifest.json"))
            self.assertEqual(len(manifests), 1)
            data = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "MATURITY_BLOCKED")
            self.assertEqual(data["candidates"], [])
            self.assertTrue((manifests[0].parent / "maturity.json").exists())

    def test_m5_readiness_does_not_enable_a_productive_campaign(self):
        enabled = Path("copox/cassettes/enabled")
        self.assertEqual(list(enabled.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
