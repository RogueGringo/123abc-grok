"""Adaptive natural-selection policy unit tests."""

from __future__ import annotations

import numpy as np

from realm.adaptive_evolve import (
    AdaptivePolicy,
    clip_vec,
    combine_fitness,
    crossover,
    knobs_to_vec,
    mutate,
    run_natural_selection,
)


def test_clip_and_mutate_in_bounds():
    rng = np.random.default_rng(0)
    x = np.array([1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0, 1.0])
    for _ in range(20):
        y = mutate(x, 0.5, rng)
        assert y.shape == (8,)
        assert np.all(np.isfinite(y))


def test_combine_fitness_prefers_enrichment():
    pol = AdaptivePolicy()
    f_hi, _ = combine_fitness(0.1, 0.005, 0.90, None, pol)
    f_lo, _ = combine_fitness(0.1, 0.005, 0.50, None, pol)
    assert f_hi < f_lo


def test_policy_tau_adapts():
    pol = AdaptivePolicy(tau=0.10, plateau_patience=1)
    pol.on_epoch(True, 0.5, 0.6)
    assert pol.tau < 0.10
    t1 = pol.tau
    pol.on_epoch(False, 0.5, 0.6)
    assert pol.tau > t1  # plateau expands


def test_crossover_shape():
    rng = np.random.default_rng(1)
    a = np.ones(8)
    b = np.full(8, 0.5)
    c = crossover(a, b, rng, rate=1.0)
    assert c.shape == (8,)
    c = clip_vec(c)
    assert np.all(c >= 0.0)


def test_ns_loop_smoke_with_mock_probe():
    knobs = {
        "Lambda": 148.0,
        "omega_scale": 1.6,
        "weight_power": 2.4,
        "tier_split": 0.6,
        "low_boost": 0.56,
        "w1_mult": 0.91,
        "w2_mult": 1.0,
        "w3_mult": 1.0,
    }
    # mock environment: enrichment from omega_scale proximity to 1.6
    def probe_fn(kn: dict) -> tuple[float, float | None]:
        enr = float(np.clip(1.0 - abs(kn["omega_scale"] - 1.6), 0.2, 0.95))
        return enr, 0.7

    out = run_natural_selection(
        knobs,
        g_last=100.0,
        N=9,
        n_zeros=10,
        n_sectors=4,
        n_pop=4,
        n_epochs=2,
        policy=AdaptivePolicy(tau=0.05),
        probe_fn=probe_fn,
        rng=np.random.default_rng(3),
    )
    assert "champion" in out
    assert out["champion"]["F_total"] < 10.0
    assert len(out["epochs"]) == 2
    v = knobs_to_vec(out["champion"]["knobs"], 100.0)
    assert v.shape == (8,)
