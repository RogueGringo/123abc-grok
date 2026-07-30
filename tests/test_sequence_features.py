"""Sequence chemistry → sheaf residual weights."""

from __future__ import annotations

import numpy as np

from realm.sequence_features import (
    aa_feature_matrix,
    sequence_residue_weights,
)
from realm.sheaf_defects import softmin_defect_vs_crit
from realm.validate.length_policy import policy_for
from realm.validate.pdb_io import load_ca_cyclic_band


def test_aa_features_and_weights():
    names = ["ALA", "LEU", "ASP", "LYS"]
    M = aa_feature_matrix(names)
    assert M.shape == (4, 3)
    w0 = sequence_residue_weights(names, mix=0.0)
    assert w0 is None
    w = sequence_residue_weights(names, mix=0.2)
    assert w is not None
    assert w.shape == (4,)
    assert abs(float(np.mean(w)) - 1.0) < 1e-9
    assert float(np.min(w)) >= 0.25


def test_seq_mix_policy():
    # production locked off; override still available for probes
    assert policy_for(8).seq_mix == 0.0
    assert policy_for(10).seq_mix == 0.0
    assert policy_for(12).seq_mix == 0.0
    assert policy_for(13).seq_mix == 0.0
    from realm.validate.length_policy import adaptive_seq_mix

    assert abs(adaptive_seq_mix(13, override=0.12) - 0.12) < 1e-12


def test_load_resnames_and_sequence_defect():
    from pathlib import Path

    import pytest

    pdb_path = Path("data/pdb/1CSA.pdb")
    if not pdb_path.is_file():
        pytest.skip("data/pdb/1CSA.pdb not present (gitignored RCSB cache)")

    xyz, names, ch = load_ca_cyclic_band(
        str(pdb_path), lo=6, hi=40, with_resnames=True
    )
    assert xyz.shape[0] == len(names)
    assert all(isinstance(n, str) and n for n in names)
    w = sequence_residue_weights(names, mix=0.1)
    th = [0.3, 1.0, 2.0]
    plain = softmin_defect_vs_crit(
        xyz, th, soft_T=0.05, prefer_maxop=False, residue_weights=None
    )
    seq = softmin_defect_vs_crit(
        xyz, th, soft_T=0.05, prefer_maxop=False, residue_weights=w
    )
    assert seq["method"] == "SHEAF_DEFECT_SEQUENCE"
    assert seq["sequence_weighted"] is True
    # sequence reweight should change the softmin (not a no-op)
    assert abs(float(seq["mean_dist"]) - float(plain["mean_dist"])) > 1e-9
