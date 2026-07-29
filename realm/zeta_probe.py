"""Honest Riemann-zeta probes against geometric spectral invariants.

Design law: never hardcode geometric eigenvalues to γ_n.
Report raw distances, optimal affine calibration (declared free params),
and null-model baselines so "resonance" cannot be faked by construction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# First non-trivial zeros on the critical line (imaginary parts γ_n)
DEFAULT_ZETA_ZEROS = np.array(
    [
        14.1347251417,
        21.0220396388,
        25.0108575801,
        30.4248761259,
        32.9350615877,
        37.5861781588,
        40.9187190121,
        43.3270732809,
        48.0051508811,
        49.7738324777,
    ],
    dtype=float,
)


@dataclass(frozen=True)
class CorrespondenceReport:
    observable_name: str
    observed: np.ndarray
    zeta_targets: np.ndarray
    raw_errors: np.ndarray
    raw_mean_error: float
    affine_scale: float
    affine_offset: float
    calibrated: np.ndarray
    calibrated_errors: np.ndarray
    calibrated_mean_error: float
    null_mean_errors: np.ndarray
    null_mean: float
    null_std: float
    beats_null: bool
    raw_resonance: bool
    calibrated_resonance: bool
    threshold: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "observable_name": self.observable_name,
            "observed": self.observed.tolist(),
            "zeta_targets": self.zeta_targets.tolist(),
            "raw_errors": self.raw_errors.tolist(),
            "raw_mean_error": self.raw_mean_error,
            "affine_scale": self.affine_scale,
            "affine_offset": self.affine_offset,
            "calibrated": self.calibrated.tolist(),
            "calibrated_errors": self.calibrated_errors.tolist(),
            "calibrated_mean_error": self.calibrated_mean_error,
            "null_mean": self.null_mean,
            "null_std": self.null_std,
            "beats_null": self.beats_null,
            "raw_resonance": self.raw_resonance,
            "calibrated_resonance": self.calibrated_resonance,
            "threshold": self.threshold,
            "verdict": self.verdict(),
        }

    def verdict(self) -> str:
        if self.raw_resonance:
            return "RAW_RESONANCE: observed values already near γ_n without free params"
        if self.calibrated_resonance and self.beats_null:
            return (
                "CALIBRATED_ONLY: affine map a·λ+b fits γ_n better than nulls "
                f"(a={self.affine_scale:.4g}, b={self.affine_offset:.4g}) — free scale, not proof"
            )
        if self.beats_null:
            return "BEATS_NULL_ONLY: better than shuffled controls but above resonance threshold"
        return "NO_RESONANCE: geometry does not collapse onto the prime wave field under this probe"


class ZetaProbe:
    def __init__(
        self,
        zeta_zeros: np.ndarray | None = None,
        resonance_threshold: float = 0.1,
        null_trials: int = 64,
        rng_seed: int = 7,
    ):
        self.zeta_zeros = np.asarray(
            DEFAULT_ZETA_ZEROS if zeta_zeros is None else zeta_zeros, dtype=float
        )
        self.threshold = float(resonance_threshold)
        self.null_trials = int(null_trials)
        self.rng = np.random.default_rng(rng_seed)

    @staticmethod
    def affine_calibrate(observed: np.ndarray, targets: np.ndarray) -> tuple[float, float, np.ndarray]:
        """Least-squares a, b minimizing ||a x + b - y||_2."""
        x = np.asarray(observed, dtype=float).ravel()
        y = np.asarray(targets, dtype=float).ravel()
        if x.size != y.size:
            raise ValueError("observed and targets must match length")
        if x.size < 2:
            a, b = 1.0, float(y[0] - x[0]) if x.size == 1 else 0.0
            return a, b, a * x + b
        A = np.column_stack([x, np.ones_like(x)])
        coef, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        a, b = float(coef[0]), float(coef[1])
        return a, b, a * x + b

    def probe(
        self,
        observed: np.ndarray,
        observable_name: str = "spectral_gap",
        n_zeros: int | None = None,
    ) -> CorrespondenceReport:
        obs = np.asarray(observed, dtype=float).ravel()
        k = len(obs) if n_zeros is None else min(n_zeros, len(obs), len(self.zeta_zeros))
        obs = obs[:k]
        targets = self.zeta_zeros[:k]

        raw_err = np.abs(obs - targets)
        raw_mean = float(np.mean(raw_err))

        a, b, calibrated = self.affine_calibrate(obs, targets)
        cal_err = np.abs(calibrated - targets)
        cal_mean = float(np.mean(cal_err))

        # Null model: random positive observables with same mean/std as observed,
        # affine-fit each trial to γ_n, collect mean calibrated errors.
        null_means = []
        mu, sigma = float(np.mean(obs)), float(np.std(obs))
        sigma = max(sigma, 1e-9)
        for _ in range(self.null_trials):
            fake = np.abs(self.rng.normal(mu, sigma, size=k))
            _, _, fit = self.affine_calibrate(fake, targets)
            null_means.append(float(np.mean(np.abs(fit - targets))))
        null_means_arr = np.asarray(null_means, dtype=float)
        null_mean = float(np.mean(null_means_arr))
        null_std = float(np.std(null_means_arr))
        beats_null = cal_mean < (null_mean - null_std)  # one-sigma better than null center

        report = CorrespondenceReport(
            observable_name=observable_name,
            observed=obs,
            zeta_targets=targets,
            raw_errors=raw_err,
            raw_mean_error=raw_mean,
            affine_scale=a,
            affine_offset=b,
            calibrated=calibrated,
            calibrated_errors=cal_err,
            calibrated_mean_error=cal_mean,
            null_mean_errors=null_means_arr,
            null_mean=null_mean,
            null_std=null_std,
            beats_null=bool(beats_null),
            raw_resonance=raw_mean < self.threshold,
            calibrated_resonance=cal_mean < self.threshold,
            threshold=self.threshold,
        )

        logger.info("Zeta probe on '%s' (k=%d)", observable_name, k)
        for i in range(k):
            logger.info(
                "  [%d] obs=%.6f γ=%.6f raw_err=%.6f cal=%.6f cal_err=%.6f",
                i + 1,
                obs[i],
                targets[i],
                raw_err[i],
                calibrated[i],
                cal_err[i],
            )
        logger.info(
            "  raw_mean=%.6f cal_mean=%.6f null=%.6f±%.6f beats_null=%s",
            raw_mean,
            cal_mean,
            null_mean,
            null_std,
            beats_null,
        )
        logger.info("  VERDICT: %s", report.verdict())
        return report
