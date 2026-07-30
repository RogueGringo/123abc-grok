"""Dual-gate → handoff pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.handoff.pipeline import export_structure_handoff, policy_stamp
from realm.validate.length_policy import policy_for
from realm.validate.report import load_knobs


def test_dual_gate_pins_still_locked():
    p = policy_for(12, base_beta=0.20)
    assert abs(p.soft_T - 0.036) < 1e-12
    assert p.seq_mix == 0.0
    assert abs(p.face_weight - 0.08) < 1e-12


def test_policy_stamp_matches_policy_for():
    st = policy_stamp(12)
    assert abs(st["length_policy"]["soft_T"] - 0.036) < 1e-12
    assert "not_lambda_eq_gamma" in st["ontology"]


def test_export_structure_handoff_1csa(tmp_path: Path):
    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        pytest.skip("need evolve_result.json and data/pdb/1CSA.pdb")
    kn = load_knobs(kn_path)
    if isinstance(kn, dict) and "best_knobs" in kn:
        kn = kn["best_knobs"]
    out = export_structure_handoff(
        "1CSA",
        kn,
        out_dir=tmp_path / "1CSA",
        top_k=3,
        include_coutsias=False,
        decorate="null",
        physics="geometry",
    )
    assert out["status"] == "OK"
    assert out["n_molds"] >= 1
    assert abs(out["dual_gate"]["length_policy"]["soft_T"] - policy_for(11).soft_T) < 1e-12
    idx = tmp_path / "1CSA" / "index.json"
    assert idx.is_file()
    for m in out["molds"]:
        assert Path(m["path_ca"]).is_file()
        assert Path(m["path_bb"]).is_file()
        assert m["ontology_remark_ok"] is True
        text = Path(m["path_ca"]).read_text(encoding="utf-8")
        assert "not_lambda_eq_gamma" in text
        assert "SOURCE" in text
