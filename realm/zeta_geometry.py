"""Geometry *off* the zeta field — induced sectors, not matched-to-actual-zeros.

Pipeline:
    ZetaField (γ_n seed)
        → monodromy twists from gap phases / modes
        → discrete cyclic geometries on C_N (Fourier embedding on S^1 ⊂ R^3)
        → connection / sheaf Laplacian spectra of *those* geometries

The spectra that come out are properties of zeta-*induced* geometry.
They are not claimed to be the Riemann zeros themselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from realm.cohesive import CohesiveHomotopyFunctor
from realm.sheaf_backend import CellularSheaf, sharp_laplacian
from realm.types import Sector, Spectrum
from realm.waypoints import signature_for_cloud
from realm.zeta_field import ZetaField

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InducedSector:
    """One discrete geometry induced by a zeta-field mode/gap."""

    id: int
    gamma_seed: float  # which γ (or gap center) seeded this sector — label only
    twist: float  # induced monodromy angle
    positions: np.ndarray  # (N, 3) cyclic cloud
    mode_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "gamma_seed": float(self.gamma_seed),
            "twist": float(self.twist),
            "mode_index": self.mode_index,
            "positions": self.positions.tolist(),
            "note": "geometry induced from zeta field; gamma_seed is a label not an eigenvalue claim",
        }

    def as_sector(self) -> Sector:
        """Project into the shared Sector type (kinematic fields left inert)."""
        return Sector(
            id=self.id,
            root_t=float(np.tan(0.5 * np.clip(self.twist, -np.pi + 0.05, np.pi - 0.05))),
            residual=0.0,  # exact by construction (spectral embedding)
            positions=self.positions,
            holonomy_angle=abs(self.twist) % (2 * np.pi),
            twist=self.twist,
            position_error=0.0,
            orientation_error=0.0,
            free_torsions=(self.twist,),
        )


def embed_cycle_from_twist(
    N: int,
    twist: float,
    radius: float = 1.0,
    height_amp: float = 0.25,
) -> np.ndarray:
    """Build a closed N-gon in R^3 whose out-of-plane ripple encodes twist.

    Planar regular N-gon + vertical Fourier mode ∝ twist → nontrivial geometry
    with exact positional closure (by construction, not optimization).
    """
    angles = 2.0 * np.pi * np.arange(N) / N
    # Twist shears the phase of the height mode (holonomy of the ribbon)
    z = height_amp * np.sin(angles + twist) * (1.0 + 0.15 * np.cos(2 * twist))
    # Mild in-plane breathing from |twist|
    r = radius * (1.0 + 0.08 * np.sin(twist) * np.cos(angles))
    x = r * np.cos(angles)
    y = r * np.sin(angles)
    pts = np.column_stack([x, y, z])
    pts -= pts.mean(axis=0)
    return pts


class ZetaInducedGeometry:
    """Construct cyclic geometries and sheaf spectra *from* a ZetaField seed."""

    def __init__(
        self,
        N: int = 11,
        d: int = 2,
        n_sectors: int = 6,
        prefer_maxop: bool = True,
        temperature: float = 0.05,
        twist_source: str = "gap_phases",
    ):
        """
        twist_source:
            "gap_phases" — monodromy from successive γ gaps (default; geometry off gaps)
            "modes"      — monodromy from normalized γ modes on the circle
        """
        self.N = N
        self.d = d
        self.n_sectors = n_sectors
        self.prefer_maxop = prefer_maxop
        self.temperature = temperature
        self.twist_source = twist_source
        self.functor = CohesiveHomotopyFunctor(N=N, d=d, temperature=temperature)

    def twists_from_field(self, field: ZetaField) -> tuple[np.ndarray, np.ndarray]:
        """Return (twists, seed_labels) for n_sectors induced sectors."""
        if self.twist_source == "modes":
            phases = field.normalized_modes()
            seeds = field.gammas
        else:
            phases = field.gap_phases()
            # label each gap by midpoint of adjacent zeros
            g = field.gammas
            seeds = 0.5 * (g[:-1] + g[1:]) if g.size > 1 else g
        k = min(self.n_sectors, len(phases))
        return phases[:k].astype(float), seeds[:k].astype(float)

    def induce_sectors(self, field: ZetaField | None = None) -> list[InducedSector]:
        field = field or ZetaField.first(self.n_sectors + 1)
        twists, seeds = self.twists_from_field(field)
        sectors: list[InducedSector] = []
        for i, (th, seed) in enumerate(zip(twists, seeds)):
            pts = embed_cycle_from_twist(self.N, float(th))
            sectors.append(
                InducedSector(
                    id=i + 1,
                    gamma_seed=float(seed),
                    twist=float(th),
                    positions=pts,
                    mode_index=i,
                )
            )
            logger.info(
                "Induced sector %d | γ-seed=%.4f (label) | twist=%.4f | N=%d",
                i + 1,
                seed,
                th,
                self.N,
            )
        return sectors

    def spectra_of(self, sectors: list[InducedSector]) -> list[Spectrum]:
        """Sheaf Laplacian spectra of zeta-*induced* geometries."""
        out: list[Spectrum] = []
        for sec in sectors:
            A = self.functor.rotation_monodromy(sec.twist)
            L, eigs, meta = sharp_laplacian(
                self.N, self.d, A, prefer_maxop=self.prefer_maxop
            )
            gap = self.functor.spectral_gap(eigs)
            Z = self.functor.partition_function(eigs)
            frust = float(2.0 - 2.0 * np.cos(sec.twist / self.N)) if not np.isclose(sec.twist, 0.0) else 0.0
            backend = str(meta.get("backend", "unknown"))
            out.append(
                Spectrum(
                    sector_id=sec.id,
                    twist=sec.twist,
                    eigenvalues=eigs,
                    spectral_gap=gap,
                    lambda_min=float(eigs[0]),
                    frustration_closed_form=frust,
                    partition_function=Z,
                    backend=backend,
                    laplacian=L,
                )
            )
            logger.info(
                "Spectrum sector %d | λ_gap=%.6g | backend=%s | (not claiming = γ)",
                sec.id,
                gap,
                backend,
            )
        return out

    def waypoints_of(self, sectors: list[InducedSector]):
        from realm.types import Waypoint

        wps: list[Waypoint] = []
        for sec in sectors:
            # densify ring for VR
            pts = sec.positions
            mids = 0.5 * (pts + np.roll(pts, -1, axis=0))
            cloud = np.vstack([pts, mids])
            raw = signature_for_cloud(cloud, state_id=sec.id)
            wps.append(
                Waypoint(
                    sector_id=sec.id,
                    backend=raw.backend,
                    epsilon_star=raw.epsilon_star,
                    gini_at_onset=raw.gini_at_onset,
                    gini_slope_at_onset=raw.gini_slope_at_onset,
                    vector=raw.vector,
                    waypoints=raw.waypoints,
                    derivative_values=raw.derivative_values,
                )
            )
        return wps
