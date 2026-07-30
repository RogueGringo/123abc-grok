"""Verified real ζ ordinates — computed, never recalled.

`realm.zeta_field.ZETA_ZEROS_IMAG` carries only 15 hardcoded ordinates, and
`realm.validate.seeds.make_seed` silently mean-gap-extrapolates past the end of
that table. Held-out-window tests need *genuine* zeros beyond γ_15, so we compute
them with mpmath and cache to disk.

Every generated table is checked three independent ways before it is trusted:

1. agreement with the repo's hardcoded table on the overlap,
2. each ordinate is a root of the Riemann-Siegel Z function,
3. the count matches the Riemann-von Mangoldt asymptotic N(T).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from realm.zeta_field import ZETA_ZEROS_IMAG

CACHE = Path(__file__).resolve().parents[2] / "data" / "zeta_zeros.json"

# Tolerances for the three verification checks
TOL_OVERLAP = 1e-8  # repo table is rounded to 10 dp
TOL_SIEGELZ = 1e-6
TOL_COUNT = 2.0  # N(T) asymptotic has O(log T) error


class ZeroVerificationError(RuntimeError):
    """Raised when a generated ordinate table fails a verification check."""


def _riemann_von_mangoldt(T: float) -> float:
    """Asymptotic count of zeros with 0 < Im(ρ) < T."""
    import mpmath as mp

    t = mp.mpf(T)
    return float(t / (2 * mp.pi) * mp.log(t / (2 * mp.pi)) - t / (2 * mp.pi) + 0.875)


def verify_zeros(g: np.ndarray, *, dps: int = 30) -> dict[str, Any]:
    """Run all three checks. Raises ZeroVerificationError on failure.

    Precision is set explicitly rather than inherited from ambient mpmath state,
    so a caller that lowered `mp.mp.dps` elsewhere cannot cause a precision-driven
    false failure as n grows. Matches the precision used by `_compute`.
    """
    import mpmath as mp

    mp.mp.dps = int(dps)
    g = np.asarray(g, dtype=float)
    report: dict[str, Any] = {"n": int(g.size)}

    if not np.all(np.diff(g) > 0):
        raise ZeroVerificationError("ordinates are not strictly increasing")

    # 1. overlap with the repo's hardcoded table
    m = min(g.size, ZETA_ZEROS_IMAG.size)
    overlap = float(np.max(np.abs(g[:m] - ZETA_ZEROS_IMAG[:m]))) if m else 0.0
    report["max_overlap_diff"] = overlap
    if overlap > TOL_OVERLAP:
        raise ZeroVerificationError(
            f"disagrees with ZETA_ZEROS_IMAG on first {m}: max diff {overlap:.3e}"
        )

    # 2. every ordinate is a root of the Riemann-Siegel Z function
    worst = 0.0
    for t in g:
        worst = max(worst, abs(float(mp.siegelz(t))))
    report["max_abs_siegelz"] = worst
    if worst > TOL_SIEGELZ:
        raise ZeroVerificationError(f"not all ordinates are Z roots: max |Z| {worst:.3e}")

    # 3. Riemann-von Mangoldt count
    T = float(g[-1]) + 0.5
    n_asym = _riemann_von_mangoldt(T)
    report["N_T_asymptotic"] = n_asym
    report["N_T_expected"] = int(g.size)
    if abs(n_asym - g.size) > TOL_COUNT:
        raise ZeroVerificationError(
            f"count mismatch at T={T:.3f}: asymptotic {n_asym:.2f} vs {g.size}"
        )

    report["verified"] = True
    return report


def _compute(n: int) -> np.ndarray:
    import mpmath as mp

    mp.mp.dps = 30
    return np.array([float(mp.im(mp.zetazero(i))) for i in range(1, n + 1)], dtype=float)


def real_zeros(n: int, *, cache: Path | None = CACHE, verify: bool = True) -> np.ndarray:
    """First `n` genuine ζ ordinates, cached on disk.

    Never extrapolates: if mpmath is unavailable and the cache is short, raises.
    """
    n = int(n)
    if n < 2:
        raise ValueError("need at least 2 ordinates")

    path = Path(cache) if cache is not None else None
    if path is not None and path.is_file():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            cached = np.asarray(blob["gammas"], dtype=float)
            if cached.size >= n:
                out = cached[:n].copy()
                if verify:
                    # `verify=True` must mean verified, including on a cache hit.
                    # Otherwise correctness silently depends on the cache file never
                    # having been edited or truncated — which defeats the point of a
                    # module whose contract is "computed and checked, never recalled".
                    if not (blob.get("verification") or {}).get("verified"):
                        raise ZeroVerificationError("cache lacks a verified stamp")
                    verify_zeros(out)
                return out
        except Exception:  # noqa: BLE001 - a bad cache is rebuilt, never trusted
            pass

    # Compute a little extra so the next request is likely a cache hit
    g = _compute(max(n, 40))
    report = verify_zeros(g) if verify else {"verified": False}

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "source": "mpmath.zetazero",
                    "gammas": g.tolist(),
                    "verification": report,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return g[:n].copy()


def window(start: int, k: int, **kw: Any) -> np.ndarray:
    """Ordinates γ_start .. γ_{start+k-1}, 1-indexed (window(1, 14) == first 14)."""
    start = int(start)
    if start < 1:
        raise ValueError("start is 1-indexed")
    return real_zeros(start + int(k) - 1, **kw)[start - 1 :].copy()
