"""PDB write / handoff export tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from realm.validate.pdb_io import parse_ca_trace
from realm.validate.pdb_write import (
    build_remarks,
    idealized_backbone_from_ca,
    write_backbone_pdb,
    write_ca_pdb,
    write_mold_pair,
)


def _ring(n: int = 11) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([3.8 * np.cos(t), 3.8 * np.sin(t), 0.1 * np.sin(2 * t)])


def test_write_ca_roundtrip(tmp_path: Path):
    xyz = _ring(11)
    path = write_ca_pdb(tmp_path / "m_ca.pdb", xyz, remarks=build_remarks(source="crit", N=11))
    text = path.read_text(encoding="utf-8")
    assert "not_lambda_eq_gamma" in text
    assert "SOURCE crit" in text
    got = parse_ca_trace(text)
    assert got.shape == (11, 3)
    assert float(np.max(np.abs(got - xyz[:, :3]))) < 1e-3  # PDB 3-decimal format


def test_write_backbone_atom_names(tmp_path: Path):
    xyz = _ring(8)
    path = write_backbone_pdb(
        tmp_path / "m_bb.pdb",
        xyz,
        remarks=build_remarks(source="coutsias", N=8, rank_score=0.5),
    )
    text = path.read_text(encoding="utf-8")
    assert text.count(" N  ") >= 8 or text.count(" N ") >= 8
    assert " CA " in text
    assert " C  " in text or " C " in text
    assert " O  " in text or " O " in text
    assert "RANK_SCORE" in text
    bb = idealized_backbone_from_ca(xyz)
    assert bb["CA"].shape == (8, 3)
    assert float(np.max(np.abs(bb["CA"] - xyz[:, :3]))) < 1e-12


def test_write_mold_pair(tmp_path: Path):
    xyz = _ring(10)
    meta = write_mold_pair(
        tmp_path / "molds",
        "000_crit",
        xyz,
        source="crit",
        rank_score=0.42,
        method="test",
    )
    assert Path(meta["path_ca"]).is_file()
    assert Path(meta["path_bb"]).is_file()
    assert meta["N"] == 10


def test_remark_ontology_literal():
    from realm.validate.pdb_write import build_remarks

    lines = build_remarks(source="crit", N=11, rank_score=0.5, method="test")
    joined = "\n".join(lines)
    assert "not_lambda_eq_gamma" in joined
    assert "substrate_crit_projection_not_lambda_eq_gamma" in joined
    assert any(
        "ONTOLOGY substrate_crit_projection_not_lambda_eq_gamma" in line
        for line in lines
    )
    assert any(line.startswith("REMARK") for line in lines)
    assert "SOURCE crit" in joined


def test_soft_T_n12_production_pin():
    """Lock dual-gate soft_T for n=12 without changing production numbers."""
    from realm.validate.length_policy import policy_for

    assert abs(policy_for(12).soft_T - 0.036) < 1e-12
