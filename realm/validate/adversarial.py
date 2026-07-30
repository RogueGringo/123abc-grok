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

from realm.validate.seeds import (
    _sample_gue_spacings,
    sample_goe_spacings,
    sample_gue_spacings,
)

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
    "goe",  # DEPRECATED alias of goe_legacy — see below
    "poisson",  # exponential spacings
    # --- correct random-matrix arms (added after the sampler repair) ---
    "gue",  # β=2 Wigner surmise, inverse-CDF. The statistically right null for ζ.
    "goe_true",  # β=1 Wigner surmise, inverse-CDF.
    "goe_legacy",  # the broken sampler the published artifacts used. Reproducibility only.
)

# Explicit, frozen seed ids. Deliberately NOT `KINDS.index(kind)`: with positional
# ids, appending or reordering an arm silently reseeds every arm after it, so old
# and new runs would disagree for reasons unrelated to the science. Assign a new
# integer for each new arm and never reuse or renumber.
ARM_SEED_ID: dict[str, int] = {
    "zeta": 0,
    "arith": 1,
    "geometric": 2,
    "primes": 3,
    "reversed": 4,
    "outlier": 5,
    "sorted_uniform": 6,
    "scramble": 7,
    "goe": 8,
    "poisson": 9,
    "gue": 10,
    "goe_true": 11,
    "goe_legacy": 12,
}

# Historical misnames for the β=2 density, kept as aliases of `gue` so existing
# call sites keep working. Not excluded from claims any more — the underlying
# sampler is repaired — but new work should name `gue` or `goe_true` explicitly.
DEPRECATED = frozenset({"goe", "goe_legacy"})


def arm_seed_id(kind: str) -> int:
    """Stable per-arm integer for RNG seeding.

    `hash(str)` is randomized per process (PYTHONHASHSEED), so using it to seed a
    spectrum draw makes stochastic arms irreproducible across runs *and* across
    pool workers.
    """
    try:
        return ARM_SEED_ID[kind]
    except KeyError as exc:
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

    if kind in ("goe", "goe_legacy"):
        # Historical misnames for the β=2 density. `_sample_gue_spacings` is now
        # repaired (inverse-CDF), so these are aliases of `gue`, not a broken path.
        # Prefer `gue` in new work; prefer `goe_true` for a genuine β=1 null.
        return _span_match(_sample_gue_spacings(n_gaps, rng), g0, span)

    if kind == "gue":
        return _span_match(sample_gue_spacings(n_gaps, rng), g0, span)

    if kind == "goe_true":
        return _span_match(sample_goe_spacings(n_gaps, rng), g0, span)

    if kind == "poisson":
        return _span_match(rng.exponential(1.0, size=n_gaps), g0, span)

    raise ValueError(f"unknown adversarial kind: {kind!r}")
