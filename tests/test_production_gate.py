from pathlib import Path

from copox.production import module_gate


POLICY = {
    "min_target_gain_pp": 0.10,
    "modules": {
        "hands": {
            "required_evidence": ["hand_left", "hand_right", "hand_detail", "learning"],
            "forbidden_flags": ["mitten_shape", "thumb_unreadable"],
        },
        "ears": {
            "required_evidence": ["region_side", "region_threeq", "uv_probe", "learning"],
            "forbidden_flags": ["phantom_ear", "material_scope_leak"],
        },
    },
}


def touch(root: Path, *names: str) -> None:
    for name in names:
        p = root / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")


def test_m5_gate_passes_complete_candidate(tmp_path):
    touch(tmp_path, "hand_left", "hand_right", "hand_detail", "learning")
    out = module_gate(policy=POLICY, module_id="hands", candidate_dir=tmp_path,
                      audit_results=[{"target_gain_pp": 0.25}], score=0.9)
    assert out["status"] == "PASS"


def test_m5_gate_vetoes_missing_evidence(tmp_path):
    touch(tmp_path, "hand_left", "hand_right")
    out = module_gate(policy=POLICY, module_id="hands", candidate_dir=tmp_path,
                      audit_results=[{"target_gain_pp": 0.25}], score=0.9)
    assert out["status"] == "FAIL"
    assert "missing_evidence" in out["reason"]


def test_m5_gate_vetoes_semantic_failure(tmp_path):
    touch(tmp_path, "hand_left", "hand_right", "hand_detail", "learning")
    out = module_gate(policy=POLICY, module_id="hands", candidate_dir=tmp_path,
                      audit_results=[{"mitten_shape": True, "target_gain_pp": 0.25}], score=0.9)
    assert out["status"] == "FAIL"
    assert out["forbidden_flags"] == ["mitten_shape"]


def test_m5_gate_vetoes_insufficient_gain_when_measured(tmp_path):
    touch(tmp_path, "region_side", "region_threeq", "uv_probe", "learning")
    out = module_gate(policy=POLICY, module_id="ears", candidate_dir=tmp_path,
                      audit_results=[{"target_gain_pp": 0.01}], score=0.9)
    assert out["status"] == "FAIL"
    assert "insufficient_gain" in out["reason"]


def test_m5_gate_rejects_unknown_module(tmp_path):
    out = module_gate(policy=POLICY, module_id="unknown", candidate_dir=tmp_path,
                      audit_results=[], score=0.0)
    assert out["status"] == "FAIL"
    assert out["reason"] == "module_not_registered"
