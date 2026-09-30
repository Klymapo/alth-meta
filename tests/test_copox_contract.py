import json
import tempfile
import unittest
from pathlib import Path

from copox.contracts import ContractError, load_cassette


class CopoxContractTests(unittest.TestCase):
    def test_smoke_contract_loads(self):
        c = load_cassette("copox/cassettes/examples/smoke.json")
        self.assertEqual(c.tournament_size, 3)
        self.assertEqual(c.max_candidates, 6)
        self.assertTrue(c.unanimity_required)

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


if __name__ == "__main__":
    unittest.main()
