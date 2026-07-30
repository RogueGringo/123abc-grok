"""Stage 9 rigidity tournament tests."""

from __future__ import annotations

import numpy as np

from realm.validate.length_policy import policy_for
from realm.validate.stage9_tournament import (
    bonferroni,
    monte_carlo_spectrum_p,
    run_rigidity_tournament,
)


def test_dual_gate_pin():
    assert abs(policy_for(12, base_beta=0.20).soft_T - 0.036) < 1e-12


def test_monte_carlo_floor():
    # zeta best (lowest) among all → n_extreme=1 (itself tie only if equals)
    z = 0.01
    nulls = [0.02, 0.03, 0.04]
    r = monte_carlo_spectrum_p(z, nulls, lower_is_better=True)
    assert r["M"] == 3
    assert r["n_extreme"] == 0  # no null ≤ zeta
    assert abs(r["p"] - 1.0 / 4.0) < 1e-12  # (0+1)/(3+1)
    assert abs(r["floor"] - 0.25) < 1e-12


def test_monte_carlo_when_nulls_better():
    z = 0.05
    nulls = [0.01, 0.02, 0.03, 0.04]
    r = monte_carlo_spectrum_p(z, nulls, lower_is_better=True)
    assert r["n_extreme"] == 4
    assert abs(r["p"] - 1.0) < 1e-12  # (4+1)/(4+1)


def test_bonferroni():
    assert abs(bonferroni(0.02, 3) - 0.06) < 1e-12
    assert bonferroni(0.5, 3) == 1.0


def test_tournament_small_m_smoke():
    """Structural smoke at M=5 (not powered)."""
    out = run_rigidity_tournament(
        M=5,
        n_windows=3,
        n_zeros=14,
        stochastic_arms=("gue", "poisson"),
        deterministic_arms=("arith",),
        base_seed=0,
    )
    assert out["stage"] == 9
    assert out["M"] == 5
    assert "gue" in out["stochastic"]
    assert out["stochastic"]["gue"]["monte_carlo"]["M"] == 5
    assert "arith" in out["deterministic"]
    assert out["summary"]["dual_gate_soft_T_12"] == 0.036
    assert out["ontology"].endswith("not_lambda_eq_gamma")


def test_component_tournament_tiny_smoke():
    from pathlib import Path

    import pytest

    from realm.validate.stage9_tournament import run_component_tournament
    from realm.validate.window_filtration import load_champion_knobs

    if not Path("evolve_result.json").is_file():
        pytest.skip("need evolve_result.json")
    kn = load_champion_knobs()
    out = run_component_tournament(
        kn,
        M=2,
        n_windows=2,
        n_zeros=14,
        N=13,
        n_sectors=6,
        carriers=("stationarity", "density_return_l1"),
        stochastic_arms=("gue",),
        base_seed=0,
    )
    assert out["stage"] == "9-component"
    assert "stationarity" in out["by_carrier"]
    assert out["by_carrier"]["stationarity"]["stochastic"]["gue"]["monte_carlo"]["M"] == 2
    assert out["summary"]["dual_gate_soft_T_12"] == 0.036
    assert out["ontology"].endswith("not_lambda_eq_gamma")
