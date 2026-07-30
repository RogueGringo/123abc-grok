"""Handoff verify + campaign smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from realm.handoff.package import build_partner_package
from realm.handoff.pipeline import export_structure_handoff
from realm.handoff.verify import verify_dual_gate_pin, verify_handoff_tree
from realm.validate.report import load_knobs


def test_verify_dual_gate_pin():
    r = verify_dual_gate_pin()
    assert r["ok"] is True
    assert abs(r["soft_T"] - 0.036) < 1e-12


def test_verify_handoff_tree_after_package(tmp_path: Path):
    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        pytest.skip("need evolve_result.json and data/pdb/1CSA.pdb")
    kn = load_knobs(kn_path)
    if isinstance(kn, dict) and "best_knobs" in kn:
        kn = kn["best_knobs"]
    src = tmp_path / "export"
    export_structure_handoff(
        "1CSA",
        kn,
        out_dir=src,
        top_k=2,
        include_coutsias=False,
        with_biopython_check=False,
    )
    meta = build_partner_package(src, dest_dir=tmp_path / "pkg", zip_path=tmp_path / "p.zip")
    report = verify_handoff_tree(
        meta["package_dir"],
        require_sha256=True,
        check_biopython=False,
    )
    assert report["pin"]["ok"] is True
    assert report["ontology_remarks"]["ok"] is True
    assert report["sha256"]["ok"] is True
    assert report["ok"] is True
