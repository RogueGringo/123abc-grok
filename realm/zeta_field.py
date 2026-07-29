"""Zeta field primitives — the generative source, not a matching target.

The non-trivial zeros γ_n on the critical line are a *spectral seed*.
Geometry is built *off* them (induced monodromy, discrete sectors, clouds).
We never assert that a physical operator's eigenvalues *are* the actual γ_n.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

# Imaginary parts of the first non-trivial zeros (seed table only)
ZETA_ZEROS_IMAG = np.array(
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
        52.9703214777,
        56.4462476971,
        59.3470440036,
        60.8317785246,
        65.1125440481,
    ],
    dtype=float,
)


@dataclass(frozen=True)
class ZetaField:
    """Finite truncation of the critical-line spectrum used as a generative field."""

    gammas: np.ndarray  # γ_n > 0
    gaps: np.ndarray  # Δγ_n = γ_{n+1} - γ_n

    @classmethod
    def first(cls, k: int = 6) -> "ZetaField":
        g = ZETA_ZEROS_IMAG[: max(k, 2)].copy()
        return cls(gammas=g, gaps=np.diff(g))

    def normalized_modes(self) -> np.ndarray:
        """Map γ_n → (0, 2π] phase modes (geometry-ready, not 'actual zeros')."""
        g = self.gammas
        # Relative to mean density so modes live on the circle
        return (2.0 * np.pi * (g - g[0]) / (g[-1] - g[0] + 1e-15)) % (2.0 * np.pi)

    def gap_phases(self) -> np.ndarray:
        """Successive zero *gaps* as monodromy angles (scale-free geometry)."""
        d = self.gaps
        if d.size == 0:
            return np.zeros(0)
        # Unit-mean gaps → angles in (0, 2π) with mean π/2 for mild twist
        return (d / (np.mean(d) + 1e-15)) * (np.pi / 2.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "generative_seed_not_physical_eigenvalues",
            "gammas": self.gammas.tolist(),
            "gaps": self.gaps.tolist(),
            "normalized_modes": self.normalized_modes().tolist(),
            "gap_phases": self.gap_phases().tolist(),
        }
