"""Pin the residual-instrument falsification (2026-07-29).

Legacy R is largely zero by construction when keys are Crit minima.
Informative R is density-return only.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.validate.seeds import make_seed


def _champion_knobs() -> dict:
    p = Path("evolve_result.json")
    if not p.is_file():
        pytest.skip("need evolve_result.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("best_knobs") or data.get("meet_knobs")


def test_lock_key_coincidence_under_zeta_seal():
    kn = _champion_knobs()
    der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(**kn)
    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action, fitness="legacy")
    # keys drawn from minima → coincidence
    assert res.diagnostics["lock_key_coincidence"] < 1e-9
    assert res.diagnostics["degenerate_seating"] == 1.0
    # tautological terms ~ 0
    assert res.shape_l1 < 1e-6
    assert res.crit_coverage < 1e-9
    assert res.diagnostics["pin_align"] < 1e-9
    assert res.diagnostics["theta_ladder_l1"] < 1e-9


def test_informative_equals_density_return():
    kn = _champion_knobs()
    der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(**kn)
    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action, fitness="informative")
    dens = res.diagnostics["density_return_l1"]
    assert abs(res.total - dens) < 1e-12
    assert res.fitness_mode == "informative"
    # legacy is much smaller than dens when dens ~ 0.09 and tautologies vanish
    assert res.diagnostics["legacy_total"] < 0.05
    assert dens > res.diagnostics["legacy_total"]


def test_legacy_is_fraction_of_density_return_weight():
    """R_legacy ≈ 0.20 * 0.25 * dens = 0.05 * dens when tautologies vanish."""
    kn = _champion_knobs()
    der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(**kn)
    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action, fitness="legacy")
    dens = res.diagnostics["density_return_l1"]
    # only dens_ret and tiny corr remain
    expected_floor = 0.20 * 0.25 * dens  # return weight * dens share
    assert res.total >= expected_floor - 1e-6
    # and close to floor + small corr contribution
    assert res.total < expected_floor + 0.05


@pytest.mark.parametrize(
    "kind",
    ["zeta", "arith", "poisson", "gue", "scramble"],
)
def test_crit_coverage_zero_when_enough_minima(kind):
    """crit_coverage is 0 for any spectrum that yields enough minima."""
    kn = _champion_knobs()
    g = make_seed(kind, 14, np.random.default_rng(0))
    der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(**{**kn, "gammas": g})
    lock = build_lock(der)
    key = build_key(der)
    n_min = int(lock.minima_theta.size)
    res = residual(lock, key, action=der.action, fitness="informative")
    if n_min >= len(key.thetas):
        assert res.crit_coverage < 1e-9
        assert res.diagnostics["degenerate_seating"] == 1.0


def test_arith_seed_constant_gaps():
    g = make_seed("arith", 14, np.random.default_rng(0))
    d = np.diff(g)
    assert np.allclose(d, d[0])


def test_goe_alias_is_gue():
    a = make_seed("gue", 10, np.random.default_rng(1))
    b = make_seed("goe", 10, np.random.default_rng(1))
    assert np.allclose(a, b)
