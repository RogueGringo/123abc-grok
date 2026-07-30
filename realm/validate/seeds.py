"""Frequency ordinate factories for null battery (not λ=γ scoring)."""

from __future__ import annotations

import numpy as np

from realm.zeta_field import ZETA_ZEROS_IMAG


def _sample_gue_spacings(n: int, rng: np.random.Generator) -> np.ndarray:
    """Sample Wigner-surmise spacings p(s)=(32/π²)s² exp(-4s²/π) via rejection."""
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
        # extend ζ table by mean-gap extrapolation if needed
        base = ZETA_ZEROS_IMAG.copy()
        mg = float(np.mean(np.diff(base)))
        extra = base[-1] + mg * np.arange(1, k - base.size + 1)
        z_full = np.concatenate([base, extra])
    else:
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
