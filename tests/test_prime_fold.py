"""Prime fold: Coutsias → sheaf L spectral action."""

from __future__ import annotations

import numpy as np

from realm.prime_fold import (
    PrimeFoldingEngine,
    spectral_zeta_action,
    score_closed_geometry,
)
from realm.coutsias import CoutsiasKinematics


def test_spectral_zeta_action_basic():
    e = np.array([0.0, 0.5, 1.0, 2.0])
    a = spectral_zeta_action(e, s=2.0)
    # 1/0.25 + 1 + 0.25 = 4 + 1 + 0.25
    assert abs(a - (4.0 + 1.0 + 0.25)) < 1e-9
    assert spectral_zeta_action([0.0, 0.0], s=2.0) == float("inf")


def test_score_closed_geometry_finite():
    kin = CoutsiasKinematics(N=8, n_starts=8, use_de=False, rng_seed=0, residual_tol=0.8)
    geoms = kin.find_real_roots()
    assert len(geoms) >= 1
    sc = score_closed_geometry(geoms[0], N=8, prefer_maxop=False, s=2.0)
    assert np.isfinite(sc["total"])
    assert sc["spectral_action"] > 0
    assert "not_lambda_eq_gamma" in sc["ontology"]


def test_prime_fold_engine_smoke():
    eng = PrimeFoldingEngine(
        N=8,
        n_starts=10,
        use_de=False,
        prefer_maxop=False,
        residual_tol=0.8,
        rng_seed=1,
    )
    out = eng.execute_folding(max_roots=4)
    assert out.status == "success"
    assert out.coordinates is not None
    assert out.coordinates.shape[1] == 3
    assert out.coordinates.shape[0] >= 6
    assert out.score["total"] <= out.candidates[0]["total"] + 1e-12
    d = out.to_dict()
    assert d["never"] == ["lambda_eq_gamma"]
    assert "Coutsias" in d["pipeline"]
