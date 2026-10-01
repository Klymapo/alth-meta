import json
import unittest
from pathlib import Path

from copox.production.module_gate import evaluate
from copox.production.module_router import choose


POLICY_PATH = Path("copox/production/theo_m5_policy.json")


class CopoxM5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def _good(self, module="fingers"):
        required = self.policy["modules"][module].get("required_evidence", [])
        return {
            "module": module,
            "mesh_integrity": True,
            "scope_safe": True,
            "regression_ok": True,
            "evidence_complete": True,
            "semantic_ready": True,
            "target_gain_pp": 0.25,
            "global_gain_pp": 0.05,
            "worst_view_delta_pp": -0.02,
            "evidence": required,
            "flags": [],
        }

    def test_good_candidate_can_pass_gate(self):
        gate = evaluate(self.policy, self._good("fingers"))
        self.assertTrue(gate["promotion_allowed"], gate)

    def test_local_gain_never_compensates_global_regression(self):
        result = self._good("hands")
        result["target_gain_pp"] = 12.0
        result["worst_view_delta_pp"] = -0.50
        gate = evaluate(self.policy, result)
        self.assertFalse(gate["promotion_allowed"])
        self.assertIn("single_view_regression", gate["reasons"])

    def test_semantic_uncertainty_vetoes_candidate(self):
        result = self._good("ears")
        result["semantic_ready"] = False
        gate = evaluate(self.policy, result)
        self.assertFalse(gate["promotion_allowed"])
        self.assertIn("semantic_ready", gate["reasons"])

    def test_forbidden_flag_vetoes_candidate(self):
        result = self._good("hair")
        result["flags"] = ["hair_randomness"]
        gate = evaluate(self.policy, result)
        self.assertFalse(gate["promotion_allowed"])
        self.assertIn("forbidden_flags:hair_randomness", gate["reasons"])

    def test_router_prefers_explained_regional_error_over_global(self):
        diagnostics = {
            "modules": {
                "global_proportions": {"error": 1.0, "confidence": 1.0, "actionable": True},
                "ears": {"error": 0.6, "confidence": 0.9, "learning_need": 0.9, "actionable": True},
                "hands": {"error": 0.7, "confidence": 0.9, "actionable": True},
            }
        }
        routed = choose(self.policy, diagnostics)
        self.assertTrue(routed["global_suppressed"])
        self.assertIn(routed["selected"], {"ears", "hands"})
        self.assertNotEqual(routed["selected"], "global_proportions")

    def test_router_can_use_global_when_no_regional_explanation_exists(self):
        diagnostics = {"modules": {"global_proportions": {"error": 0.8, "confidence": 1.0, "actionable": True}}}
        routed = choose(self.policy, diagnostics)
        self.assertEqual(routed["selected"], "global_proportions")

    def test_policy_covers_every_model_module(self):
        coverage = json.loads(Path("copox/maturity/theo.json").read_text(encoding="utf-8"))
        ids = {m["id"] for m in coverage["modules"]}
        self.assertEqual(ids, set(self.policy["modules"]))


if __name__ == "__main__":
    unittest.main()
