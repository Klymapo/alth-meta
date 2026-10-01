import json
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from copox.production.research_gate import require_research, validate_research
from copox.production.research_iteration_loop import run_generations

BRIEF = Path("copox/research/fingers-micro-valleys-20261001.json")


class ResearchIterationTests(unittest.TestCase):
    def setUp(self):
        self.brief = json.loads(BRIEF.read_text())
        self.brief["researched_at"] = datetime.now(timezone.utc).isoformat()

    def test_theo_promotion_is_blocked_even_with_pass_gate(self):
        from copox.adapters.alth_model_m5 import cmd_promote
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            policy = repo / "copox" / "production" / "theo_m5_policy.json"
            policy.parent.mkdir(parents=True)
            policy.write_text(json.dumps({"automatic_promotion_enabled": False}))
            candidate = repo / "candidate"
            candidate.mkdir()
            (candidate / "gate.json").write_text(json.dumps({"promotion_allowed": True}))
            with patch("copox.adapters.alth_model_m5.save_bundle") as save:
                code = cmd_promote(Namespace(repo_root=str(repo), candidate_dir=str(candidate)))
                save.assert_not_called()
            self.assertEqual(code, 9)
            report = json.loads((candidate / "promotion.json").read_text())
            self.assertFalse(report["promotion_executed"])
            self.assertEqual(report["status"], "PROMOTION_DISABLED")

    def test_unresearched_technique_cannot_mutate(self):
        result = validate_research(self.brief, "fingers", technique="invented_technique")
        self.assertEqual(result["status"], "RESEARCH_REQUIRED")
        self.assertFalse(result["research_ready"])

    def test_stale_and_future_research_fail_closed(self):
        for delta in (-46, 1):
            brief = {**self.brief, "researched_at": (datetime.now(timezone.utc) + timedelta(days=delta)).isoformat()}
            self.assertFalse(validate_research(brief, "fingers", technique="micro_valley_cut_local_sections")["research_ready"])

    def test_no_fake_browsing(self):
        brief = {**self.brief, "web_research_performed": False}
        self.assertFalse(validate_research(brief, "fingers", technique="micro_valley_cut_local_sections")["research_ready"])

    def test_malformed_brief_has_report(self):
        with tempfile.TemporaryDirectory() as td:
            path, report = Path(td, "brief.json"), Path(td, "gate.json")
            path.write_text("{malformed")
            with self.assertRaisesRegex(RuntimeError, "RESEARCH_REQUIRED"):
                require_research(path, "fingers", output=report, technique="micro_valley_cut_local_sections")
            self.assertEqual(json.loads(report.read_text())["status"], "RESEARCH_REQUIRED")

    def test_missing_research_never_calls_mutator(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            spec = {"brief": Path(td, "missing.json"), "technique": "micro_valley_cut_local_sections",
                    "parameters": [{"depth_scale": x} for x in (0.75, 1, 1.25)], "next_hypothesis": "research"}
            result = run_generations(parent_sha="immutable", module="fingers", specs=[spec], output=td,
                                     mutate_and_audit=lambda *args: calls.append(args))
            self.assertEqual(calls, [])
            self.assertEqual(result["stop_reason"], "RESEARCH_REQUIRED")

    def test_all_generations_use_same_parent_no_rejected_lineage(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "brief.json")
            path.write_text(json.dumps(self.brief))
            calls = []
            spec = {"brief": path, "technique": "micro_valley_cut_local_sections",
                    "parameters": [{"depth_scale": x} for x in (0.75, 1, 1.25)], "next_hypothesis": "refine"}
            def mutate(directory, params, parent):
                calls.append(parent)
                return {"candidate": directory.name, "parent_sha": parent, "audit_passed": False,
                        "semantic_ready": False, "mesh_integrity": True, "regression_ok": True,
                        "parent_target_delta_pp": 0.5, "target_gain_pp": 1, "global_gain_pp": 0.1}
            result = run_generations(parent_sha="immutable", module="fingers", specs=[spec] * 3,
                                     output=td, mutate_and_audit=mutate)
            self.assertEqual(calls, ["immutable"] * 9)
            self.assertEqual(result["stop_reason"], "ITERATION_LIMIT")
            self.assertFalse(result["promotion_executed"])
            self.assertTrue(all(row["winner"] is None for row in result["generations"]))

    def test_pending_visual_audit_cannot_become_winner(self):
        with tempfile.TemporaryDirectory() as td:
            brief=Path(td,"brief.json")
            brief.write_text(json.dumps(self.brief))
            spec={"brief":brief,"technique":"micro_valley_cut_local_sections",
                  "parameters":[{"depth_scale":x} for x in (.75,1,1.25)],"next_hypothesis":"inspect evidence"}
            def mutate(directory,params,parent):
                return {"candidate":directory.name,"parent_sha":parent,"audit_passed":True,
                        "mesh_integrity":True,"semantic_ready":True,"regression_ok":True,
                        "visual_review":"PENDING","target_gain_pp":1,"global_gain_pp":.2,"parent_target_delta_pp":.5}
            result=run_generations(parent_sha="immutable",module="fingers",specs=[spec],output=td,mutate_and_audit=mutate)
            self.assertIsNone(result["generations"][0]["winner"])
            self.assertEqual(result["stop_reason"],"VISUAL_REVIEW_REQUIRED")
            self.assertEqual(len(result["generations"][0]["pending_visual_candidates"]),3)
            self.assertFalse(result["promotion_executed"])

    def test_passing_gate_stops_after_exactly_three_and_never_promotes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "brief.json")
            path.write_text(json.dumps(self.brief))
            spec = {"brief": path, "technique": "micro_valley_cut_local_sections",
                    "parameters": [{"depth_scale": x} for x in (0.75, 1, 1.25)], "next_hypothesis": "visual review"}
            def mutate(directory, params, parent):
                return {"candidate": directory.name, "parent_sha": parent, "audit_passed": True,
                        "mesh_integrity": True, "semantic_ready": True, "regression_ok": True,
                        "target_gain_pp": params["depth_scale"], "global_gain_pp": 0.2,
                        "parent_target_delta_pp": 0.1}
            result = run_generations(parent_sha="immutable", module="fingers", specs=[spec] * 3,
                                     output=td, mutate_and_audit=mutate)
            self.assertEqual(len(result["generations"]), 1)
            self.assertEqual(len(result["generations"][0]["candidate_metrics"]), 3)
            self.assertFalse(result["promotion_allowed"])
            self.assertEqual(result["stop_reason"], "CANDIDATE_PASSED_GATES")


if __name__ == "__main__":
    unittest.main()
