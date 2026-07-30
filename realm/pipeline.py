"""Realm pipeline: cohesive spectra → zeta probes → prime-wave → multi-panel figure."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from realm.cohesive import CohesiveHomotopyFunctor, StateSpectrum
from realm.prime_wave import PrimeWaveProbe, WaveReport
from realm.zeta_probe import CorrespondenceReport, ZetaProbe

logger = logging.getLogger(__name__)

# Placeholder Coutsias-style roots (replace when real algebraic roots land)
DEFAULT_CYCLOSPORIN_ROOTS = [0.1245, -0.8921, 1.4432, -2.0154]


class RealmPipeline:
    def __init__(
        self,
        N: int = 11,
        d: int = 2,
        twist_mode: str = "pi_scale",
        out_dir: str | Path = ".",
    ):
        self.functor = CohesiveHomotopyFunctor(N=N, d=d)
        self.zeta = ZetaProbe()
        self.prime_wave = PrimeWaveProbe(n_primes=64, fft_pad=256)
        self.twist_mode = twist_mode
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        roots: list[float] | None = None,
        plot_name: str = "realm_spectrum.png",
        manifest_name: str = "realm_manifest.json",
    ) -> dict[str, Any]:
        roots = list(DEFAULT_CYCLOSPORIN_ROOTS if roots is None else roots)
        logger.info("=== REALM PIPELINE START ===")
        logger.info("roots=%s twist_mode=%s N=%d d=%d", roots, self.twist_mode, self.functor.N, self.functor.d)

        states = self.functor.run(roots, twist_mode=self.twist_mode)
        gaps = np.array([s.spectral_gap for s in states], dtype=float)
        frust = np.array([s.frustration_closed_form for s in states], dtype=float)
        # Free energy F = -T log Z — gap-sensitive at low T
        T = self.functor.temperature
        free_energy = np.array(
            [-T * np.log(s.partition_function + 1e-300) for s in states], dtype=float
        )
        # Rank-order invariant: sort gaps ascending as a "ladder" vs γ ladder
        gap_ladder = np.sort(gaps)

        # Probe several geometric observables against γ_n
        reports: dict[str, CorrespondenceReport] = {
            "spectral_gap": self.zeta.probe(gaps, "spectral_gap"),
            "gap_ladder_sorted": self.zeta.probe(gap_ladder, "gap_ladder_sorted"),
            "frustration_closed_form": self.zeta.probe(frust, "frustration_closed_form"),
            "free_energy": self.zeta.probe(free_energy, "free_energy"),
        }

        # Ordered spectral gaps of the primary observable for wave analysis
        wave = self.prime_wave.analyze(gap_ladder)

        plot_path = self.out_dir / plot_name
        self.plot_realm(states, reports, wave, plot_path)

        manifest = {
            "roots": roots,
            "twist_mode": self.twist_mode,
            "N": self.functor.N,
            "d": self.functor.d,
            "states": [s.to_dict() for s in states],
            "zeta_probes": {k: v.to_dict() for k, v in reports.items()},
            "prime_wave": wave.to_dict(),
            "plot": str(plot_path.resolve()),
            "honest_summary": self._summary(reports, wave),
        }
        man_path = self.out_dir / manifest_name
        man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info("Wrote manifest %s", man_path)
        logger.info("=== REALM PIPELINE END ===\n%s", manifest["honest_summary"])
        return manifest

    @staticmethod
    def _summary(reports: dict[str, CorrespondenceReport], wave: WaveReport) -> str:
        lines = ["HONEST REALM SUMMARY"]
        for name, rep in reports.items():
            lines.append(f"  [{name}] {rep.verdict()}")
        lines.append(
            f"  [prime_wave] scale-free KS(geom gaps vs prime gaps)={wave.gap_ks_distance:.4f} "
            f"(0=identical shape; ~0.5=unrelated)"
        )
        lines.append(
            "  NOTE: raw resonance would require geometric λ already ≈ γ_n; "
            "affine calibration always has 2 free parameters and is not a proof."
        )
        return "\n".join(lines)

    def plot_realm(
        self,
        states: list[StateSpectrum],
        reports: dict[str, CorrespondenceReport],
        wave: WaveReport,
        path: Path,
    ) -> None:
        fig = plt.figure(figsize=(14, 10))
        gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.28)

        # (0,0) Full spectra per state
        ax0 = fig.add_subplot(gs[0, 0])
        colors = ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728", "#9467bd", "#8c564b"]
        for i, s in enumerate(states):
            ax0.plot(
                s.eigenvalues,
                "o-",
                ms=3,
                color=colors[i % len(colors)],
                label=f"S{s.state_id} θ/π={s.twist / np.pi:.2f}",
            )
        ax0.set_title("Connection Laplacian spectra (sharp modality)")
        ax0.set_xlabel("Eigenvalue index k")
        ax0.set_ylabel("λ_k")
        ax0.grid(True, alpha=0.4, ls="--")
        ax0.legend(fontsize=8)

        # (0,1) Spectral gaps vs ζ zeros: raw + calibrated
        ax1 = fig.add_subplot(gs[0, 1])
        rep = reports["spectral_gap"]
        idx = np.arange(1, len(rep.observed) + 1)
        ax1.plot(idx, rep.zeta_targets, "k*-", label="γ_n (Riemann zeros)", lw=2)
        ax1.plot(idx, rep.observed, "o--", color="#d62728", label="raw λ_gap (geometry)")
        ax1.plot(idx, rep.calibrated, "s--", color="#1f77b4", label=f"affine aλ+b (a={rep.affine_scale:.3g})")
        ax1.set_title("Zeta correspondence (honest)")
        ax1.set_xlabel("State index")
        ax1.set_ylabel("Value")
        ax1.grid(True, alpha=0.4, ls="--")
        ax1.legend(fontsize=8)
        ax1.text(
            0.02,
            0.98,
            f"raw⟨err⟩={rep.raw_mean_error:.3g}\ncal⟨err⟩={rep.calibrated_mean_error:.3g}\nnull={rep.null_mean:.3g}±{rep.null_std:.3g}",
            transform=ax1.transAxes,
            va="top",
            fontsize=8,
            family="monospace",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.7),
        )

        # (1,0) FFT geometric gaps vs prime gaps
        ax2 = fig.add_subplot(gs[1, 0])
        if wave.geom_amps.size:
            ax2.plot(wave.geom_freqs, wave.geom_amps, color="purple", lw=2, label="FFT | geom gaps")
        if wave.prime_amps.size:
            # normalize prime amps to same peak for shape comparison
            scale = (np.max(wave.geom_amps) / (np.max(wave.prime_amps) + 1e-12)) if wave.geom_amps.size else 1.0
            ax2.plot(
                wave.prime_freqs,
                wave.prime_amps * scale,
                color="gray",
                lw=1.5,
                alpha=0.8,
                label="FFT | prime gaps (peak-scaled)",
            )
        ax2.set_title("Prime-wave FFT comparison")
        ax2.set_xlabel("Frequency")
        ax2.set_ylabel("Amplitude")
        ax2.grid(True, alpha=0.4, ls="--")
        ax2.legend(fontsize=8)

        # (1,1) Bar: Z and frustration per state
        ax3 = fig.add_subplot(gs[1, 1])
        labels = [f"S{s.state_id}" for s in states]
        x = np.arange(len(states))
        w = 0.35
        z_vals = [s.partition_function for s in states]
        f_vals = [s.frustration_closed_form for s in states]
        ax3.bar(x - w / 2, z_vals, w, label="Z = Tr e^{-L/T}", color="#2ca02c")
        ax3b = ax3.twinx()
        ax3b.bar(x + w / 2, f_vals, w, label="frustration (closed form)", color="#ff7f0e", alpha=0.8)
        ax3.set_xticks(x)
        ax3.set_xticklabels(labels)
        ax3.set_ylabel("Partition function Z")
        ax3b.set_ylabel("Frustration λ_cf")
        ax3.set_title("Thermodynamic / flat-modality diagnostics")
        ax3.grid(True, axis="y", alpha=0.3, ls="--")
        h1, l1 = ax3.get_legend_handles_labels()
        h2, l2 = ax3b.get_legend_handles_labels()
        ax3.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")

        fig.suptitle(
            "Zeta–Kinematic Realm  |  cohesive monodromy → spectral probes",
            fontsize=14,
            fontweight="bold",
        )
        fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved realm figure → %s", path)
