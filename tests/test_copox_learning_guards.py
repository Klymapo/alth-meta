import json
import tempfile
import unittest
from pathlib import Path

from copox.learning.facial_diagnosis import diagnose as diagnose_face
from copox.learning.global_shape_study import check_view_regression
from copox.learning.rig_diagnosis import diagnose as diagnose_rig
from copox.learning.topology_diagnosis import diagnose as diagnose_topology


class LearningGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data))
        return str(path)

    def rig_inputs(self):
        return (
            {"bone_names": ["head", "forearm.L"], "vertex_count": 10, "weight_coverage": 1.0,
             "pose_test": {"finite": True, "moved_vertices": 3, "max_displacement": 0.002}},
            {"counts": {"skins": 1}, "rig": {"joint_names": ["head", "forearm.L"]}},
            {"regions": {"arms": {"views": [{"delta_pp": 0.0}]}}},
        )

    def run_rig(self, candidate, structure, regional):
        return diagnose_rig(self.write("rig.json", candidate), self.write("structure.json", structure),
                            self.write("regional.json", regional), str(self.root / "learning.json"))

    def test_exported_rig_with_real_pose_is_m4_without_promotion(self):
        result = self.run_rig(*self.rig_inputs())
        self.assertTrue(result["ready_for_m4_process"])
        self.assertFalse(result["promotion_allowed"])

    def test_missing_exported_joint_blocks_m4(self):
        candidate, structure, regional = self.rig_inputs()
        structure["rig"]["joint_names"].remove("forearm.L")
        result = self.run_rig(candidate, structure, regional)
        self.assertFalse(result["ready_for_m4_process"])
        self.assertEqual(result["action"], "FIX_SKIN_EXPORT")

    def test_rest_pose_regression_is_not_hidden_by_other_views(self):
        candidate, structure, regional = self.rig_inputs()
        regional["regions"]["arms"]["views"] = [{"delta_pp": -0.2}, {"delta_pp": 0.2}]
        result = self.run_rig(candidate, structure, regional)
        self.assertFalse(result["ready_for_m4_process"])
        self.assertEqual(result["action"], "REPAIR_REST_POSE")

    def test_nonfinite_deformation_blocks_m4(self):
        candidate, structure, regional = self.rig_inputs()
        candidate["pose_test"]["max_displacement"] = float("nan")
        self.assertFalse(self.run_rig(candidate, structure, regional)["ready_for_m4_process"])

    def test_named_controls_must_survive_glb_export(self):
        candidate = {"controls": {"blink_left": {}, "blink_right": {}, "mouth_open": {}},
                     "rest_vertices_unchanged": True, "all_controls_move_vertices": True}
        structure = {"counts": {"morph_targets": 3}, "rig": {"morph_target_meshes": [{"target_names": ["unknown"]}]}}
        result = diagnose_face(self.write("face.json", candidate), self.write("structure.json", structure),
                               str(self.root / "learning.json"))
        self.assertFalse(result["ready_for_m4_process"])
        self.assertFalse(result["exported"])

    def test_global_gain_cannot_compensate_a_single_view_regression(self):
        deltas = {"front": 3.0, "side": -0.3, "back": 2.0, "threeq": 1.0}
        result = check_view_regression(deltas)
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_views"], ["side"])

    def test_missing_or_nonfinite_view_blocks_global_hypothesis(self):
        self.assertFalse(check_view_regression({"front": 0.0})["ok"])
        deltas = dict.fromkeys(("front", "side", "back", "threeq"), 0.0)
        deltas["back"] = float("nan")
        self.assertFalse(check_view_regression(deltas)["ok"])

    def test_preserving_old_vertices_is_insufficient_if_new_surface_changes(self):
        candidate = {"safe_geometry_regression": True, "original_vertices_unchanged": True,
                     "surface_unchanged": False, "topology_density_increased": True, "selected_faces": 1,
                     "uv_layers": 1, "uv_layers_preserved": True}
        regional = {"regions": {"fingers": {"delta_pp": 0.0}}}
        result = diagnose_topology(self.write("topology.json", candidate), self.write("regional.json", regional),
                                   str(self.root / "learning.json"))
        self.assertFalse(result["ready_for_m4_process"])


if __name__ == "__main__":
    unittest.main()
