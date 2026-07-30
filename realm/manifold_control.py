"""Manifold control tuples for the fold protocol — Connes-compatible framing.

What Allen Connes would insist on
--------------------------------
1. Geometry is *spectral*: (A, H, D) first; coordinates second.
2. Spectral action Tr(f(D/Λ)) warps the moduli; Crit(S) is Morse selection.
3. Never claim λ=γ (zeros ≠ eigenvalues of D) without a full NC proof.
4. Consistency of the connection is kernel of the sheaf Laplacian L_F = δ*δ.
5. Control acts by admissible variations of holonomy / IR knobs in U,
   not by inventing new ontology mid-flight.

Maps onto the existing stack
----------------------------
  Σ  control-affine   → SpectralAction holonomy dynamics on M = S¹ (θ)
  D  distribution     → Δ = span{∂_θ, IR micro-axes}; ∇ = connection monodromy
  S  cellular sheaf   → G = C_N, F = R^d stalks, L_F = MaxOp/numpy L

Tuple-time (t, τ, resolution, F) advances until phenotype resolution maxes
(see realm.adaptive_evolve.until_resolved). Feedback = −grad sheaf energy.

Never λ=γ. ζ = substrate seed only (realm.ontology).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from realm.ontology import ONTOLOGY, ontology_note
from realm.sheaf_defects import (
    ca_to_stalk_section,
    defect_report_for_twist,
    dirichlet_energy,
)
from realm.cohesive import CohesiveHomotopyFunctor


# ---------------------------------------------------------------------------
# Formal tuples (documentation + runtime snapshots)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpectralTripleProxy:
    """Finite proxy of Connes spectral triple (A, H, D).

    Not a full NC spectral triple — discrete cycle + connection Laplacian.
    """

    algebra: str = "C(C_N) ≅ functions on cycle vertices"
    hilbert: str = "⊕_v F(v) ≅ (R^d)^N  (stalk Hilbert sum)"
    dirac: str = "connection Laplacian L_F = δ*δ (MaxOp/numpy)"
    spectral_action: str = "S_Λ(θ) = Σ w_n (1 − cos(ω_n θ))  [finite model]"
    never: tuple[str, ...] = ("lambda_eq_gamma",)

    def to_dict(self) -> dict[str, Any]:
        return {
            "A": self.algebra,
            "H": self.hilbert,
            "D": self.dirac,
            "spectral_action": self.spectral_action,
            "never": list(self.never),
            "note": "proxy only; continuum NC geometry not claimed",
        }


@dataclass(frozen=True)
class ControlAffineTuple:
    """Σ = (M, f, {g_i}, U) on holonomy / knob space."""

    M: str  # state manifold
    f: str  # drift
    g: tuple[str, ...]  # control fields
    U: str  # admissible controls

    def to_dict(self) -> dict[str, Any]:
        return {
            "Sigma": "control_affine",
            "M": self.M,
            "f": self.f,
            "g": list(self.g),
            "U": self.U,
            "evolution": "ẋ = f(x) + Σ u_i g_i(x)",
        }


@dataclass(frozen=True)
class DistributionTuple:
    """D = (M, Δ, ∇) sub-Riemannian / connection control."""

    M: str
    Delta: str
    nabla: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "D": "distribution_connection",
            "M": self.M,
            "Delta": self.Delta,
            "nabla": self.nabla,
            "chow": "bracket-generating on holonomy+IR axes (search-level, not Lie proof)",
        }


@dataclass(frozen=True)
class SheafControlTuple:
    """S = (G, F, L_F) cellular sheaf constraint control."""

    G: str
    F: str
    L_F: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "S": "cellular_sheaf",
            "G": self.G,
            "F": self.F,
            "L_F": self.L_F,
            "kernel": "ker L_F = globally consistent zero-frustration sections",
            "feedback": "u ∝ −∇ E, E = xᵀ L_F x (Dirichlet / coboundary residual)",
        }


@dataclass
class FoldControlArchitecture:
    """Full control stack for Crit→geometry fold protocol."""

    spectral_triple: SpectralTripleProxy = field(default_factory=SpectralTripleProxy)
    sigma: ControlAffineTuple = field(
        default_factory=lambda: ControlAffineTuple(
            M="S¹_θ × Knob⁸  (holonomy × SpectralAction parameters)",
            f="∇_θ S_Λ  (Witten–Morse drift toward Crit(S))",
            g=(
                "g_Λ: heat-cutoff / spectral action scale",
                "g_ω: frequency warp omega_scale",
                "g_w: weight_power / tier / low_boost",
                "g_IR: (w1,w2,w3) micro IR mults",
                "g_θ: holonomy sector selection (Crit bank)",
            ),
            U="evolve KNOB_BOUNDS + soft_T, defect_beta, mold bank",
        )
    )
    distribution: DistributionTuple = field(
        default_factory=lambda: DistributionTuple(
            M="C_N ⊂ R³ projected molds + SO(2) monodromy",
            Delta="span{∂_θ, IR axes} at each Crit sector (not full T M)",
            nabla="principal connection: cut-edge monodromy A(θ) on sheaf stalks",
        )
    )
    sheaf: SheafControlTuple = field(
        default_factory=lambda: SheafControlTuple(
            G="cycle graph C_N (peptide CA ring / combinatorial loop)",
            F="F(v)=R^d stalks; restriction I or A(θ) on cut edge",
            L_F="MaxOp CellularSheaf L=δ*δ (numpy fallback)",
        )
    )
    ontology: dict[str, Any] = field(default_factory=lambda: dict(ONTOLOGY))

    def to_dict(self) -> dict[str, Any]:
        return {
            "connes_proxy": self.spectral_triple.to_dict(),
            "control_affine_Sigma": self.sigma.to_dict(),
            "distribution_D": self.distribution.to_dict(),
            "sheaf_S": self.sheaf.to_dict(),
            "ontology_note": ontology_note(),
            "tuple_time": "(t, τ, resolution, F_total) — adaptive NS clock",
            "resolution_max": "stop when phenotype resolution stable (until_resolved)",
            "allen_connes_discipline": [
                "geometry_from_spectrum",
                "spectral_action_not_ad_hoc_potential",
                "never_lambda_eq_gamma",
                "kernel_L_is_consistency",
                "control_is_admissible_variation_of_D_and_knobs",
            ],
        }


def fold_control_snapshot() -> dict[str, Any]:
    """JSON-safe architecture card for stage ledger / evolve_ns payloads."""
    return FoldControlArchitecture().to_dict()


# ---------------------------------------------------------------------------
# Active feedback: sheaf energy descent on holonomy (discrete control step)
# ---------------------------------------------------------------------------

def sheaf_energy_at_twist(
    xyz: np.ndarray,
    twist: float,
    *,
    d: int = 2,
    prefer_maxop: bool = True,
) -> float:
    """E(θ) = xᵀ L(A(θ)) x for CA section — control cost on monodromy."""
    rep = defect_report_for_twist(
        xyz, float(twist), d=d, prefer_maxop=prefer_maxop, chord_weight=0.0
    )
    return float(rep["dirichlet_energy"])


def holonomy_feedback_step(
    xyz: np.ndarray,
    theta: float,
    *,
    step: float = 0.05,
    d: int = 2,
    prefer_maxop: bool = True,
) -> dict[str, Any]:
    """One control step: u = −sign(∂_θ E) along holonomy axis.

    Discrete finite-difference gradient descent on sheaf Dirichlet energy.
    Maps L_F kernel pursuit into an active feedback loop on θ ∈ S¹.
    """
    th = float(theta)
    e0 = sheaf_energy_at_twist(xyz, th, d=d, prefer_maxop=prefer_maxop)
    e_p = sheaf_energy_at_twist(xyz, th + step, d=d, prefer_maxop=prefer_maxop)
    e_m = sheaf_energy_at_twist(xyz, th - step, d=d, prefer_maxop=prefer_maxop)
    # central difference
    dE = (e_p - e_m) / (2.0 * step)
    u = -float(np.clip(dE, -1.0, 1.0))  # bounded control
    th_new = th + step * u
    # wrap to [0, 2π)
    twopi = 2.0 * np.pi
    th_new = float(th_new % twopi)
    e1 = sheaf_energy_at_twist(xyz, th_new, d=d, prefer_maxop=prefer_maxop)
    return {
        "theta_in": th,
        "theta_out": th_new,
        "E_in": e0,
        "E_out": e1,
        "dE_dtheta": float(dE),
        "u": u,
        "step": step,
        "improved": e1 < e0 - 1e-12,
        "control_law": "u = -clip(∂_θ E), E = x^T L_F(A(θ)) x",
        "tuple": "feedback on Sigma holonomy axis via sheaf cost",
    }


def multi_step_holonomy_control(
    xyz: np.ndarray,
    theta0: float,
    *,
    n_steps: int = 8,
    step: float = 0.05,
    prefer_maxop: bool = True,
) -> dict[str, Any]:
    """Iterate holonomy feedback; report trajectory toward lower sheaf energy."""
    th = float(theta0)
    traj = []
    for k in range(int(n_steps)):
        rec = holonomy_feedback_step(
            xyz, th, step=step, prefer_maxop=prefer_maxop
        )
        traj.append(rec)
        th = rec["theta_out"]
        if abs(rec["u"]) < 1e-6 and not rec["improved"]:
            break
    return {
        "theta0": float(theta0),
        "theta_final": th,
        "E0": traj[0]["E_in"] if traj else None,
        "E_final": traj[-1]["E_out"] if traj else None,
        "n_steps": len(traj),
        "trajectory": traj,
        "architecture": "sheaf_Laplacian_feedback_on_control_affine_holonomy",
    }


def consistent_section_residual(
    xyz: np.ndarray,
    twist: float,
    *,
    d: int = 2,
    prefer_maxop: bool = True,
) -> dict[str, Any]:
    """Distance-to-kernel proxy: normalized Dirichlet energy of CA section."""
    n = int(np.asarray(xyz).shape[0])
    fun = CohesiveHomotopyFunctor(N=n, d=d)
    A = fun.rotation_monodromy(float(twist))
    sec = ca_to_stalk_section(xyz, d=d)
    E, residuals, meta = dirichlet_energy(sec, A, prefer_maxop=prefer_maxop)
    mean_r = float(np.mean(residuals))
    return {
        "dirichlet_energy": E,
        "mean_edge_residual": mean_r,
        "near_kernel": bool(E < 1e-3 or mean_r < 0.05),
        "backend": meta.get("backend"),
        "operator_gap": meta.get("spectral_gap"),
        "interpretation": "small E ⇒ closer to ker L_F (global consistency)",
    }
