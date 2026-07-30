"""Adversarial spectra for the falsifiability diagnostic.

The null battery's scramble/GOE/Poisson arms are all *plausible* spectra. They
cannot answer the prior question: can the forge drive F toward zero for
**anything**? These seeds are deliberately structureless or absurd. If any of
them reaches F comparable to ζ under an equal tuning budget, the framework has
no discriminating power and every downstream result is vacuous.

Every seed is span-matched to a reference window (same γ_0, same total span), so
scale is never the discriminator — consistent with `realm.validate.seeds`.
"""

from __future__ import annotations

import numpy as np

from realm.validate.seeds import _sample_gue_spacings

# Seeds whose spectrum is fully determined (no RNG); reps differ only by optimizer path.
DETERMINISTIC = frozenset({"zeta", "arith", "geometric", "primes", "reversed", "outlier"})

KINDS = (
    "zeta",  # control
    "arith",  # constant gap — maximally regular, zero information
    "geometric",  # smoothly growing gaps
    "primes",  # arithmetic object, wrong one
    "reversed",  # ζ gaps in reverse order (a specific scramble)
    "outlier",  # constant gaps + one dominating gap
    "sorted_uniform",  # sorted uniform draws
    "scramble",  # ζ gap multiset, permuted
    "goe",  # Wigner-surmise spacings
    "poisson",  # exponential spacings
)


def arm_seed_id(kind: str) -> int:
    """Stable per-arm integer for RNG seeding.

    `hash(str)` is randomized per process (PYTHONHASHSEED), so using it to seed a
    spectrum draw makes stochastic arms irreproducible across runs *and* across
    pool workers. Index into KINDS instead.
    """
    try:
        return KINDS.index(kind)
    except ValueError as exc:
        raise ValueError(f"unknown adversarial kind: {kind!r}") from exc


def _primes(n: int) -> np.ndarray:
    out: list[int] = []
    cand = 2
    while len(out) < n:
        if all(cand % p for p in out if p * p <= cand):
            out.append(cand)
        cand += 1
    return np.array(out, dtype=float)


def _span_match(spacings: np.ndarray, g0: float, span: float) -> np.ndarray:
    s = np.asarray(spacings, dtype=float)
    s = np.abs(s) + 1e-12
    s = s / (float(np.sum(s)) + 1e-15) * span
    return np.concatenate([[g0], g0 + np.cumsum(s)])


def make_adversarial_seed(
    kind: str,
    k: int,
    rng: np.random.Generator,
    *,
    base: np.ndarray,
) -> np.ndarray:
    """`k` increasing positive ordinates of the given kind, span-matched to `base`.

    `base` is the reference ζ window (real ordinates, length >= k).
    """
    k = max(int(k), 2)
    b = np.asarray(base, dtype=float).ravel()[:k]
    if b.size < k:
        raise ValueError(f"base window too short: {b.size} < {k}")

    if kind == "zeta":
        return b.copy()

    g0 = float(b[0])
    span = float(b[-1] - b[0])
    n_gaps = k - 1

    if kind == "arith":
        return _span_match(np.ones(n_gaps), g0, span)

    if kind == "geometric":
        return _span_match(np.power(1.25, np.arange(n_gaps)), g0, span)

    if kind == "primes":
        return _span_match(np.diff(_primes(k)), g0, span)

    if kind == "reversed":
        return _span_match(np.diff(b)[::-1], g0, span)

    if kind == "outlier":
        s = np.ones(n_gaps)
        s[n_gaps // 2] = float(n_gaps)
        return _span_match(s, g0, span)

    if kind == "sorted_uniform":
        return _span_match(rng.random(n_gaps), g0, span)

    if kind == "scramble":
        gaps = np.diff(b).copy()
        rng.shuffle(gaps)
        return _span_match(gaps, g0, span)

    if kind == "goe":
        return _span_match(_sample_gue_spacings(n_gaps, rng), g0, span)

    if kind == "poisson":
        return _span_match(rng.exponential(1.0, size=n_gaps), g0, span)

    raise ValueError(f"unknown adversarial kind: {kind!r}")
