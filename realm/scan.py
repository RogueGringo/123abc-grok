"""Multi-N family scan: Coutsias → holonomy → sharp L → zeta/GUE probes per N."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from realm.cohesive import CohesiveHomotopyFunctor, StateSpectrum
from realm.coutsias import CoutsiasKinematics, ClosedGeometry
from realm.gue import GUEReport, analyze_spectrum_gue, pooled_gue
from realm.zeta_probe import CorrespondenceReport, ZetaProbe

logger = logging.getLogger(__name__)


@dataclass
class NFamilyResult:
    N: int
    n_roots: int
    roots: list[float]
    geometries: list[ClosedGeometry]
    states: list[StateSpectrum]
    zeta_gap: CorrespondenceReport | None
    gue_pooled: GUEReport | None
    mean_gap: float
    mean_holonomy: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "N": self.N,
            "n_roots": self.n_roots,
            "roots": self.roots,
            "mean_gap": self.mean_gap,
            "mean_holonomy": self.mean_holonomy,
            "zeta_gap": self.zeta_gap.to_dict() if self.zeta_gap else None,
            "gue_pooled": self.gue_pooled.to_dict() if self.gue_pooled else None,
            "states": [s.to_dict() for s in self.states],
            "geometries": [g.to_dict() for g in self.geometries],
        }


class MultiNScan:
    def __init__(
        self,
        N_values: list[int] | None = None,
        d: int = 2,
        prefer_maxop: bool = True,
        residual_tol: float = 0.55,
    ):
        self.N_values = N_values or [7, 9, 11, 13, 15]
        self.d = d
        self.prefer_maxop = prefer_maxop
        self.residual_tol = residual_tol
        self.zeta = ZetaProbe()

    def scan_one(self, N: int) -> NFamilyResult:
        logger.info("==== multi-N scan: N=%d ====", N)
        kin = CoutsiasKinematics(N=N, residual_tol=self.residual_tol)
        geoms = kin.find_real_roots()
        if len(geoms) < 2:
            kin.residual_tol = min(1.2, self.residual_tol + 0.4)
            geoms = kin.find_real_roots()
        geoms = geoms[:6]
        roots = [g.root_t for g in geoms]
        twists = [g.twist_so2 for g in geoms]

        functor = CohesiveHomotopyFunctor(N=N, d=self.d)
        states: list[StateSpectrum] = []
        for i, (root, twist, geo) in enumerate(zip(roots, twists, geoms)):
            # Drive monodromy from *geometry holonomy*, not r·π
            state = functor.evaluate_state_from_twist(
                state_id=i + 1,
                root=root,
                twist=twist,
                prefer_maxop=self.prefer_maxop,
                geometry_meta={
                    "holonomy_angle": geo.holonomy_angle,
                    "position_error": geo.position_error,
                    "residual": geo.residual,
                },
            )
            states.append(state)

        gaps = np.array([s.spectral_gap for s in states], dtype=float) if states else np.array([])
        zeta_rep = self.zeta.probe(gaps, f"spectral_gap_N{N}") if gaps.size >= 2 else None
        gue_rep = pooled_gue([s.eigenvalues for s in states]) if states else None

        return NFamilyResult(
            N=N,
            n_roots=len(roots),
            roots=roots,
            geometries=geoms,
            states=states,
            zeta_gap=zeta_rep,
            gue_pooled=gue_rep,
            mean_gap=float(np.mean(gaps)) if gaps.size else float("nan"),
            mean_holonomy=float(np.mean([g.holonomy_angle for g in geoms])) if geoms else float("nan"),
        )

    def run(self) -> list[NFamilyResult]:
        results = []
        for N in self.N_values:
            try:
                results.append(self.scan_one(N))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Scan failed for N=%d: %s", N, exc)
        return results
