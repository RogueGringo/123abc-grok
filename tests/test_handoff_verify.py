"""Handoff verify + campaign smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from handoff_verify import main as verify_main
from realm.handoff.package import (
    archive_partner_release,
    build_partner_package,
    write_release_md,
)
from realm.handoff.pipeline import export_structure_batch, export_structure_handoff
from realm.handoff.verify import (
    quality_gate,
    verify_archive_dir,
    verify_dual_gate_pin,
    verify_handoff_tree,
)
from realm.validate.report import load_knobs


def test_verify_dual_gate_pin():
    r = verify_dual_gate_pin()
    assert r["ok"] is True
    assert abs(r["soft_T"] - 0.036) < 1e-12


def test_quality_gate_pass_and_fail():
    pin_ok_export = {"n_ok": 2, "n_ids": 2}
    report_ok = {
        "ok": True,
        "ontology_remarks": {"ok": True, "n_pdb": 4},
        "biopython": {"ok": None, "skipped": True},
    }
    g = quality_gate(pin_ok_export, report_ok, min_ok_fraction=1.0, min_openable_pdbs=2)
    assert g["ok"] is True
    assert g["export"]["ok_fraction"] == 1.0

    g_fail = quality_gate(
        {"n_ok": 1, "n_ids": 4},
        report_ok,
        min_ok_fraction=0.9,
        min_openable_pdbs=1,
    )
    assert g_fail["ok"] is False
    assert any("ok_fraction" in r for r in g_fail["reasons"])


def test_quality_gate_require_biopython():
    report = {
        "ok": True,
        "ontology_remarks": {"ok": True, "n_pdb": 2},
        "biopython": {"ok": None, "skipped": True},
    }
    g = quality_gate(
        {"n_ok": 1, "n_ids": 1},
        report,
        require_biopython=True,
    )
    assert g["ok"] is False
    assert any("biopython_required" in r for r in g["reasons"])

    report_bio = {
        "ok": True,
        "ontology_remarks": {"ok": True, "n_pdb": 2},
        "biopython": {"ok": True, "n_ok": 2},
    }
    g2 = quality_gate(
        {"n_ok": 1, "n_ids": 1},
        report_bio,
        require_biopython=True,
    )
    assert g2["ok"] is True
    assert g2["biopython_ok"] is True


def test_verify_archive_dir(tmp_path: Path):
    camp = tmp_path / "camp"
    camp.mkdir()
    zpath = tmp_path / "pkg.zip"
    zpath.write_bytes(b"PK\x03\x04data")
    campaign = {
        "ids": ["1CSA"],
        "export": {"n_ok": 1, "n_ids": 1, "summary_md": str(camp / "SUMMARY.md")},
        "package": {
            "zip_path": str(zpath),
            "zip_sha256": "x",
        },
        "quality_gate": {"ok": True},
    }
    (camp / "SUMMARY.md").write_text("# s\n", encoding="utf-8")
    (camp / "campaign_report.json").write_text("{}\n", encoding="utf-8")
    (camp / "verify_report.json").write_text('{"ok":true}\n', encoding="utf-8")
    write_release_md(campaign, camp / "RELEASE.md", label="t")
    campaign["release_md"] = str(camp / "RELEASE.md")
    meta = archive_partner_release(
        campaign,
        archive_root=tmp_path / "releases",
        label="t",
        campaign_dir=camp,
    )
    arch = Path(meta["archive_dir"])
    report = verify_archive_dir(arch)
    assert report["ok"] is True
    assert report["n_checked"] >= 1
    assert report["pin"]["ok"] is True

    # tamper
    (arch / "RELEASE.md").write_text("tampered\n", encoding="utf-8")
    bad = verify_archive_dir(arch)
    assert bad["ok"] is False
    assert bad["n_bad"] >= 1

    rc = verify_main(["--archive", str(arch), "--report", str(tmp_path / "av.json")])
    assert rc == 3


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

    # standalone CLI
    rc = verify_main(
        [
            str(meta["package_dir"]),
            "--require-sha256",
            "--no-biopython",
            "--report",
            str(tmp_path / "cli_report.json"),
        ]
    )
    assert rc == 0
    assert (tmp_path / "cli_report.json").is_file()


def test_package_includes_batch_summary(tmp_path: Path):
    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        pytest.skip("need evolve_result.json and data/pdb/1CSA.pdb")
    kn = load_knobs(kn_path)
    if isinstance(kn, dict) and "best_knobs" in kn:
        kn = kn["best_knobs"]
    root = tmp_path / "batch"
    summary = export_structure_batch(
        ["1CSA"],
        kn,
        out_root=root,
        top_k=1,
        include_coutsias=False,
        with_biopython_check=False,
    )
    assert summary["n_ok"] == 1
    assert (root / "SUMMARY.md").is_file()
    meta = build_partner_package(
        root, dest_dir=tmp_path / "pkg", zip_path=tmp_path / "pkg.zip"
    )
    assert meta.get("has_summary_md") is True
    pkg = Path(meta["package_dir"])
    assert (pkg / "SUMMARY.md").is_file()
    readme = (pkg / "PARTNER_README.md").read_text(encoding="utf-8")
    assert "handoff_verify" in readme
