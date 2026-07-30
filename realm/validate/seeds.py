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


def _gue_surmise_pdf(s: np.ndarray | float) -> np.ndarray | float:
    """GUE Wigner surmise p(s) = (32/π²) s² exp(−4s²/π), unit mean."""
    x = np.asarray(s, dtype=float)
    return (32.0 / (np.pi**2)) * (x**2) * np.exp(-4.0 * (x**2) / np.pi)


def _sample_gue_spacings(n: int, rng: np.random.Generator) -> np.ndarray:
    """β=2 (GUE) spacings. Delegates to the inverse-CDF sampler.

    Two independent repairs of this function converged from different branches.
    Both correctly identified the original defect — a rejection loop that fell
    through to a second `|N(0.8, 0.4)|` proposal instead of retrying, which
    sampled neither surmise (KS D=0.085 vs GUE, 0.118 vs GOE, both p≈0 at
    n=200k; mean 0.922, variance 0.135 vs GUE's 0.178).

    The pure-rejection repair (retry the same Exp(1) proposal, envelope c=2.5) is
    *nearly* right, but the envelope does not actually dominate everywhere:
    measured, p(s) > 2.5·e^(−s) on s ∈ [1.0355, 1.1738], peak ratio 1.0101. A
    violated envelope biases the accepted sample by roughly that margin in that
    band. Inverse-CDF sampling is used instead because it has no envelope to
    violate and no branch that can silently change the target density.
    """
    return _inverse_cdf_sample(cdf_gue, n, rng)


# Back-compat name from main. NOTE: main's `_sample_goe_spacings` was an alias for
# the GUE sampler (the arm was misnamed, the density was always β=2). The true β=1
# sampler is `sample_goe_spacings` — no leading underscore. Kept distinct on purpose.
_sample_goe_spacings = _sample_gue_spacings


def make_seed(kind: str, k: int, rng: np.random.Generator) -> np.ndarray:
    """Return k increasing positive ordinates for spectral action seed.

    kinds: zeta | scramble | gue | poisson | arith
    alias: goe → gue (historical misname; the density was always β=2)
    """
    k = max(int(k), 2)
    kind = str(kind).lower().strip()
    if kind == "goe":
        kind = "gue"
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

    if kind == "arith":
        # Constant-gap progression on the same [g0, g0+span] window as ζ.
        # The cheapest falsifier: 13 identical gaps, so every ordering is the same
        # object. It beat ζ under equal budget (F 0.002040 vs 0.004421).
        return g0 + (span / (k - 1)) * np.arange(k, dtype=float)

    if kind == "gue":
        s = _sample_gue_spacings(k - 1, rng)
    elif kind == "goe_true":
        s = sample_goe_spacings(k - 1, rng)
    elif kind == "poisson":
        s = rng.exponential(1.0, size=k - 1)
    else:
        raise ValueError(f"unknown seed kind: {kind!r}")

    s = s / (float(np.sum(s)) + 1e-15) * span
    return np.concatenate([[g0], g0 + np.cumsum(s)])
