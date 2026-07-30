"""GUE Wigner-surmise spacing statistics for spectra (honest RMT probe).

Mirrors the spirit of primed-topology/demos/riemann_zero_spacings.py without
claiming ATFT validation: unfold consecutive level spacings to unit mean and
measure KS distance to the GUE surmise
    p(s) = (32/π²) s² exp(-4 s² / π)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def unfold_spacings(levels: np.ndarray) -> np.ndarray:
    """Normalize consecutive gaps by local mean (unit-mean unfolding)."""
    lam = np.sort(np.real(np.asarray(levels, dtype=float).ravel()))
    # Drop numerical kernel cluster near zero
    pos = lam[lam > 1e-9]
    if pos.size < 3:
        return np.zeros(0)
    gaps = np.diff(pos)
    # Local mean via 3-point moving average of gaps
    if gaps.size == 1:
        return gaps / (gaps[0] + 1e-15)
    pad = np.pad(gaps, (1, 1), mode="edge")
    local = (pad[:-2] + pad[1:-1] + pad[2:]) / 3.0
    return gaps / (local + 1e-15)


def gue_wigner_surmise_cdf(s: np.ndarray) -> np.ndarray:
    s = np.asarray(s, dtype=float)
    hi = max(float(s.max()) if s.size else 4.0, 4.0)
    grid = np.linspace(0.0, hi, 4001)
    p = (32.0 / (math.pi**2)) * (grid**2) * np.exp(-4.0 * (grid**2) / math.pi)
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (p[1:] + p[:-1]) * np.diff(grid))])
    cdf /= cdf[-1] + 1e-15
    return np.interp(s, grid, cdf)


def poisson_spacing_cdf(s: np.ndarray) -> np.ndarray:
    """Integrable Poisson (exponential) spacings: CDF = 1 - e^{-s} for unit mean."""
    s = np.asarray(s, dtype=float)
    return 1.0 - np.exp(-np.clip(s, 0, None))


def ks_to_cdf(samples: np.ndarray, cdf_fn) -> float:
    s = np.sort(np.asarray(samples, dtype=float).ravel())
    if s.size == 0:
        return float("nan")
    n = s.size
    empirical = np.arange(1, n + 1) / n
    theoretical = cdf_fn(s)
    return float(np.max(np.abs(empirical - theoretical)))


@dataclass(frozen=True)
class GUEReport:
    n_levels: int
    n_spacings: int
    mean_spacing: float
    ks_gue: float
    ks_poisson: float
    prefers_gue: bool
    spacings: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_levels": self.n_levels,
            "n_spacings": self.n_spacings,
            "mean_spacing": self.mean_spacing,
            "ks_gue": self.ks_gue,
            "ks_poisson": self.ks_poisson,
            "prefers_gue": self.prefers_gue,
            "verdict": self.verdict(),
        }

    def verdict(self) -> str:
        if self.n_spacings < 5:
            return "INSUFFICIENT_LEVELS"
        if self.prefers_gue and self.ks_gue < 0.25:
            return "GUE-LIKE (closer to Wigner surmise than Poisson)"
        if self.ks_poisson < self.ks_gue:
            return "POISSON-LIKE (integrable / uncorrelated levels)"
        return "INDETERMINATE"


def analyze_spectrum_gue(eigenvalues: np.ndarray) -> GUEReport:
    lam = np.sort(np.real(np.asarray(eigenvalues, dtype=float).ravel()))
    spacings = unfold_spacings(lam)
    ks_g = ks_to_cdf(spacings, gue_wigner_surmise_cdf)
    ks_p = ks_to_cdf(spacings, poisson_spacing_cdf)
    report = GUEReport(
        n_levels=int(lam.size),
        n_spacings=int(spacings.size),
        mean_spacing=float(np.mean(spacings)) if spacings.size else float("nan"),
        ks_gue=ks_g,
        ks_poisson=ks_p,
        prefers_gue=bool(ks_g < ks_p),
        spacings=spacings,
    )
    logger.info(
        "GUE probe: n_sp=%d KS_GUE=%.4f KS_Poisson=%.4f → %s",
        report.n_spacings,
        report.ks_gue,
        report.ks_poisson,
        report.verdict(),
    )
    return report


def pooled_gue(spectra: list[np.ndarray]) -> GUEReport:
    """Pool unfolded spacings across several states for a family-level test."""
    all_sp = []
    n_levels = 0
    for sp in spectra:
        n_levels += len(sp)
        all_sp.append(unfold_spacings(sp))
    if not all_sp:
        return analyze_spectrum_gue(np.array([0.0, 1.0]))
    spacings = np.concatenate(all_sp) if all_sp else np.zeros(0)
    ks_g = ks_to_cdf(spacings, gue_wigner_surmise_cdf)
    ks_p = ks_to_cdf(spacings, poisson_spacing_cdf)
    report = GUEReport(
        n_levels=n_levels,
        n_spacings=int(spacings.size),
        mean_spacing=float(np.mean(spacings)) if spacings.size else float("nan"),
        ks_gue=ks_g,
        ks_poisson=ks_p,
        prefers_gue=bool(ks_g < ks_p),
        spacings=spacings,
    )
    logger.info(
        "Pooled GUE: n_sp=%d KS_GUE=%.4f KS_Poisson=%.4f → %s",
        report.n_spacings,
        report.ks_gue,
        report.ks_poisson,
        report.verdict(),
    )
    return report
