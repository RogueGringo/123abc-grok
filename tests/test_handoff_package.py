"""Partner package builder tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from realm.handoff.package import build_partner_package, write_release_md
from realm.handoff.pipeline import export_structure_handoff
from realm.validate.length_policy import policy_for
from realm.validate.report import load_knobs


def test_dual_gate_still_locked():
    p = policy_for(12, base_beta=0.20)
    assert abs(p.soft_T - 0.036) < 1e-12


def test_write_release_md(tmp_path: Path):
    campaign = {
        "ids": ["1CSA"],
        "export": {"n_ok": 1, "n_ids": 1, "summary_md": "SUMMARY.md"},
        "package": {
            "package_dir": str(tmp_path / "pkg"),
            "zip_path": str(tmp_path / "p.zip"),
            "zip_sha256": "abc",
            "has_summary_md": True,
        },
        "verify": {
            "ok": True,
            "pin": {
                "ok": True,
                "soft_T": 0.036,
                "seq_mix": 0.0,
                "face_weight": 0.08,
            },
            "ontology_remarks": {"ok": True, "n_pdb": 4},
            "sha256": {"ok": True},
        },
        "quality_gate": {"ok": True, "reasons": [], "n_pdb": 4},
        "ontology": "handoff_campaign_not_lambda_eq_gamma",
    }
    path = write_release_md(campaign, tmp_path / "RELEASE.md", label="probe")
    text = path.read_text(encoding="utf-8")
    assert "0.036" in text
    assert "not" in text.lower() and "lambda" in text.lower()
    assert "1CSA" in text
    assert "Quality gate" in text
    assert "handoff_verify" in text


def test_build_partner_package(tmp_path: Path):
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
    meta = build_partner_package(
        src,
        dest_dir=tmp_path / "pkg",
        zip_path=tmp_path / "pkg.zip",
        label="test_pkg",
    )
    pkg = Path(meta["package_dir"])
    assert (pkg / "PARTNER_README.md").is_file()
    assert (pkg / "SHA256SUMS.txt").is_file()
    assert (pkg / "manifest.tsv").is_file() or list(pkg.rglob("manifest.tsv"))
    assert Path(meta["zip_path"]).is_file()
    assert "not_lambda_eq_gamma" in meta["ontology"]
    readme = (pkg / "PARTNER_README.md").read_text(encoding="utf-8")
    assert "not_lambda_eq_gamma" in readme or "Never" in readme
