"""Fold protocol + AQFT local net proxies."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from realm.aqft_local import aqft_dual_report, net_consistency
from realm.fold_protocol import (
    forge_with_substrate,
    rank_enrichment,
    select_mold_for_substrate,
)
from realm.validate.dual import OperatorFingerprint, operator_fingerprint


def _knobs():
    p = Path("evolve_result.json")
    if not p.is_file():
        pytest.skip("need evolve_result.json")
    return json.loads(p.read_text(encoding="utf-8"))["best_knobs"]


def test_aqft_net_on_fingerprint():
    th = np.linspace(0.2, 5.0, 6)
    op = operator_fingerprint(th, N=9, prefer_maxop=False)
    rep = aqft_dual_report(op)
    assert len(rep["local_observables"]) == 6
    assert "adjacent_gap_corr" in rep["net"]
    assert rep["ontology"].startswith("aqft_dual")


def test_forge_substrates_equal_interface():
    kn = _knobs()
    rng = np.random.default_rng(0)
    for kind in ("zeta", "arith", "poisson"):
        pack = forge_with_substrate(
            kn,
            kind=kind,
            N=11,
            n_zeros=14,
            n_sectors=6,
            multimode=False,
            rng=rng,
        )
        assert len(pack["templates"]) >= 1
        assert pack["operator"].gaps.size >= 1


def test_select_mold_and_rank_smoke():
    kn = _knobs()
    # unit circle synthetic "native"
    t = np.linspace(0, 2 * np.pi, 11, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.02 * np.sin(2 * t)])
    pack, diag = select_mold_for_substrate(
        xyz, kn, kind="zeta", n_zeros=14, soft_T=0.04, rng=np.random.default_rng(1)
    )
    assert diag["n_bank"] == 10  # 2 multimode × 5 omega
    enr = rank_enrichment(
        xyz,
        pack,
        n_decoys=8,
        n_seeds=1,
        soft_T=0.04,
        rng=np.random.default_rng(2),
    )
    assert 0.0 <= enr["enrichment"] <= 1.0
