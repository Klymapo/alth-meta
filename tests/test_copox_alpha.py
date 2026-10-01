import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh

from copox.adapters.alth_glb_character import apply_structured_hair
from copox.contracts import load_cassette
from copox.state_bundle import load_bundle, save_bundle


class CopoxAlphaTests(unittest.TestCase):
    def test_seed_matches_the_artistic_approval(self):
        approved = json.loads(Path("copox/approved/theo.json").read_text())["approved_artistic_version"]
        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(hashlib.sha256(Path(approved["repo_path"]).read_bytes()).hexdigest(), approved["sha256"])

    def test_theo_cassette_uses_approved_alpha_glb(self):
        cassette = load_cassette("copox/cassettes/examples/theo.json")
        variables = cassette.data["variables"]
        self.assertEqual(variables["baseline_model"], "assets/joven_rubio/theo_alpha.glb")
        self.assertEqual(cassette.data["baseline"], "copox/baselines/joven_rubio_alpha.json")
        self.assertEqual(cassette.data["profile"], "copox/profiles/alth_character_alpha.json")
        applicable = {a["id"]: a.get("applicable", True) for a in cassette.auditors}
        self.assertTrue(applicable["HairAgent"])
        self.assertTrue(applicable["HairStructureGate"])
        self.assertTrue(applicable["HairRandomnessGate"])

    def test_search_space_contains_no_random_hair_generator_controls(self):
        data = Path("copox/search_spaces/joven_rubio_alpha_hair.json").read_text(encoding="utf-8").lower()
        for forbidden in ("semilla", "cunias", "cuñas", "copete"):
            self.assertNotIn(forbidden, data)
        self.assertIn("front_width_scale", data)
        self.assertIn("side_outward_mm", data)

    def test_structured_edit_keeps_frozen_nodes_unchanged(self):
        source = Path("assets/joven_rubio/theo_alpha.glb")
        self.assertTrue(source.exists())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            params = root / "params.json"
            params.write_text(json.dumps({"hair": {"front_width_scale": 1.04}}), encoding="utf-8")
            out = root / "candidate.glb"
            report_path = root / "report.json"
            report = apply_structured_hair(
                source,
                params,
                "copox/reference_configs/joven_rubio_alpha.json",
                out,
                report_path,
            )
            self.assertTrue(report["verificacion"]["ok"])
            self.assertTrue(report["technical"]["frozen_nodes_unchanged"])
            self.assertTrue(report["structure"]["hair_structure_ok"])
            self.assertEqual(report["structure"]["randomness_penalty_mm"], 0.0)
            self.assertTrue(out.exists())

    def test_state_bundle_roundtrip_preserves_binary_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            remote = root / "remote.git"
            repo = root / "repo"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "init", str(repo)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
            baseline = root / "baseline.json"
            model = root / "model.glb"
            baseline.write_text('{"hair":{"front_width_scale":1.0}}\n', encoding="utf-8")
            model.write_bytes(b"glTF-test-binary\x00\x01\xff")
            branch = "copox/state/test-alpha"
            commit = save_bundle(repo, branch, baseline, model, {"cassette_id": "test-alpha"})
            out_baseline = root / "out" / "baseline.json"
            out_model = root / "out" / "model.glb"
            meta = load_bundle(repo, branch, out_baseline, out_model, baseline, model)
            self.assertEqual(meta["commit"], commit)
            self.assertEqual(out_model.read_bytes(), model.read_bytes())
            self.assertEqual(json.loads(out_baseline.read_text())["hair"]["front_width_scale"], 1.0)


if __name__ == "__main__":
    unittest.main()
