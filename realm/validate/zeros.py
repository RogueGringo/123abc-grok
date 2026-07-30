"""Genuine Riemann zero ordinates (mpmath) — not mean-gap extrapolation.

Used by transfer / held-out windows so off-table scores test ζ, not
extrapolation of ZETA_ZEROS_IMAG.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from realm.zeta_field import ZETA_ZEROS_IMAG


@lru_cache(maxsize=4)
def riemann_zeros_imag(n: int) -> np.ndarray:
    """First n positive imaginary parts of non-trivial zeros (sorted)."""
    n = int(n)
    if n < 1:
        raise ValueError("n >= 1")
    # Prefer mpmath for extension past the hardcoded seed table
    try:
        from mpmath import zetazero
    except ImportError as exc:  # pragma: no cover
        if n <= ZETA_ZEROS_IMAG.size:
            return ZETA_ZEROS_IMAG[:n].copy()
        raise ImportError("mpmath required for zeros beyond the seed table") from exc

    g = np.array([float(zetazero(k).imag) for k in range(1, n + 1)], dtype=float)
    return g


def zeros_window(start: int, count: int) -> np.ndarray:
    """1-based inclusive start index; return `count` consecutive ordinates."""
    start = int(start)
    count = int(count)
    if start < 1 or count < 2:
        raise ValueError("need start>=1 and count>=2")
    full = riemann_zeros_imag(start + count - 1)
    return full[start - 1 : start - 1 + count].copy()


def verify_seed_table(atol: float = 1e-9) -> dict:
    """Cross-check hardcoded ZETA_ZEROS_IMAG against mpmath."""
    n = int(ZETA_ZEROS_IMAG.size)
    mp = riemann_zeros_imag(n)
    err = float(np.max(np.abs(mp - ZETA_ZEROS_IMAG[:n])))
    return {
        "n": n,
        "max_abs_err": err,
        "ok": err <= atol,
        "atol": atol,
    }
