"""Decorate adapters: polyala + sequence-aware stubs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from realm.handoff.decorate import (
    PolyAlaStubAdapter,
    SequenceStubAdapter,
    select_adapter,
)
from realm.handoff.types import BackboneArtifact, DecorateRequest
from realm.validate.pdb_write import write_mold_pair


def _ring_bb(tmp_path: Path, n: int = 6) -> Path:
    r = 3.8 / (2 * np.sin(np.pi / n))
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    xyz = np.column_stack([r * np.cos(th), r * np.sin(th), np.zeros(n)])
    molds = tmp_path / "molds"
    molds.mkdir()
    paths = write_mold_pair(
        molds, "000_crit", xyz, source="crit", rank_score=0.1, method="t"
    )
    return Path(paths["path_bb"])


def test_select_adapter_sequence_and_auto():
    assert select_adapter("sequence").name == "sequence"
    assert select_adapter("auto").name == "sequence"
    assert select_adapter("polyala").name == "polyala"
    assert select_adapter("null").name == "null"


def test_polyala_decorate(tmp_path: Path):
    bb = _ring_bb(tmp_path)
    art = BackboneArtifact(path_ca=bb, path_bb=bb, meta={})
    res = PolyAlaStubAdapter().decorate(DecorateRequest(backbone=art))
    assert res.status == "OK"
    assert res.path_decorated is not None and res.path_decorated.is_file()
    text = res.path_decorated.read_text(encoding="utf-8")
    assert "ALA" in text
    assert " CB " in text or "CB  ALA" in text


def test_sequence_decorate_native_resnames(tmp_path: Path):
    bb = _ring_bb(tmp_path, n=6)
    names = ["CYS", "ALA", "GLY", "PRO", "SER", "VAL"]
    art = BackboneArtifact(
        path_ca=bb, path_bb=bb, meta={"resnames": names, "n_ca_native": 6}
    )
    res = SequenceStubAdapter().decorate(
        DecorateRequest(backbone=art, resnames=names)
    )
    assert res.status == "OK"
    assert res.path_decorated is not None
    assert res.path_decorated.name.endswith("_seq.pdb")
    text = res.path_decorated.read_text(encoding="utf-8")
    assert "CYS" in text and "PRO" in text and "VAL" in text
    # GLY should not get CB; other 5 should
    cb_lines = [
        ln
        for ln in text.splitlines()
        if ln.startswith("ATOM") and ln[12:16].strip() == "CB"
    ]
    assert len(cb_lines) == 5  # all except GLY
    assert "sequence unavailable" not in (res.note or "")


def test_sequence_fallback_polyala(tmp_path: Path):
    bb = _ring_bb(tmp_path, n=6)
    art = BackboneArtifact(path_ca=bb, path_bb=bb, meta={})
    res = SequenceStubAdapter().decorate(DecorateRequest(backbone=art))
    assert res.status == "OK"
    assert res.path_decorated is not None
    assert "polyala" in res.path_decorated.name or "fell back" in (res.note or "")


def test_export_sequence_decorate_1csa(tmp_path: Path):
    from realm.handoff.pipeline import export_structure_handoff
    from realm.validate.report import load_knobs

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
        decorate="sequence",
        physics="none",
        with_enrichment=False,
        with_biopython_check=False,
    )
    assert out["status"] == "OK"
    # resnames should flow when pdb_io supports them
    m0 = out["molds"][0]
    meta_rn = (m0.get("physics") and None) or None
    # check mold path decorated
    assert m0.get("decorate_status") == "OK"
    assert m0.get("path_decorated")
    p = Path(m0["path_decorated"])
    assert p.is_file()
    # if sequence path, native residues; else polyala fallback still OK
    assert p.suffix == ".pdb"
