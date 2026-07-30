"""Refit engine: reproduces the published objective, and stays fair across arms."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from realm.validate.adversarial import make_adversarial_seed
from realm.validate.refit import (
    BOUNDS,
    N_DIM,
    knobs_to_vec,
    refit,
    refit_job,
    score_gammas,
    vec_to_knobs,
)
from realm.validate.zeros import real_zeros

EVOLVE = Path("evolve_result.json")
PUBLISHED_F_ZETA = 0.004532164789813  # null_battery_result.json means.zeta.F

needs_evolve = pytest.mark.skipif(
    not EVOLVE.is_file(), reason="evolve_result.json (champion knobs) not present"
)


@pytest.fixture(scope="module")
def champion():
    return json.loads(EVOLVE.read_text(encoding="utf-8"))["best_knobs"]


@needs_evolve
def test_reproduces_published_f_zeta(champion):
    """The new scorer must agree with the published null-battery number exactly.

    This is the validity anchor: every claim built on score_gammas depends on it
    walking the same forge/residual/mold path as harness.score_configuration.
    """
    g = real_zeros(14)
    vec = knobs_to_vec(champion, float(g[-1]))
    out = score_gammas(vec, gammas=g, N=13, n_sectors=6)
    assert out["F"] == pytest.approx(PUBLISHED_F_ZETA, rel=1e-9)
    assert out["R"] == pytest.approx(PUBLISHED_F_ZETA, rel=1e-9)
    assert out["occupancy"] == pytest.approx(1.0)


@needs_evolve
def test_knob_vector_roundtrip(champion):
    g_last = float(real_zeros(14)[-1])
    vec = knobs_to_vec(champion, g_last)
    back = vec_to_knobs(vec, g_last)
    for key, value in back.items():
        assert value == pytest.approx(float(champion[key]), rel=1e-12)


@needs_evolve
def test_champion_v0_is_dimensionless_and_in_bounds(champion):
    """v[0] is Lambda/g_last; evolve.py:506 bounds are dimensionless."""
    g_last = float(real_zeros(14)[-1])
    vec = knobs_to_vec(champion, g_last)
    assert len(vec) == N_DIM
    for v, (lo, hi) in zip(vec, BOUNDS):
        assert lo - 1e-9 <= v <= hi + 1e-9


def test_score_gammas_handles_infeasible_knobs():
    """DE explores infeasible corners; those must score badly, not raise."""
    g = real_zeros(14)
    out = score_gammas(np.array([4.5, 2.9, 2.9, 0.80, 3.8, 1.2, 1.2, 1.2]), gammas=g)
    assert np.isfinite(out["F"])
    assert out["F"] > 0


def test_refit_improves_over_random_start():
    g = real_zeros(14)
    out = refit(g, popsize=4, maxiter=3, polish_iter=10, de_seed=0, label="t")
    lo = np.array([b[0] for b in BOUNDS])
    hi = np.array([b[1] for b in BOUNDS])
    rng = np.random.default_rng(0)
    random_F = min(
        float(score_gammas(lo + rng.random(N_DIM) * (hi - lo), gammas=g)["F"])
        for _ in range(40)
    )
    assert out["F"] <= random_F


def test_refit_reports_fairness_invariants():
    """Budget must be identical across arms: no warm start, no early exit."""
    out = refit(real_zeros(14), popsize=4, maxiter=3, polish_iter=5, de_seed=1)
    assert out["budget"]["warm_start"] is False
    assert out["budget"]["early_stop_disabled"] is True
    conv = out["convergence"]
    assert conv["n_eval"] > 0
    assert 0.0 <= conv["best_at_budget_fraction"] <= 1.0
    assert conv["polish_gain"] >= -1e-12  # polish may find nothing, never worsens best


def test_identical_budget_across_arms():
    """Two different spectra, same budget => same evaluation count."""
    base = real_zeros(14)
    counts = []
    for kind in ("zeta", "arith"):
        g = make_adversarial_seed(kind, 14, np.random.default_rng(0), base=base)
        out = refit(g, popsize=4, maxiter=4, polish_iter=0, de_seed=7)
        counts.append(out["convergence"]["evals_de"])
    assert counts[0] == counts[1], f"budget differed across arms: {counts}"


def test_refit_job_decouples_spectrum_from_optimizer():
    """Same spectrum draw, different instance => different search path."""
    base = real_zeros(14).tolist()
    payload = {
        "kind": "arith",  # deterministic spectrum
        "base": base,
        "k": 14,
        "popsize": 4,
        "maxiter": 3,
        "polish_iter": 0,
        "master_seed": 5,
    }
    a = refit_job({**payload, "instance": 0})
    b = refit_job({**payload, "instance": 1})
    assert np.allclose(a["gammas"], b["gammas"]), "arith spectrum should be identical"
    assert a["deterministic_spectrum"] is True
    assert a["best_vec"] != b["best_vec"], "optimizer paths should differ by instance"
