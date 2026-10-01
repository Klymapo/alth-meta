import unittest

from copox.production.regional_trial import _semantic_hand_progress, _variant


class FingerValleyTests(unittest.TestCase):
    def test_third_finger_technique_uses_one_cut_and_valley_carve(self):
        params = _variant("fingers", 2, 3)
        self.assertTrue(params["topology_refine"])
        self.assertEqual(params["refine_cuts"], 1)
        self.assertTrue(params["valley_carve"])
        self.assertGreater(params["valley_strength"], 0.0)

    def test_semantic_progress_can_be_incremental(self):
        baseline = {
            "hands": [
                {"side": "left", "component_gap": 0, "vertical_run_gap": 3},
                {"side": "right", "component_gap": 0, "vertical_run_gap": 1},
            ],
            "summary": {"mean_component_gap": 0.0, "mean_vertical_run_gap": 2.0, "definition_match": False},
        }
        candidate = {
            "hands": [
                {"side": "left", "component_gap": 0, "vertical_run_gap": 2},
                {"side": "right", "component_gap": 0, "vertical_run_gap": 1},
            ],
            "summary": {"mean_component_gap": 0.0, "mean_vertical_run_gap": 1.5, "definition_match": False},
        }
        result = _semantic_hand_progress(baseline, candidate)
        self.assertTrue(result["semantic_improved"])
        self.assertFalse(result["definition_match"])
        self.assertEqual(result["gap_improvement"], 0.5)

    def test_average_gain_cannot_hide_one_hand_regression(self):
        baseline = {
            "hands": [
                {"side": "left", "component_gap": 0, "vertical_run_gap": 3},
                {"side": "right", "component_gap": 0, "vertical_run_gap": 1},
            ],
            "summary": {"mean_component_gap": 0.0, "mean_vertical_run_gap": 2.0, "definition_match": False},
        }
        candidate = {
            "hands": [
                {"side": "left", "component_gap": 0, "vertical_run_gap": 1},
                {"side": "right", "component_gap": 0, "vertical_run_gap": 2},
            ],
            "summary": {"mean_component_gap": 0.0, "mean_vertical_run_gap": 1.5, "definition_match": False},
        }
        result = _semantic_hand_progress(baseline, candidate)
        self.assertGreater(result["gap_improvement"], 0.0)
        self.assertFalse(result["no_side_worse"])
        self.assertFalse(result["semantic_improved"])


if __name__ == "__main__":
    unittest.main()
