import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from copox.adapters.alth_character import cmd_mutate
from copox.contracts import ContractError, load_cassette
from copox.state import load_state, save_state


class CopoxContractTests(unittest.TestCase):
    def test_smoke_contract_loads(self):
        c = load_cassette("copox/cassettes/examples/smoke.json")
        self.assertEqual(c.tournament_size, 3)
        self.assertEqual(c.max_candidates, 6)
        self.assertTrue(c.unanimity_required)

    def test_theo_contract_is_generic_and_strict(self):
        c = load_cassette("copox/cassettes/examples/theo.json")
        self.assertEqual(c.kind, "alth_character")
        self.assertEqual(c.tournament_size, 3)
        self.assertEqual(c.max_candidates, 6)
        self.assertEqual(c.data["variables"]["focus"], "hair,profile")
        self.assertEqual(c.data["variables"]["state_branch"], "copox/state/theo-character")
        self.assertIn("{run_dir}/baseline/params.json", c.data["commands"]["mutate"])
        applicable = {a["id"]: a.get("applicable", True) for a in c.auditors}
        self.assertFalse(applicable["HeadAgent"])
        self.assertFalse(applicable["FaceAgent"])
        self.assertTrue(applicable["HairAgent"])
        self.assertFalse(applicable["ArmsAgent"])
        self.assertFalse(applicable["LegsAgent"])
        self.assertFalse(applicable["FootwearAgent"])
        self.assertNotIn("theo", Path("copox/engine.py").read_text(encoding="utf-8").lower())

    def test_theo_integral_m5_contract_loads_without_enabling_scheduler(self):
        c = load_cassette("copox/cassettes/examples/theo_model_m5.json")
        self.assertEqual(c.kind, "alth_model_m5")
        self.assertEqual(c.data["maturity"]["min_level"], "M5")
        self.assertEqual(c.data["maturity"]["production_policy"], "copox/production/theo_m5_policy.json")
        self.assertEqual(c.data["variables"]["state_branch"], "copox/state/theo-character")
        self.assertIn("copox.adapters.alth_model_m5", c.data["commands"]["prepare"])
        self.assertIn("copox.adapters.alth_model_m5", c.data["commands"]["capture"])
        self.assertTrue(all(a.get("applicable", True) for a in c.auditors))
        self.assertEqual(list(Path("copox/cassettes/enabled").glob("*.json")), [])

    def test_unanimity_is_mandatory(self):
        src = json.loads(Path("copox/cassettes/examples/smoke.json").read_text(encoding="utf-8"))
        src["promotion"]["unanimous"] = False
        with tempfile.TemporaryDirectory(dir=".") as td:
            path = Path(td) / "bad.json"
            src["profile"] = str(Path("copox/profiles/smoke.json").resolve())
            path.write_text(json.dumps(src), encoding="utf-8")
            with self.assertRaises(ContractError):
                load_cassette(path)

    def test_auditor_override_can_make_agent_na(self):
        src = json.loads(Path("copox/cassettes/examples/smoke.json").read_text(encoding="utf-8"))
        src["auditor_overrides"] = {"LearningArchitect": {"applicable": False}}
        with tempfile.TemporaryDirectory(dir=".") as td:
            path = Path(td) / "override.json"
            src["profile"] = str(Path("copox/profiles/smoke.json").resolve())
            path.write_text(json.dumps(src), encoding="utf-8")
            c = load_cassette(path)
            status = {a["id"]: a.get("applicable", True) for a in c.auditors}
            self.assertFalse(status["LearningArchitect"])

    def test_parametric_mutator_changes_one_allowed_parameter(self):
        with tempfile.TemporaryDirectory(dir=".") as td:
            root = Path(td)
            candidate = root / "candidate"
            candidate.mkdir()
            (root / "search_state.json").write_text(json.dumps({"parameter_cursor": 0}), encoding="utf-8")
            args = Namespace(
                baseline_params="copox/baselines/joven_rubio.json",
                search_space="copox/search_spaces/joven_rubio.json",
                run_dir=str(root),
                candidate_dir=str(candidate),
                candidate_id="t01-c01",
            )
            self.assertEqual(cmd_mutate(args), 0)
            out = json.loads((candidate / "params.json").read_text(encoding="utf-8"))
            meta = out["_copox"]
            self.assertEqual(meta["mutated_parameter"], "hair.escala")
            self.assertNotEqual(meta["baseline_value"], meta["candidate_value"])

    def test_state_branch_preserves_history_and_loads_latest_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            remote = root / "remote.git"
            repo = root / "repo"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "init", str(repo)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)

            b1 = root / "b1.json"
            b2 = root / "b2.json"
            b1.write_text('{"value": 1}\n', encoding="utf-8")
            b2.write_text('{"value": 2}\n', encoding="utf-8")
            branch = "copox/state/test-cassette"

            c1 = save_state(repo, branch, b1, {"cassette_id": "test-cassette", "candidate": "c1"})
            out1 = root / "out1.json"
            meta1 = load_state(repo, branch, out1)
            self.assertEqual(json.loads(out1.read_text())["value"], 1)
            self.assertEqual(meta1["commit"], c1)

            c2 = save_state(repo, branch, b2, {"cassette_id": "test-cassette", "candidate": "c2"})
            out2 = root / "out2.json"
            meta2 = load_state(repo, branch, out2)
            self.assertEqual(json.loads(out2.read_text())["value"], 2)
            self.assertEqual(meta2["commit"], c2)
            self.assertNotEqual(c1, c2)

            parents = subprocess.check_output(["git", "-C", str(repo), "rev-list", "--parents", "-n", "1", c2], text=True).split()
            self.assertEqual(parents[1], c1)


if __name__ == "__main__":
    unittest.main()
