"""Zeta-Kinematic Resonance — realm-aware facade.

The original stub hardcoded λ ≈ γ_n (tautological "Strong Resonance").
This module now delegates to the real cohesive monodromy pipeline and runs
*honest* zeta / prime-wave probes. For the full multi-panel figure use:

    python run_realm.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.cohesive import CohesiveHomotopyFunctor
from realm.pipeline import DEFAULT_CYCLOSPORIN_ROOTS, RealmPipeline
from realm.prime_wave import PrimeWaveProbe
from realm.zeta_probe import DEFAULT_ZETA_ZEROS, ZetaProbe

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ZetaKinematicResonance:
    """Compatibility API: real spectra in, honest correspondence out."""

    def __init__(self, d_distinctions: int = 3, r_relations: int = 8, N: int = 11, d: int = 2):
        self.D = d_distinctions
        self.R = r_relations
        self.topological_action_S_min = self.D * self.R * (2 * np.pi)
        self.zeta_zeros = DEFAULT_ZETA_ZEROS.copy()
        self.functor = CohesiveHomotopyFunctor(N=N, d=d)
        self.probe = ZetaProbe(zeta_zeros=self.zeta_zeros)
        self._last_states = None

    def compute_root_laplacians(self, coutsias_roots):
        """Build real connection Laplacians; return spectral gaps (not hardcoded γ_n)."""
        states = self.functor.run(list(coutsias_roots), twist_mode="pi_scale")
        self._last_states = states
        gaps = np.array([s.spectral_gap for s in states], dtype=float)
        logger.info("Spectral gaps from monodromy Laplacians: %s", gaps)
        return gaps

    def test_zeta_correspondence(self, laplacian_eigenvalues):
        """Honest probe: raw + affine + null controls (no automatic victory)."""
        report = self.probe.probe(np.asarray(laplacian_eigenvalues, dtype=float), "spectral_gap")
        return report.raw_errors.tolist()

    def fourier_transform_gaps(self, laplacian_eigenvalues):
        wave = PrimeWaveProbe().analyze(np.asarray(laplacian_eigenvalues, dtype=float))
        return wave.geom_freqs, wave.geom_amps

    def plot_prime_wave_resonance(self, freqs, fft_vals):
        """Thin wrapper: full realm figure is preferred (run_realm.py)."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 6))
        plt.plot(freqs, fft_vals, color="purple", linewidth=2)
        plt.title("Fourier Transform of Geometric Spectral Gaps")
        plt.xlabel("Frequency")
        plt.ylabel("Amplitude")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.tight_layout()
        out = ROOT / "zeta_resonance_spikes.png"
        plt.savefig(out, dpi=300)
        plt.close()
        logger.info("Saved %s (prefer realm_spectrum.png from run_realm.py)", out)


if __name__ == "__main__":
    # Full realm is the primary experience
    pipe = RealmPipeline(N=11, d=2, out_dir=ROOT)
    pipe.run()
