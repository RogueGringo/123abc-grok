"""Frequency ordinate factories for null battery (not λ=γ scoring)."""

from __future__ import annotations

import numpy as np

from realm.zeta_field import ZETA_ZEROS_IMAG


def cdf_gue(s: np.ndarray | float) -> np.ndarray:
    """Closed-form CDF of the β=2 (GUE) Wigner surmise, unit mean.

    p(s) = (32/π²) s² exp(−4s²/π)  ⇒  F(s) = erf(2s/√π) − (4s/π) exp(−4s²/π)
    """
    from scipy.special import erf

    x = np.asarray(s, dtype=float)
    x = np.maximum(x, 0.0)
    return erf(2.0 * x / np.sqrt(np.pi)) - (4.0 * x / np.pi) * np.exp(
        -4.0 * x**2 / np.pi
    )


def cdf_goe(s: np.ndarray | float) -> np.ndarray:
    """Closed-form CDF of the β=1 (GOE) Wigner surmise, unit mean.

    p(s) = (π/2) s exp(−πs²/4)  ⇒  F(s) = 1 − exp(−πs²/4)
    """
    x = np.asarray(s, dtype=float)
    x = np.maximum(x, 0.0)
    return 1.0 - np.exp(-np.pi * x**2 / 4.0)


def _inverse_cdf_sample(
    cdf, n: int, rng: np.random.Generator, *, s_max: float = 8.0, grid: int = 200_001
) -> np.ndarray:
    """Draw from a unit-mean surmise by inverting its CDF on a fine grid.

    Inverse-CDF is used rather than rejection sampling because it is
    unconditionally correct: there is no envelope to violate and no fallback
    branch that can silently change the target density.
    """
    s = np.linspace(0.0, float(s_max), int(grid))
    c = np.asarray(cdf(s), dtype=float)
    c[0] = 0.0
    c = np.maximum.accumulate(c)  # guard against float non-monotonicity
    u = rng.random(int(n)) * c[-1]
    return np.interp(u, c, s)


def sample_gue_spacings(n: int, rng: np.random.Generator) -> np.ndarray:
    """β=2 (GUE) Wigner-surmise spacings, unit mean. Correct sampler."""
    return _inverse_cdf_sample(cdf_gue, n, rng)


def sample_goe_spacings(n: int, rng: np.random.Generator) -> np.ndarray:
    """β=1 (GOE) Wigner-surmise spacings, unit mean. Correct sampler."""
    return _inverse_cdf_sample(cdf_goe, n, rng)


def _sample_gue_spacings(n: int, rng: np.random.Generator) -> np.ndarray:
    """DEPRECATED — BROKEN. Retained only to reproduce published artifacts.

    Measured against 200,000 draws: matches neither surmise (KS D=0.085 vs GUE,
    0.118 vs GOE, both p≈0), sample mean 0.922 (should be 1), variance 0.135
    (GUE: 0.178). The exponential-proposal branch below is sound — the envelope
    2.5·e^(−s) does dominate p(s), which peaks at 0.772 near s=√(π/8)≈0.627 —
    but on *rejection* it falls through to a second `|N(0.8, 0.4)|` proposal with
    its own accept test instead of retrying. Mixing two proposals that way does
    not sample the target density.

    Use `sample_gue_spacings` (inverse-CDF) for anything new. This function backs
    the `goe_legacy` arm so `null_battery_result.json` and
    `fair_fight_result.json` remain reproducible.
    """
    out = np.empty(n, dtype=float)
    # mode near s~0.8; envelope C * exp(-s) works poorly — use gamma-ish proposal
    i = 0
    # p_max roughly at s=sqrt(pi/8) ≈ 0.626; p≈0.61
    p_peak = 0.65
    while i < n:
        s = rng.exponential(scale=1.0)  # heavy tail ok
        # acceptance ratio vs exponential(1): p(s)/ (c e^{-s})
        p = (32.0 / (np.pi**2)) * (s**2) * np.exp(-4.0 * (s**2) / np.pi)
        c = 2.5  # envelope constant
        if rng.random() * c * np.exp(-s) < p and s > 1e-9:
            out[i] = s
            i += 1
            continue
        # fallback: truncated normal-ish positive
        s2 = abs(rng.normal(0.8, 0.4))
        p2 = (32.0 / (np.pi**2)) * (s2**2) * np.exp(-4.0 * (s2**2) / np.pi)
        if rng.random() * p_peak < p2:
            out[i] = max(s2, 1e-6)
            i += 1
    return out


def make_seed(kind: str, k: int, rng: np.random.Generator) -> np.ndarray:
    """Return k increasing positive ordinates for spectral action seed.

    kinds: zeta | scramble | goe | poisson
    """
    k = max(int(k), 2)
    if k > ZETA_ZEROS_IMAG.size:
        # Never fabricate ordinates. The old mean-gap extrapolation here silently
        # substituted invented values for real zeros, which would have made any
        # held-out-window test a test of extrapolation. Use genuine, verified
        # ordinates instead; raise rather than invent if they are unavailable.
        from realm.validate.zeros import real_zeros

        try:
            z_full = real_zeros(k)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"need {k} genuine zeta ordinates but only "
                f"{ZETA_ZEROS_IMAG.size} are tabulated and they could not be "
                f"computed ({exc}). Refusing to extrapolate."
            ) from exc
    else:
        # Bit-identical to the published path for k <= table size.
        z_full = ZETA_ZEROS_IMAG[:k].copy()

    if kind == "zeta":
        return z_full

    z = z_full
    span = float(z[-1] - z[0])
    g0 = float(z[0])

    if kind == "scramble":
        gaps = np.diff(z).copy()
        rng.shuffle(gaps)
        return np.concatenate([[g0], g0 + np.cumsum(gaps)])

    if kind == "goe":
        s = _sample_gue_spacings(k - 1, rng)
    elif kind == "poisson":
        s = rng.exponential(1.0, size=k - 1)
    else:
        raise ValueError(f"unknown seed kind: {kind!r}")

    s = s / (float(np.sum(s)) + 1e-15) * span
    return np.concatenate([[g0], g0 + np.cumsum(s)])
