"""GUE Wigner-surmise rejection sampler — distributional checks."""

from __future__ import annotations

import numpy as np

from realm.validate.seeds import _gue_surmise_pdf, _sample_gue_spacings


def _gue_cdf_grid(s: np.ndarray) -> np.ndarray:
    """Numerical CDF of GUE surmise on sorted s via integrate pdf."""
    # use scipy integration of pdf on dense grid then interp
    grid = np.linspace(0.0, max(8.0, float(s.max()) + 1.0), 4000)
    pdf = _gue_surmise_pdf(grid)
    # trapezoid CDF
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (pdf[1:] + pdf[:-1]) * np.diff(grid))])
    cdf = cdf / (cdf[-1] + 1e-15)
    return np.interp(s, grid, cdf)


def test_gue_sampler_mean_near_one():
    rng = np.random.default_rng(0)
    s = _sample_gue_spacings(50_000, rng)
    # mean of GUE surmise is 1
    assert abs(float(np.mean(s)) - 1.0) < 0.02


def test_gue_sampler_ks_not_rejected():
    rng = np.random.default_rng(1)
    s = _sample_gue_spacings(20_000, rng)
    # KS against numerical GUE CDF
    cdf_vals = _gue_cdf_grid(np.sort(s))
    # manual KS: max |ecdf - cdf|
    n = s.size
    ecdf = np.arange(1, n + 1) / n
    D = float(np.max(np.abs(ecdf - cdf_vals)))
    # critical value approx 1.36/sqrt(n) at 5%
    crit = 1.36 / np.sqrt(n)
    assert D < crit * 1.5  # modest slack for numerical CDF error


def test_gue_not_goe_surmise_mean_ok_but_var():
    """Variance of GUE surmise ≈ 0.178; GOE ≈ 0.273."""
    rng = np.random.default_rng(2)
    s = _sample_gue_spacings(40_000, rng)
    var = float(np.var(s))
    # GUE: 3π/8 - 1 ≈ 0.178
    assert abs(var - (3 * np.pi / 8 - 1)) < 0.03
