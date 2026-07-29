"""Cohesive monodromy engine: roots → holonomy → connection Laplacian → spectrum.

Shape/flat/sharp language is retained as an *organizational* map onto:
  shape  – combinatorial type of the cycle (S^1 / C_N)
  flat   – holonomy-frustration diagnostic (closed-form + spectral)
  sharp  – concrete connection Laplacian L(θ) and its spectrum

This is computational spectral geometry on a twisted cycle graph, not an
implementation of cohesive ∞-topos theory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.linalg import eigh

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StateSpectrum:
    """One conformational sector after monodromy concretification."""

    state_id: int
    root: float
    twist: float
    monodromy: np.ndarray
    laplacian: np.ndarray
    eigenvalues: np.ndarray
    spectral_gap: float
    lambda_min: float
    frustration_closed_form: float
    is_flat: bool
    partition_function: float
    cohomology_note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "root": float(self.root),
            "twist": float(self.twist),
            "twist_over_pi": float(self.twist / np.pi),
            "spectral_gap": float(self.spectral_gap),
            "lambda_min": float(self.lambda_min),
            "frustration_closed_form": float(self.frustration_closed_form),
            "is_flat": bool(self.is_flat),
            "partition_function": float(self.partition_function),
            "cohomology_note": self.cohomology_note,
            "eigenvalues": self.eigenvalues.tolist(),
        }


class CohesiveHomotopyFunctor:
    """Cycle-graph connection Laplacian functor for N-residue loops.

    Parameters
    ----------
    N : int
        Number of nodes on the cycle (peptide residues). Cyclosporin A → 11.
    d : int
        Fiber / stalk dimension (dihedral deviation channels). Default 2 → SO(2).
    temperature : float
        Inverse-temperature scale for the heat-kernel partition function.
    """

    def __init__(self, N: int = 11, d: int = 2, temperature: float = 0.05):
        """temperature default 0.05 so Z is gap-sensitive (T=1 is bulk-dominated)."""
        if N < 3:
            raise ValueError("N must be >= 3 for a cycle")
        if d < 1:
            raise ValueError("d must be >= 1")
        self.N = N
        self.d = d
        self.temperature = temperature

    # --- modalities (computational reading) ---------------------------------

    def shape_modality(self) -> dict[str, str]:
        """Combinatorial type of C_N ≃ S^1 (declarative, not a homology solver)."""
        logger.info("Shape modality: C_N combinatorial type → S^1 / K(Z,1)")
        return {
            "topological_type": "S^1",
            "homology": "H_1(X, Z) = Z",
            "fundamental_groupoid": "pi_1(X) = Z",
            "cells": f"C_{self.N}",
        }

    def flat_modality(self, twist: float) -> dict[str, Any]:
        """Holonomy-frustration diagnostic on the cycle.

        Closed-form ground-state strain for U(1)-like twist on C_N:
            λ_min(θ) = 2 - 2 cos(θ / N)
        Flat (θ ≈ 0) ⇒ full fiber of global sections; nonzero twist collapses H^0.
        """
        is_flat = bool(np.isclose(twist, 0.0, atol=1e-12))
        frustration = 0.0 if is_flat else float(2.0 - 2.0 * np.cos(twist / self.N))
        if is_flat:
            note = f"H^0 ~ R^{self.d} (exact flat sections, zero monodromy strain)"
        else:
            note = "H^0 collapsed (holonomy anomaly / residual twist strain)"
        logger.info(
            "Flat modality: θ=%.6f is_flat=%s frustration_cf=%.6f",
            twist,
            is_flat,
            frustration,
        )
        return {
            "is_flat": is_flat,
            "frustration_closed_form": frustration,
            "cohomology_note": note,
        }

    def rotation_monodromy(self, twist: float) -> np.ndarray:
        """Build d×d monodromy. d=2 → planar rotation; d=1 → cos; d>2 → block-diagonal SO(2)."""
        if self.d == 1:
            return np.array([[np.cos(twist)]], dtype=float)
        A = np.eye(self.d, dtype=float)
        # Embed SO(2) blocks along the diagonal; leftover 1D stays 1.
        for k in range(self.d // 2):
            i = 2 * k
            c, s = np.cos(twist), np.sin(twist)
            A[i : i + 2, i : i + 2] = np.array([[c, -s], [s, c]], dtype=float)
        if self.d % 2 == 1:
            A[-1, -1] = np.cos(twist)
        return A

    def sharp_modality(self, monodromy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Concrete connection Laplacian L on the cycle with closing monodromy A.

        For ordinary edges: off-diagonal −I_d.
        For the cut edge (N-1 → 0): off-diagonal −A / −Aᵀ.
        Diagonal blocks accumulate degree contributions (standard graph Laplacian
        structure lifted to R^d stalks).
        """
        A = np.asarray(monodromy, dtype=float)
        if A.shape != (self.d, self.d):
            raise ValueError(f"monodromy shape {A.shape} != ({self.d}, {self.d})")

        dim = self.N * self.d
        L = np.zeros((dim, dim), dtype=float)
        I = np.eye(self.d, dtype=float)

        for i in range(self.N):
            j = (i + 1) % self.N
            bi, bj = i * self.d, j * self.d
            L[bi : bi + self.d, bi : bi + self.d] += I
            L[bj : bj + self.d, bj : bj + self.d] += I
            if i == self.N - 1:
                L[bi : bi + self.d, bj : bj + self.d] -= A
                L[bj : bj + self.d, bi : bi + self.d] -= A.T
            else:
                L[bi : bi + self.d, bj : bj + self.d] -= I
                L[bj : bj + self.d, bi : bi + self.d] -= I

        # Numerical symmetrization (float drift on non-orthogonal A)
        L = 0.5 * (L + L.T)
        eigenvalues = eigh(L, eigvals_only=True)
        eigenvalues = np.sort(np.real(eigenvalues))
        return L, eigenvalues

    def partition_function(self, eigenvalues: np.ndarray, temperature: float | None = None) -> float:
        """Z = Tr exp(-L / T) = sum_k exp(-λ_k / T)."""
        T = self.temperature if temperature is None else temperature
        if T <= 0:
            raise ValueError("temperature must be positive")
        # Stable: shift by min eigenvalue so largest term is O(1)
        lam = np.asarray(eigenvalues, dtype=float)
        shifted = lam - lam.min()
        return float(np.sum(np.exp(-shifted / T)) * np.exp(-lam.min() / T))

    @staticmethod
    def spectral_gap(eigenvalues: np.ndarray, atol: float = 1e-10) -> float:
        """First eigenvalue strictly above the numerical kernel."""
        lam = np.sort(np.real(np.asarray(eigenvalues, dtype=float)))
        for val in lam:
            if val > atol:
                return float(val)
        return 0.0

    # --- root → sector map --------------------------------------------------

    def root_to_twist(self, root: float, mode: str = "pi_scale") -> float:
        """Map a scalar algebraic root into a holonomy angle.

        Modes
        -----
        pi_scale : θ = r · π  (legacy cohesive stub; explicit free convention)
        atan     : θ = 2 atan(r)  (bounded in (-π, π), smoother near 0)
        raw      : θ = r  (radians as-given)
        """
        r = float(root)
        if mode == "pi_scale":
            return r * np.pi
        if mode == "atan":
            return 2.0 * np.arctan(r)
        if mode == "raw":
            return r
        raise ValueError(f"unknown root_to_twist mode: {mode}")

    def evaluate_state(
        self,
        state_id: int,
        root: float,
        twist_mode: str = "pi_scale",
    ) -> StateSpectrum:
        twist = self.root_to_twist(root, mode=twist_mode)
        shape = self.shape_modality()  # noqa: F841 — declarative side-effect log
        flat = self.flat_modality(twist)
        A = self.rotation_monodromy(twist)
        L, eigs = self.sharp_modality(A)
        gap = self.spectral_gap(eigs)
        Z = self.partition_function(eigs)
        return StateSpectrum(
            state_id=state_id,
            root=float(root),
            twist=float(twist),
            monodromy=A,
            laplacian=L,
            eigenvalues=eigs,
            spectral_gap=gap,
            lambda_min=float(eigs[0]),
            frustration_closed_form=float(flat["frustration_closed_form"]),
            is_flat=bool(flat["is_flat"]),
            partition_function=Z,
            cohomology_note=str(flat["cohomology_note"]),
        )

    def run(self, roots: list[float] | np.ndarray, twist_mode: str = "pi_scale") -> list[StateSpectrum]:
        """Evaluate the functor on a list of algebraic roots (e.g. Coutsias)."""
        logger.info(
            "Cohesive functor pipeline: N=%d d=%d n_roots=%d twist_mode=%s",
            self.N,
            self.d,
            len(roots),
            twist_mode,
        )
        results: list[StateSpectrum] = []
        for idx, root in enumerate(roots):
            state = self.evaluate_state(idx + 1, float(root), twist_mode=twist_mode)
            results.append(state)
            logger.info(
                "State %d | root=%.4f | θ/π=%.3f | λ_gap=%.6f | λ_min=%.6e | Z=%.6f | flat=%s",
                state.state_id,
                state.root,
                state.twist / np.pi,
                state.spectral_gap,
                state.lambda_min,
                state.partition_function,
                state.is_flat,
            )
        return results
