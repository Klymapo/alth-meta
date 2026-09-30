import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from copox.adapters.alth_character import cmd_mutate
from copox.contracts import ContractError, load_cassette


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
        applicable = {a["id"]: a.get("applicable", True) for a in c.auditors}
        self.assertFalse(applicable["HeadAgent"])
        self.assertFalse(applicable["FaceAgent"])
        self.assertTrue(applicable["HairAgent"])
        self.assertFalse(applicable["ArmsAgent"])
        self.assertFalse(applicable["LegsAgent"])
        self.assertFalse(applicable["FootwearAgent"])
        self.assertNotIn("theo", Path("copox/engine.py").read_text(encoding="utf-8").lower())

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


if __name__ == "__main__":
    unittest.main()
