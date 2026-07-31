"""Dual-gate → handoff pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.handoff.pipeline import (
    DEFAULT_HANDOFF_IDS,
    biopython_open_check,
    export_structure_batch,
    export_structure_handoff,
    policy_stamp,
    resolve_pdb_id_list,
    write_enrichment_summary_tsv,
    write_manifest_tsv,
)
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


def test_biopython_open_check_missing():
    r = biopython_open_check(Path("/no/such/file.pdb"))
    assert r["ok"] is False
    assert r["error"] == "missing_file"


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
        with_enrichment=False,
        with_biopython_check=True,
    )
    assert out["status"] == "OK"
    assert out["n_molds"] >= 1
    assert abs(out["dual_gate"]["length_policy"]["soft_T"] - policy_for(11).soft_T) < 1e-12
    idx = tmp_path / "1CSA" / "index.json"
    assert idx.is_file()
    man = tmp_path / "1CSA" / "manifest.tsv"
    assert man.is_file()
    text = man.read_text(encoding="utf-8")
    assert "path_ca" in text and "soft_T" in text
    for m in out["molds"]:
        assert Path(m["path_ca"]).is_file()
        assert Path(m["path_bb"]).is_file()
        assert m["ontology_remark_ok"] is True
        ca = Path(m["path_ca"]).read_text(encoding="utf-8")
        assert "not_lambda_eq_gamma" in ca
    assert (tmp_path / "1CSA" / "PHYSICS_ROLLUP.json").is_file()


def test_export_structure_handoff_polyala(tmp_path: Path):
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
        top_k=2,
        include_coutsias=False,
        decorate="polyala",
        physics="geometry",
        with_enrichment=False,
        with_biopython_check=False,
    )
    assert out["status"] == "OK"
    dec = out.get("decorate_rollup") or {}
    assert dec.get("n_ok", 0) >= 1
    assert (tmp_path / "1CSA" / "DECORATE_ROLLUP.json").is_file()
    # at least one decorated polyala file
    decorated = list((tmp_path / "1CSA").rglob("*_polyala.pdb"))
    assert decorated
    text = decorated[0].read_text(encoding="utf-8")
    assert " CB " in text or "CB  ALA" in text
    for m in out["molds"]:
        assert m.get("decorate_status") == "OK"
        assert m.get("path_decorated")


def test_export_batch_campaign_rollups(tmp_path: Path):
    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        pytest.skip("need evolve_result.json and data/pdb/1CSA.pdb")
    kn = load_knobs(kn_path)
    if isinstance(kn, dict) and "best_knobs" in kn:
        kn = kn["best_knobs"]
    summary = export_structure_batch(
        ["1CSA"],
        kn,
        out_root=tmp_path / "camp",
        top_k=2,
        decorate="sequence",
        physics="geometry",
        with_enrichment=False,
        with_biopython_check=False,
        include_coutsias=False,
    )
    assert summary["n_ok"] == 1
    assert (tmp_path / "camp" / "DECORATE_ROLLUP.json").is_file()
    assert (tmp_path / "camp" / "PHYSICS_ROLLUP.json").is_file()
    dec = summary.get("decorate_rollup") or {}
    assert int(dec.get("n_ok") or 0) >= 1
    md = (tmp_path / "camp" / "SUMMARY.md").read_text(encoding="utf-8")
    assert "Decorate OK" in md
    assert "Physics self-check" in md
    # verify decorate inventory
    from realm.handoff.verify import verify_decorate_inventory, verify_handoff_tree

    inv = verify_decorate_inventory(tmp_path / "camp")
    assert inv["n_decorated"] >= 1
    assert inv["n_with_ontology_remark"] >= 1
    report = verify_handoff_tree(
        tmp_path / "camp",
        require_sha256=False,
        check_biopython=False,
    )
    assert "decorate_inventory" in report
    assert report["pin"]["ok"] is True


def test_export_batch_manifest(tmp_path: Path):
    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        pytest.skip("need evolve_result.json and data/pdb/1CSA.pdb")
    kn = load_knobs(kn_path)
    if isinstance(kn, dict) and "best_knobs" in kn:
        kn = kn["best_knobs"]
    summary = export_structure_batch(
        ["1CSA"],
        kn,
        out_root=tmp_path / "batch",
        top_k=2,
        include_coutsias=False,
        with_enrichment=False,
        with_biopython_check=False,
    )
    assert summary["n_ok"] == 1
    root_man = tmp_path / "batch" / "manifest.tsv"
    assert root_man.is_file()
    assert "1CSA" in root_man.read_text(encoding="utf-8")
    enr = tmp_path / "batch" / "enrichment_summary.tsv"
    assert enr.is_file()
    assert "soft_T" in enr.read_text(encoding="utf-8")


def test_resolve_pdb_id_list_tokens():
    assert "1CSA" in resolve_pdb_id_list("probe")
    assert "1TET" in resolve_pdb_id_list("holdout")
    assert len(resolve_pdb_id_list("default")) == len(DEFAULT_HANDOFF_IDS)
    assert resolve_pdb_id_list("1csa,2x2c") == ["1CSA", "2X2C"]
    # unique
    assert resolve_pdb_id_list("probe,1CSA")[0] == "1CSA"


def test_export_batch_dry_run_and_resume(tmp_path: Path):
    dry = export_structure_batch(
        ["1CSA", "2X2C"], {}, out_root=tmp_path / "dry", dry_run=True
    )
    assert dry["dry_run"] is True
    assert dry["ids"] == ["1CSA", "2X2C"]
    assert abs(dry["dual_gate_pin"]["soft_T_n12"] - 0.036) < 1e-12

    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        return  # dry-run already exercised
    kn = load_knobs(kn_path)
    if isinstance(kn, dict) and "best_knobs" in kn:
        kn = kn["best_knobs"]
    root = tmp_path / "res"
    s1 = export_structure_batch(
        ["1CSA"],
        kn,
        out_root=root,
        top_k=1,
        include_coutsias=False,
        with_biopython_check=False,
    )
    assert s1["n_ok"] == 1
    assert (root / "SUMMARY.md").is_file()
    s2 = export_structure_batch(
        ["1CSA"],
        kn,
        out_root=root,
        top_k=1,
        include_coutsias=False,
        with_biopython_check=False,
        resume=True,
    )
    assert s2["n_skipped_resume"] == 1
    assert s2["n_ok"] == 1
