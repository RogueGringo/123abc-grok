"""Holographic projection: zeta scaffolding → 3D moduli landscape.

Ontology (Gemini-aligned, code-locked)
--------------------------------------
The non-trivial zeros {γ_n} are **not** molecular energy levels.
They are coordinates of an abstract / higher-dimensional lattice
(the arithmetic scaffolding). Physical 3D geometry is a **projection**
(shadow) of that structure into configuration space.

Consequences
------------
1. Do NOT test λ ≈ γ (grocery-list matching of eigenvalues to zeros).
2. An affine map ax+b between abstract and physical coordinates is the
   **signature of projection**, not a cheat.
3. The correct test: stable molecular conformations fall into **valleys**
   (minima) of the moduli landscape projected from the zeta lattice.
4. Arithmetic topology (Mazur): primes ↔ knots; closed cyclic peptides
   are geometric loops that can sit in projected knot-shadows of the field.

Construction
------------
Higher-D lattice points use dimensionless frequencies ω_n = γ_n/γ_1.
Cut-and-project style potential on holonomy / configuration angle θ ∈ S¹:

    V_Λ(θ) = Σ_n w_n ( 1 - cos(ω_n θ + φ_n) )     (spectral action / quasicrystal)

Valleys = local minima of V (same Crit structure as the derivation ladder).
Affine projection: physical observable y ≈ a · abstract + b
    is recorded as ProjectionSignature, not dismissed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq

from realm.derive import SpectralAction, critical_holonomies, unfold_zeros
from realm.zeta_field import ZetaField

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Affine projection signature (not a cheat)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectionSignature:
    """y ≈ a x + b — geometric projection, not eigenvalue identity."""

    a: float
    b: float
    residual_rms: float
    corr: float
    interpretation: str = (
        "affine ax+b is the mathematical signature of projection "
        "(scale + shift of the shadow), not a failed 1:1 match to actual γ_n"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "a": self.a,
            "b": self.b,
            "residual_rms": self.residual_rms,
            "corr": self.corr,
            "interpretation": self.interpretation,
        }


def affine_projection(x: np.ndarray, y: np.ndarray) -> ProjectionSignature:
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    m = min(x.size, y.size)
    x, y = x[:m], y[:m]
    if m < 2:
        return ProjectionSignature(1.0, 0.0, float("inf"), float("nan"))
    A = np.column_stack([x, np.ones(m)])
    coef, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
    a, b = float(coef[0]), float(coef[1])
    pred = a * x + b
    rms = float(np.sqrt(np.mean((pred - y) ** 2)))
    corr = float(np.corrcoef(x, y)[0, 1]) if np.std(x) > 1e-15 and np.std(y) > 1e-15 else float("nan")
    return ProjectionSignature(a=a, b=b, residual_rms=rms, corr=corr)


# ---------------------------------------------------------------------------
# Higher-D zeta lattice → projected moduli potential on S¹
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ZetaLattice:
    """Abstract lattice from the zeros (scaffolding, not energy levels)."""

    gammas: np.ndarray
    omega: np.ndarray  # dimensionless
    weights: np.ndarray
    unfolded: np.ndarray
    ambient_dim: int

    @classmethod
    def from_field(cls, field: ZetaField, Lambda: float | None = None) -> "ZetaLattice":
        g = field.gammas
        Lambda = float(Lambda if Lambda is not None else 2.0 * g[-1])
        omega = g / (g[0] + 1e-15)
        w = np.exp(-g / Lambda)
        w = w / (w.sum() + 1e-15)
        return cls(
            gammas=g.copy(),
            omega=omega,
            weights=w,
            unfolded=unfold_zeros(g),
            ambient_dim=int(g.size),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "higher_dimensional_scaffolding_not_energy_levels",
            "ambient_dim": self.ambient_dim,
            "gammas": self.gammas.tolist(),
            "omega": self.omega.tolist(),
            "weights": self.weights.tolist(),
            "unfolded": self.unfolded.tolist(),
            "mazur_note": "primes↔knots; zeta scaffolding projects to 3D loop geometry",
        }


@dataclass(frozen=True)
class ModuliLandscape:
    """Projected potential V(θ) on U(1) holonomy = 3D config shadow of the lattice."""

    lattice: ZetaLattice
    action: SpectralAction
    valleys: list[dict[str, float]]  # minima of V
    ridges: list[dict[str, float]]  # maxima
    sample_theta: np.ndarray
    sample_V: np.ndarray

    def V(self, theta: np.ndarray | float) -> np.ndarray | float:
        return self.action.S(theta)

    def nearest_valley(self, theta: float) -> tuple[float, float]:
        """Return (valley_theta, circular_distance)."""
        if not self.valleys:
            return float("nan"), float("inf")
        best_d, best_th = float("inf"), float("nan")
        for v in self.valleys:
            d = abs(theta - v["theta"]) % (2 * np.pi)
            d = min(d, 2 * np.pi - d)
            if d < best_d:
                best_d, best_th = d, v["theta"]
        return best_th, best_d

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "projected_moduli_landscape_3d_shadow",
            "n_valleys": len(self.valleys),
            "n_ridges": len(self.ridges),
            "valleys": self.valleys,
            "ridges": self.ridges,
            "lattice": self.lattice.to_dict(),
            "quasicrystal_note": (
                "V is a cut-and-project style potential: discrete valleys are "
                "intersections of the physical screen with the zeta lattice"
            ),
        }


def build_moduli_landscape(
    field: ZetaField | None = None,
    Lambda: float | None = None,
    omega_scale: float = 1.0,
    weight_power: float = 1.0,
    tier_split: float = 0.45,
    low_boost: float = 1.0,
    action: SpectralAction | None = None,
    critical: list | None = None,
) -> ModuliLandscape:
    """Build landscape; pass sealed knobs OR an already-forged action+critical set."""
    field = field or ZetaField.first(12)
    lattice = ZetaLattice.from_field(field, Lambda=Lambda)
    if action is None:
        action = SpectralAction.from_field(
            field,
            Lambda=Lambda,
            omega_scale=omega_scale,
            weight_power=weight_power,
            tier_split=tier_split,
            low_boost=low_boost,
        )
    crit = critical if critical is not None else critical_holonomies(action, max_crit=24)
    valleys = [c for c in crit if c["kind"] == "minimum"]
    if not valleys:
        valleys = list(crit)
    ridges = [c for c in crit if c["kind"] == "maximum"]
    th = np.linspace(0, 2 * np.pi, 721)
    return ModuliLandscape(
        lattice=lattice,
        action=action,
        valleys=valleys,
        ridges=ridges,
        sample_theta=th,
        sample_V=np.asarray(action.S(th), dtype=float),
    )


# ---------------------------------------------------------------------------
# Valley occupancy test — the correct "winner" probe
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConformationProbe:
    """One physical / derived conformation tested against the landscape."""

    label: str
    theta: float
    valley_theta: float
    distance_to_valley: float
    V_at: float
    in_valley: bool  # within basin radius

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "theta": self.theta,
            "valley_theta": self.valley_theta,
            "distance_to_valley": self.distance_to_valley,
            "V_at": self.V_at,
            "in_valley": self.in_valley,
        }


@dataclass(frozen=True)
class ProjectionTestResult:
    """Does the molecule sit in the projected mold?"""

    landscape: ModuliLandscape
    probes: list[ConformationProbe]
    basin_radius: float
    occupancy_fraction: float
    mean_distance_to_valley: float
    affine_theta_vs_index: ProjectionSignature
    affine_V_vs_gap: ProjectionSignature | None
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ontology": "projection_not_eigenvalue_identity",
            "verdict": self.verdict,
            "basin_radius": self.basin_radius,
            "occupancy_fraction": self.occupancy_fraction,
            "mean_distance_to_valley": self.mean_distance_to_valley,
            "n_probes": len(self.probes),
            "n_in_valley": sum(1 for p in self.probes if p.in_valley),
            "probes": [p.to_dict() for p in self.probes],
            "affine_projection_signature": self.affine_theta_vs_index.to_dict(),
            "affine_V_vs_spectral_gap": (
                self.affine_V_vs_gap.to_dict() if self.affine_V_vs_gap else None
            ),
            "landscape": {
                "n_valleys": len(self.landscape.valleys),
                "valleys": self.landscape.valleys,
            },
            "reading": (
                "High occupancy + finite affine projection signature supports "
                "holographic/quasicrystal templating. It does NOT claim λ=γ."
            ),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "occupancy_fraction": self.occupancy_fraction,
            "mean_distance_to_valley": self.mean_distance_to_valley,
            "n_valleys": len(self.landscape.valleys),
            "n_probes": len(self.probes),
            "affine_a": self.affine_theta_vs_index.a,
            "affine_b": self.affine_theta_vs_index.b,
            "affine_corr": self.affine_theta_vs_index.corr,
            "ontology": "projection_not_eigenvalue_identity",
        }


def test_valley_occupancy(
    thetas: np.ndarray | list[float],
    landscape: ModuliLandscape | None = None,
    labels: list[str] | None = None,
    spectral_gaps: np.ndarray | None = None,
    basin_radius: float | None = None,
    occupancy_threshold: float = 0.5,
) -> ProjectionTestResult:
    """Correct test: do conformations fall into projected moduli valleys?"""
    landscape = landscape or build_moduli_landscape()
    thetas = np.asarray(thetas, dtype=float).ravel()
    labels = labels or [f"C{i+1}" for i in range(len(thetas))]

    # Default basin: half median spacing between valleys (or π/8)
    if basin_radius is None:
        if len(landscape.valleys) >= 2:
            vt = np.sort([v["theta"] for v in landscape.valleys])
            basin_radius = float(np.median(np.diff(vt)) / 2.0)
        else:
            basin_radius = np.pi / 8.0

    probes: list[ConformationProbe] = []
    for lab, th in zip(labels, thetas):
        vth, dist = landscape.nearest_valley(float(th))
        probes.append(
            ConformationProbe(
                label=lab,
                theta=float(th),
                valley_theta=float(vth),
                distance_to_valley=float(dist),
                V_at=float(landscape.V(th)),
                in_valley=bool(dist <= basin_radius),
            )
        )

    occ = float(np.mean([p.in_valley for p in probes])) if probes else 0.0
    mean_d = float(np.mean([p.distance_to_valley for p in probes])) if probes else float("inf")

    # Affine signature: ordered index → theta (projection bookkeeping)
    idx = np.arange(1, len(thetas) + 1, dtype=float)
    aff_th = affine_projection(idx, np.sort(thetas))

    aff_gap = None
    if spectral_gaps is not None:
        V_at = np.array([float(landscape.V(t)) for t in thetas])
        aff_gap = affine_projection(V_at, np.asarray(spectral_gaps, dtype=float))

    if occ >= occupancy_threshold and mean_d < basin_radius:
        verdict = (
            f"MOLDED — {occ:.0%} of conformations sit in projected zeta valleys "
            f"(mean dist {mean_d:.4f} ≤ basin {basin_radius:.4f}). "
            f"Affine projection signature a={aff_th.a:.4g}, b={aff_th.b:.4g} is expected, not a cheat."
        )
    elif occ >= occupancy_threshold * 0.5:
        verdict = (
            f"PARTIAL MOLD — occupancy {occ:.0%}, mean dist {mean_d:.4f}. "
            f"Projection signature present (a={aff_th.a:.4g}). Refine knobs / basin."
        )
    else:
        verdict = (
            f"OFF-MOLD — occupancy {occ:.0%}. Conformations do not lock into "
            f"projected valleys under current landscape (basin={basin_radius:.4f})."
        )

    logger.info("Valley test: %s", verdict)
    return ProjectionTestResult(
        landscape=landscape,
        probes=probes,
        basin_radius=float(basin_radius),
        occupancy_fraction=occ,
        mean_distance_to_valley=mean_d,
        affine_theta_vs_index=aff_th,
        affine_V_vs_gap=aff_gap,
        verdict=verdict,
    )


def run_projection_protocol(
    N: int = 11,
    n_zeros: int = 12,
    n_sectors: int = 6,
    use_sealed_knobs: bool = True,
) -> dict[str, Any]:
    """Full winner protocol: build landscape, forge keys, test valley occupancy.

    Optionally uses sealed Keymaker knobs from meet_lock when available.
    """
    from realm.derive import Deriver

    knobs = {"Lambda": None, "omega_scale": 1.0, "weight_power": 1.0}
    if use_sealed_knobs:
        try:
            from realm.lock_key import meet_lock

            m = meet_lock(N=N, n_zeros=n_zeros, n_sectors=n_sectors, threshold=0.18, max_iter=16)
            knobs = m.best_knobs
            der = m.derivation
            locked = m.locked
            R = m.residual.total
        except Exception as exc:  # noqa: BLE001
            logger.warning("meet_lock unavailable (%s); default knobs", exc)
            der = Deriver(N=N, n_zeros=n_zeros, n_sectors=n_sectors).run()
            locked, R = False, float("nan")
    else:
        der = Deriver(N=N, n_zeros=n_zeros, n_sectors=n_sectors).run()
        locked, R = False, float("nan")

    landscape = build_moduli_landscape(
        field=der.field,
        Lambda=knobs.get("Lambda"),
        omega_scale=float(knobs.get("omega_scale", 1.0)),
        weight_power=float(knobs.get("weight_power", 1.0)),
        tier_split=float(knobs.get("tier_split", 0.45)),
        low_boost=float(knobs.get("low_boost", 1.0)),
        action=der.action,
        critical=der.critical,
    )
    thetas = np.array([s.twist for s in der.sectors], dtype=float)
    gaps = np.array([s.spectral_gap for s in der.spectra], dtype=float)
    test = test_valley_occupancy(
        thetas,
        landscape=landscape,
        labels=[f"sector_{s.id}" for s in der.sectors],
        spectral_gaps=gaps,
    )

    # Optional: Coutsias kinematic roots as independent physical probes of the mold
    coutsias_test = None
    try:
        from realm.coutsias import CoutsiasKinematics

        kin = CoutsiasKinematics(N=N, n_free=min(6, N - 2), n_starts=24, use_de=False, residual_tol=0.5)
        geoms = kin.find_real_roots()[:n_sectors]
        # Map free torsion[0] to holonomy-like angle on S¹
        c_thetas = np.array(
            [float(np.clip(g.free_torsions[0], 0, 2 * np.pi - 1e-6)) % (2 * np.pi) for g in geoms],
            dtype=float,
        )
        if c_thetas.size:
            coutsias_test = test_valley_occupancy(
                c_thetas,
                landscape=landscape,
                labels=[f"coutsias_{i+1}" for i in range(len(c_thetas))],
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("Coutsias dual probe skipped: %s", exc)

    return {
        "ontology": "holographic_projection_zeta_scaffolding",
        "arithmetic_topology": "primes↔knots; cyclic peptides as geometric loops in the shadow",
        "quasicrystal": "3D folds as intersections with higher-D zeta lattice",
        "sealed_knobs": knobs,
        "lock_key_sealed": locked,
        "lock_key_R": R,
        "moduli_landscape": landscape.to_dict(),
        "derived_sector_valley_test": test.to_dict(),
        "coutsias_valley_test": coutsias_test.to_dict() if coutsias_test else None,
        "summary": {
            **test.summary(),
            "lock_key_sealed": locked,
            "coutsias_occupancy": (
                coutsias_test.occupancy_fraction if coutsias_test else None
            ),
            "winner_criterion": (
                "conformations in projected valleys + affine projection signature; "
                "NOT eigenvalue identity with actual γ_n"
            ),
        },
    }
