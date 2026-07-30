"""Prime-wave field probes: geometric energy-gap FFT vs prime-gap statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.fft import rfft, rfftfreq

logger = logging.getLogger(__name__)


def first_primes(n: int) -> np.ndarray:
    """First n primes via sieve (n up to a few thousand is fine)."""
    if n < 1:
        return np.array([], dtype=int)
    # Prime number theorem bound with margin
    if n < 6:
        limit = 15
    else:
        limit = int(n * (np.log(n) + np.log(np.log(n))) + 10)
    while True:
        sieve = np.ones(limit + 1, dtype=bool)
        sieve[:2] = False
        for p in range(2, int(limit**0.5) + 1):
            if sieve[p]:
                sieve[p * p :: p] = False
        primes = np.flatnonzero(sieve)
        if len(primes) >= n:
            return primes[:n].astype(int)
        limit *= 2


@dataclass(frozen=True)
class WaveReport:
    geometric_gaps: np.ndarray
    prime_gaps: np.ndarray
    geom_freqs: np.ndarray
    geom_amps: np.ndarray
    prime_freqs: np.ndarray
    prime_amps: np.ndarray
    gap_ks_distance: float
    gap_mean_geom: float
    gap_mean_prime: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometric_gaps": self.geometric_gaps.tolist(),
            "prime_gaps": self.prime_gaps.tolist(),
            "gap_ks_distance": self.gap_ks_distance,
            "gap_mean_geom": self.gap_mean_geom,
            "gap_mean_prime": self.gap_mean_prime,
            "geom_fft_peak_freq": float(self.geom_freqs[np.argmax(self.geom_amps)])
            if len(self.geom_amps)
            else None,
            "prime_fft_peak_freq": float(self.prime_freqs[np.argmax(self.prime_amps)])
            if len(self.prime_amps)
            else None,
        }


def _fft_positive(signal: np.ndarray, pad_to: int = 256) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(signal, dtype=float).ravel()
    if x.size == 0:
        return np.array([]), np.array([])
    if pad_to > x.size:
        x = np.pad(x, (0, pad_to - x.size), mode="constant")
    amps = np.abs(rfft(x))
    freqs = rfftfreq(len(x), d=1.0)
    # drop DC for spike hunting
    if len(freqs) > 1:
        return freqs[1:], amps[1:]
    return freqs, amps


def _ks_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sample KS distance on empirical CDFs (no SciPy dependency)."""
    a = np.sort(np.asarray(a, dtype=float).ravel())
    b = np.sort(np.asarray(b, dtype=float).ravel())
    if a.size == 0 or b.size == 0:
        return float("nan")
    # Normalize each sample to unit mean so shape is compared, not scale
    a = a / (np.mean(a) + 1e-12)
    b = b / (np.mean(b) + 1e-12)
    grid = np.sort(np.unique(np.concatenate([a, b])))
    cdf_a = np.searchsorted(a, grid, side="right") / len(a)
    cdf_b = np.searchsorted(b, grid, side="right") / len(b)
    return float(np.max(np.abs(cdf_a - cdf_b)))


class PrimeWaveProbe:
    def __init__(self, n_primes: int = 64, fft_pad: int = 256):
        self.n_primes = n_primes
        self.fft_pad = fft_pad

    def analyze(self, ordered_levels: np.ndarray) -> WaveReport:
        """ordered_levels: sorted spectral observables per discrete state (e.g. gaps of λ)."""
        levels = np.sort(np.asarray(ordered_levels, dtype=float).ravel())
        geom_gaps = np.diff(levels)
        primes = first_primes(self.n_primes)
        prime_gaps = np.diff(primes).astype(float)

        g_f, g_a = _fft_positive(geom_gaps, pad_to=self.fft_pad)
        p_f, p_a = _fft_positive(prime_gaps, pad_to=self.fft_pad)
        ks = _ks_distance(geom_gaps, prime_gaps)

        report = WaveReport(
            geometric_gaps=geom_gaps,
            prime_gaps=prime_gaps,
            geom_freqs=g_f,
            geom_amps=g_a,
            prime_freqs=p_f,
            prime_amps=p_a,
            gap_ks_distance=ks,
            gap_mean_geom=float(np.mean(geom_gaps)) if geom_gaps.size else float("nan"),
            gap_mean_prime=float(np.mean(prime_gaps)) if prime_gaps.size else float("nan"),
        )
        logger.info(
            "Prime-wave: n_geom_gaps=%d n_prime_gaps=%d KS(scale-free)=%.4f mean_g=%.4f mean_p=%.4f",
            geom_gaps.size,
            prime_gaps.size,
            ks,
            report.gap_mean_geom,
            report.gap_mean_prime,
        )
        return report
