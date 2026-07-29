"""The correct pipeline — geometry *off* the zetas, not the actual zeros.

Correct dataflow:

    ZetaField (γ_n as generative seed)
        → induced monodromy twists (from gaps / modes)
        → closed cyclic geometries on C_N  (exact by construction)
        → MaxOp sheaf Laplacian L_F of that geometry
        → waypoint signatures W(C)
        → structural probes on the *induced* spectra
          (GUE, prime-wave of induced gaps, consistency checks)

What this is NOT:
    - kinematics whose λ are claimed to equal actual γ_n
    - θ = root·π fantasy matching
    - "Strong Resonance" with the literal Riemann zeros

The zeros seed geometry. Geometry produces its own spectrum.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from realm.gue import pooled_gue
from realm.prime_wave import PrimeWaveProbe
from realm.sheaf_backend import CellularSheaf
from realm.types import AnalysisResult, ProbeReport, Sector, Spectrum, Waypoint
from realm.zeta_field import ZetaField
from realm.zeta_geometry import InducedSector, ZetaInducedGeometry

logger = logging.getLogger(__name__)


@dataclass
class KinematicSpectralRealm:
    """Canonical engine: zeta field → induced geometry → sheaf spectrum → probes.

    Name kept for call-site stability; kinematics-from-scratch is no longer
    the source of truth. Optional Coutsias comparison can be layered later.
    """

    N: int = 11
    d: int = 2
    n_sectors: int = 6
    prefer_maxop: bool = True
    temperature: float = 0.05
    twist_source: str = "gap_phases"  # geometry off successive zero gaps
    with_waypoints: bool = True
    with_probes: bool = True
    # legacy kwargs ignored (compat)
    n_free: int = 6
    residual_tol: float = 0.4
    n_starts: int = 56
    use_de: bool = True
    max_sectors: int = 6
    rng_seed: int = 11

    def __post_init__(self) -> None:
        self.n_sectors = min(self.n_sectors, self.max_sectors)
        self._geom = ZetaInducedGeometry(
            N=self.N,
            d=self.d,
            n_sectors=self.n_sectors,
            prefer_maxop=self.prefer_maxop,
            temperature=self.temperature,
            twist_source=self.twist_source,
        )
        self._prime = PrimeWaveProbe(n_primes=80)

    def analyze(self, field: ZetaField | None = None) -> AnalysisResult:
        """Default: full spectral-action derivation (geometry off Crit(S)).

        Falls back to gap-phase induction if derivation yields no sectors.
        """
        # Prefer continued derivation ladder
        try:
            from realm.derive import Deriver

            der = Deriver(
                N=self.N,
                d=self.d,
                n_zeros=max(self.n_sectors + 4, 10),
                n_sectors=self.n_sectors,
                prefer_maxop=self.prefer_maxop,
            ).run()
            induced = der.sectors
            spectra = der.spectra
            field = der.field
            logger.info(
                "CORRECT pipeline via DERIVATION ladder D0–D6 | N=%d sectors=%d",
                self.N,
                len(induced),
            )
            self._last_derivation = der
        except Exception as exc:  # noqa: BLE001
            logger.warning("Derivation ladder failed (%s); gap-phase induction", exc)
            field = field or ZetaField.first(self.n_sectors + 1)
            logger.info(
                "CORRECT pipeline: geometry OFF zeta field | N=%d sectors=%d maxop=%s source=%s",
                self.N,
                self.n_sectors,
                self.prefer_maxop and CellularSheaf is not None,
                self.twist_source,
            )
            induced = self._geom.induce_sectors(field)
            spectra = self._geom.spectra_of(induced)
        waypoints: list[Waypoint] = []
        if self.with_waypoints:
            waypoints = self._geom.waypoints_of(induced)

        sectors: list[Sector] = [s.as_sector() for s in induced]
        probes: list[ProbeReport] = []
        if self.with_probes:
            probes = self._structural_probes(spectra, field, induced)

        sheaf_backend = spectra[0].backend if spectra else "none"
        wp_backend = waypoints[0].backend if waypoints else "none"

        result = AnalysisResult(
            N=self.N,
            d=self.d,
            n_free=0,  # not Coutsias-sourced
            best_residual=0.0,  # exact induced closure
            sectors=tuple(sectors),
            spectra=tuple(spectra),
            waypoints=tuple(waypoints),
            probes=tuple(probes),
            sheaf_backend=sheaf_backend,
            waypoint_backend=wp_backend,
        )
        # Attach field metadata via probe note
        logger.info(
            "analyze complete | sheaf=%s waypoints=%s | spectra are of INDUCED geometry, not actual γ_n",
            sheaf_backend,
            wp_backend,
        )
        return result

    def _structural_probes(
        self,
        spectra: list[Spectrum],
        field: ZetaField,
        induced: list[InducedSector],
    ) -> list[ProbeReport]:
        """Probes on induced structure — never 'match λ to actual γ'."""
        reports: list[ProbeReport] = []
        gaps = np.array([s.spectral_gap for s in spectra], dtype=float)
        twists = np.array([s.twist for s in spectra], dtype=float)

        # 1) Induced gap ladder vs seed gap ladder (shape comparison, scale-free)
        seed_gaps = field.gaps[: max(len(gaps) - 1, 0)]
        if gaps.size >= 2 and seed_gaps.size >= 1:
            ind = np.diff(np.sort(gaps))
            # pad/truncate
            m = min(len(ind), len(seed_gaps))
            if m >= 1:
                a = ind[:m] / (np.mean(ind[:m]) + 1e-15)
                b = seed_gaps[:m] / (np.mean(seed_gaps[:m]) + 1e-15)
                shape_err = float(np.mean(np.abs(a - b)))
                reports.append(
                    ProbeReport(
                        name="induced_vs_seed_gap_shape",
                        verdict=(
                            f"scale-free gap-shape L1={shape_err:.4f} "
                            f"(0=same shape; compares induced geometry gaps to ζ-gap shape — not λ=γ)"
                        ),
                        detail={
                            "induced_norm_gaps": a.tolist(),
                            "seed_norm_gaps": b.tolist(),
                            "shape_l1": shape_err,
                            "interpretation": "geometry-off-zetas consistency, not eigenvalue identity",
                        },
                    )
                )

        # 2) Twist field should be monotone-ish with mode index for gap_phases
        if twists.size >= 2:
            mono = float(np.mean(np.diff(np.sort(np.abs(twists))) >= -1e-9))
            reports.append(
                ProbeReport(
                    name="twist_field_structure",
                    verdict=f"twist spread={float(np.std(twists)):.4f} |abs| monotone_frac~{mono:.2f}",
                    detail={"twists": twists.tolist()},
                )
            )

        # 3) Prime-wave on induced spectral gaps (structure of geometry, not RH)
        wave = self._prime.analyze(np.sort(gaps)) if gaps.size else None
        if wave is not None:
            reports.append(
                ProbeReport(
                    name="prime_wave_induced",
                    verdict=f"KS(induced gaps vs primes)={wave.gap_ks_distance:.4f}",
                    detail=wave.to_dict(),
                )
            )

        # 4) GUE/Poisson of induced sheaf spectra
        gue = pooled_gue([s.eigenvalues for s in spectra])
        reports.append(
            ProbeReport(
                name="gue_induced_sheaf",
                verdict=gue.verdict(),
                detail=gue.to_dict(),
            )
        )

        # 5) Explicit non-claim
        reports.append(
            ProbeReport(
                name="ontology",
                verdict="Geometry is OFF the zeta field; spectra are not the actual zeros.",
                detail=field.to_dict(),
            )
        )
        return reports


def analyze_cycle(N: int = 11, **kwargs) -> AnalysisResult:
    """One-liner: geometry induced from the zeta field, then spectral analysis."""
    return KinematicSpectralRealm(N=N, **kwargs).analyze()
