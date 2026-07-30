"""Frequency ordinate factories for null battery (not λ=γ scoring).

Kinds
-----
zeta      — real critical-line ordinates (table / mpmath via zeros.py for windows)
scramble  — exact permutation of ζ gaps (same multiset)
gue       — GUE Wigner surmise spacings (correct null for ζ; Montgomery–Odlyzko)
poisson   — exponential spacings
arith     — constant-gap arithmetic progression (cheapest falsifier)

Deprecated alias: ``goe`` → ``gue`` (historical misname; density was always GUE).
"""

from __future__ import annotations

import numpy as np

from realm.zeta_field import ZETA_ZEROS_IMAG


def _gue_surmise_pdf(s: np.ndarray | float) -> np.ndarray | float:
    """GUE Wigner surmise p(s) = (32/π²) s² exp(-4 s² / π), mean 1."""
    s = np.asarray(s, dtype=float)
    return (32.0 / (np.pi**2)) * (s**2) * np.exp(-4.0 * (s**2) / np.pi)


def _sample_gue_spacings(n: int, rng: np.random.Generator) -> np.ndarray:
    """Sample GUE Wigner-surmise spacings via pure rejection (no mixed proposal).

    Proposal: Exp(1). Envelope constant c=2.5 dominates p(s) on (0, ∞)
    (p peaks ≈0.772 at s=√(π/8)≈0.627). On reject, *retry* the same proposal
    — never fall through to a second independent proposal (that broke the law).
    """
    n = int(n)
    out = np.empty(n, dtype=float)
    c = 2.5
    i = 0
    # safety: expected accept rate is healthy; cap attempts anyway
    attempts = 0
    max_attempts = max(n * 200, 1000)
    while i < n:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError("GUE rejection sampler failed to fill quota")
        s = float(rng.exponential(scale=1.0))
        if s <= 1e-12:
            continue
        p = float(_gue_surmise_pdf(s))
        # accept with prob p / (c e^{-s})
        if rng.random() * c * np.exp(-s) < p:
            out[i] = s
            i += 1
    return out


# Back-compat name used in older docs/tests
_sample_goe_spacings = _sample_gue_spacings


def make_seed(kind: str, k: int, rng: np.random.Generator) -> np.ndarray:
    """Return k increasing positive ordinates for spectral action seed.

    kinds: zeta | scramble | gue | poisson | arith
    alias: goe → gue
    """
    k = max(int(k), 2)
    kind = str(kind).lower().strip()
    if kind == "goe":
        kind = "gue"

    if k > ZETA_ZEROS_IMAG.size:
        # extend ζ table by mean-gap extrapolation if needed (warn-level path;
        # prefer zeros.riemann_zeros_imag / zeros_window for held-out tests)
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

    if kind == "arith":
        # constant-gap progression on the same [g0, g0+span] window as ζ
        mg = span / (k - 1)
        return g0 + mg * np.arange(k, dtype=float)

    if kind == "gue":
        s = _sample_gue_spacings(k - 1, rng)
    elif kind == "poisson":
        s = rng.exponential(1.0, size=k - 1)
    else:
        raise ValueError(f"unknown seed kind: {kind!r}")

    s = s / (float(np.sum(s)) + 1e-15) * span
    return np.concatenate([[g0], g0 + np.cumsum(s)])
