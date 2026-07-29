"""Canonical data types for the zeta-induced geometry pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Sector:
    """One discrete cyclic sector (zeta-induced or kinematic)."""

    id: int
    root_t: float
    residual: float
    positions: np.ndarray
    holonomy_angle: float
    twist: float
    position_error: float
    orientation_error: float
    free_torsions: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "root_t": float(self.root_t),
            "residual": float(self.residual),
            "holonomy_angle": float(self.holonomy_angle),
            "twist": float(self.twist),
            "position_error": float(self.position_error),
            "orientation_error": float(self.orientation_error),
            "free_torsions": list(self.free_torsions),
            "positions": self.positions.tolist(),
        }


@dataclass(frozen=True)
class Spectrum:
    """Sheaf Laplacian spectrum of an induced geometric sector."""

    sector_id: int
    twist: float
    eigenvalues: np.ndarray
    spectral_gap: float
    lambda_min: float
    frustration_closed_form: float
    partition_function: float
    backend: str
    laplacian: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_id": self.sector_id,
            "twist": float(self.twist),
            "spectral_gap": float(self.spectral_gap),
            "lambda_min": float(self.lambda_min),
            "frustration_closed_form": float(self.frustration_closed_form),
            "partition_function": float(self.partition_function),
            "backend": self.backend,
            "eigenvalues": self.eigenvalues.tolist(),
            "note": "spectrum of zeta-induced geometry; not claimed equal to γ_n",
        }


@dataclass(frozen=True)
class Waypoint:
    sector_id: int
    backend: str
    epsilon_star: float
    gini_at_onset: float
    gini_slope_at_onset: float
    vector: np.ndarray
    waypoints: np.ndarray
    derivative_values: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_id": self.sector_id,
            "backend": self.backend,
            "epsilon_star": float(self.epsilon_star),
            "gini_at_onset": float(self.gini_at_onset),
            "gini_slope_at_onset": float(self.gini_slope_at_onset),
            "vector": self.vector.tolist(),
            "waypoints": self.waypoints.tolist(),
            "derivative_values": self.derivative_values.tolist(),
        }


@dataclass(frozen=True)
class ProbeReport:
    name: str
    verdict: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict, "detail": self.detail}


@dataclass(frozen=True)
class AnalysisResult:
    """Output of geometry-off-zetas analysis."""

    N: int
    d: int
    n_free: int
    best_residual: float
    sectors: tuple[Sector, ...]
    spectra: tuple[Spectrum, ...]
    waypoints: tuple[Waypoint, ...]
    probes: tuple[ProbeReport, ...]
    sheaf_backend: str
    waypoint_backend: str

    def gaps(self) -> np.ndarray:
        return np.array([s.spectral_gap for s in self.spectra], dtype=float)

    def twists(self) -> np.ndarray:
        return np.array([s.twist for s in self.spectra], dtype=float)

    def epsilon_stars(self) -> np.ndarray:
        return np.array([w.epsilon_star for w in self.waypoints], dtype=float)

    def summary(self) -> dict[str, Any]:
        return {
            "ontology": "geometry_off_zeta_field_not_actual_zeros",
            "N": self.N,
            "d": self.d,
            "n_sectors": len(self.sectors),
            "sheaf_backend": self.sheaf_backend,
            "waypoint_backend": self.waypoint_backend,
            "spectral_gaps": self.gaps().tolist(),
            "twists": self.twists().tolist(),
            "epsilon_stars": self.epsilon_stars().tolist(),
            "probes": [p.to_dict() for p in self.probes],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "sectors": [s.to_dict() for s in self.sectors],
            "spectra": [s.to_dict() for s in self.spectra],
            "waypoints": [w.to_dict() for w in self.waypoints],
        }
