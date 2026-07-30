"""Structural audit: most of the residual weight is zero by construction.

`derive.py:410` fills the sector pool from the critical *minima* of the spectral
action, and `build_key` takes `key.thetas` to be those sector twists while
`build_lock` takes `lock.minima_theta` from the same critical minima. So whenever
the action yields at least `n_sectors` minima, the lock and the key are the same
set of numbers, and the residual terms that compare them vanish identically:

| term            | weight in R | why it is zero            |
|-----------------|-------------|---------------------------|
| stationarity    | 0.30        | keys are critical points, where dS = 0 |
| crit_coverage   | 0.25        | minima are always a subset of keys     |
| pin_align       | 0.20 x 0.40 | the two sets coincide                  |
| theta_ladder_l1 | 0.20 x 0.35 | the two sets coincide                  |

That is 0.70 of the total weight. It is *not* a ζ property — it holds for
arithmetic progressions and Poisson spectra alike. These tests pin the fact down
so that a future change which makes R meaningful (or makes it worse) is visible.

None of this says the geometry is wrong. It says a low R is not by itself
evidence that the seed spectrum is special.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.validate.adversarial import make_adversarial_seed
from realm.validate.zeros import real_zeros

EVOLVE = Path("evolve_result.json")
K = 14
N = 13

# Weights from realm/lock_key.py:263 and the return_map_err blend at :300
W_STATIONARITY = 0.30
W_COVERAGE = 0.25
W_PIN = 0.20 * 0.40
W_LADDER = 0.20 * 0.35
TAUTOLOGICAL_WEIGHT = W_STATIONARITY + W_COVERAGE + W_PIN + W_LADDER

needs_evolve = pytest.mark.skipif(not EVOLVE.is_file(), reason="champion knobs absent")


@pytest.fixture(scope="module")
def champion():
    return json.loads(EVOLVE.read_text(encoding="utf-8"))["best_knobs"]


@pytest.fixture(autouse=True)
def _quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def _forge(knobs, gammas, n_sectors):
    der = Keymaker(N=N, n_zeros=int(gammas.size), n_sectors=n_sectors).forge(
        **knobs, gammas=gammas
    )
    lock = build_lock(der)
    key = build_key(der)
    return key, lock, residual(lock, key, action=der.action)


def test_tautological_weight_is_seventy_percent():
    assert TAUTOLOGICAL_WEIGHT == pytest.approx(0.70)


@needs_evolve
def test_keys_are_exactly_the_lock_minima_at_sectors_6(champion):
    """The seal configuration compares a set of numbers against itself."""
    key, lock, res = _forge(champion, real_zeros(K), 6)
    kt, mt = np.sort(key.thetas), np.sort(lock.minima_theta)
    assert kt.size == mt.size == 6
    assert np.allclose(kt, mt, atol=1e-12)
    assert res.diagnostics["pin_align"] == pytest.approx(0.0, abs=1e-12)
    assert res.diagnostics["theta_ladder_l1"] == pytest.approx(0.0, abs=1e-12)
    assert res.crit_coverage == pytest.approx(0.0, abs=1e-12)
    assert res.shape_l1 < 1e-9  # stationarity: dS = 0 at critical points


@needs_evolve
@pytest.mark.parametrize(
    "kind", ["zeta", "arith", "primes", "outlier", "sorted_uniform", "goe", "poisson"]
)
def test_degeneracy_is_not_zeta_specific(champion, kind):
    """Structureless spectra get the same free zeros ζ does."""
    g = make_adversarial_seed(kind, K, np.random.default_rng(0), base=real_zeros(K))
    key, lock, res = _forge(champion, g, 6)
    if lock.minima_theta.size < 6:
        pytest.skip(f"{kind} yields only {lock.minima_theta.size} minima")
    assert res.diagnostics["pin_align"] == pytest.approx(0.0, abs=1e-12)
    assert res.diagnostics["theta_ladder_l1"] == pytest.approx(0.0, abs=1e-12)
    assert res.shape_l1 < 1e-9


@needs_evolve
@pytest.mark.parametrize("kind", ["zeta", "arith", "geometric", "goe", "poisson"])
def test_crit_coverage_is_always_zero(champion, kind):
    """Minima are drawn into the key pool first, so coverage can never be nonzero."""
    g = make_adversarial_seed(kind, K, np.random.default_rng(0), base=real_zeros(K))
    _, _, res = _forge(champion, g, 6)
    assert res.crit_coverage == pytest.approx(0.0, abs=1e-12)


@needs_evolve
@pytest.mark.parametrize("n_sectors", [8, 10, 12])
def test_extra_sectors_break_the_coincidence(champion, n_sectors):
    """Above the minima count, keys get filled from non-minima and pin/ladder wake up.

    This is why sec_scale_result.json degrades monotonically past sectors=6: it is
    the coincidence breaking, not a scale-dependent physical relation.
    """
    key, lock, res = _forge(champion, real_zeros(K), n_sectors)
    assert key.thetas.size == n_sectors
    assert lock.minima_theta.size < n_sectors
    assert res.diagnostics["pin_align"] > 0.0


@needs_evolve
def test_corr_term_is_fit_on_six_points(champion):
    """The one heavy informative term is |Pearson r| over n_sectors points.

    With 8 free knobs and 6 points, |r| ~ 1 is nearly free, so a high
    corr_S_lambda is not strong evidence either.
    """
    key, _, res = _forge(champion, real_zeros(K), 6)
    assert key.S_at.size == 6
    assert key.spectral_gaps.size == 6
    assert res.diagnostics["corr_S_lambda"] > 0.999


@needs_evolve
def test_residual_is_dominated_by_density_return(champion):
    """R at the champion point is ~0.05 x dens_return; everything else is ~0."""
    _, _, res = _forge(champion, real_zeros(K), 6)
    dens = res.diagnostics["density_return_l1"]
    assert res.total == pytest.approx(0.20 * 0.25 * dens, rel=0.02)
