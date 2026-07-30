"""Coutsias-style multi-start 3D loop closure for cyclic N-mers.

Finds discrete conformational sectors by minimizing a loop-closure energy
over free torsions (the classical Coutsias free-DOF motif), then extracts:

  • algebraic root labels t_i = tan(φ_i / 2) for the primary free torsion
  • 3D closed geometries
  • SO(3) holonomy of the discrete Frenet/Bishop frame around the cycle
  • SO(2) twist for monodromy Laplacians

This is computational kinematics — multi-basin optimization — not a claim of
the full 16th-degree Coutsias resultant, but it *does* produce multiple real
sectors with geometry-derived twists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


def _rodrigues(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    n = np.linalg.norm(axis)
    if n < 1e-15:
        return np.eye(3)
    k = axis / n
    K = np.array(
        [[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]], dtype=float
    )
    return np.eye(3) + np.sin(angle) * K + (1.0 - np.cos(angle)) * (K @ K)


def _frame_step(pos, x, y, z, bond, bond_angle, torsion):
    ca = np.cos(np.pi - bond_angle)
    sa = np.sin(np.pi - bond_angle)
    d_local = np.array([sa, 0.0, ca], dtype=float)
    R_t = _rodrigues(z, torsion)
    d = R_t @ (x * d_local[0] + y * d_local[1] + z * d_local[2])
    nrm = np.linalg.norm(d)
    d = d / (nrm + 1e-15)
    new_pos = pos + bond * d
    new_z = d
    new_x = x - np.dot(x, new_z) * new_z
    if np.linalg.norm(new_x) < 1e-10:
        new_x = y - np.dot(y, new_z) * new_z
    new_x = new_x / (np.linalg.norm(new_x) + 1e-15)
    new_y = np.cross(new_z, new_x)
    new_y = new_y / (np.linalg.norm(new_y) + 1e-15)
    return new_pos, new_x, new_y, new_z


@dataclass(frozen=True)
class ClosedGeometry:
    root_t: float
    residual: float
    positions: np.ndarray
    holonomy_R: np.ndarray
    holonomy_angle: float
    twist_so2: float
    position_error: float
    orientation_error: float
    free_torsions: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_t": float(self.root_t),
            "residual": float(self.residual),
            "holonomy_angle": float(self.holonomy_angle),
            "twist_so2": float(self.twist_so2),
            "position_error": float(self.position_error),
            "orientation_error": float(self.orientation_error),
            "free_torsions": list(self.free_torsions),
            "positions": self.positions.tolist(),
            "holonomy_R": self.holonomy_R.tolist(),
        }


class CoutsiasKinematics:
    """N-residue backbone with 6 free torsions (Coutsias 6-DOF loop motif).

    Multi-start L-BFGS-B + optional differential-evolution polish finds discrete
    near-closure sectors. Geometries are soft-closed for topology (waypoints)
    while residual reports the true open-chain closure energy.
    """

    def __init__(
        self,
        N: int = 11,
        bond_length: float = 1.53,
        base_bond_angle: float = np.deg2rad(111.0),
        residual_tol: float = 0.35,
        n_starts: int = 64,
        n_free: int = 6,
        rng_seed: int = 11,
        use_de: bool = True,
    ):
        if N < 6:
            raise ValueError("N >= 6 required")
        self.N = N
        self.bond_length = bond_length
        self.residual_tol = residual_tol
        self.n_starts = n_starts
        self.n_free = int(np.clip(n_free, 3, min(6, N - 2)))
        self.use_de = use_de
        self.rng = np.random.default_rng(rng_seed)

        self.bond_angles = np.full(N, base_bond_angle, dtype=float)
        self.bond_angles += 0.05 * np.sin(2 * np.pi * np.arange(N) / N)
        self.bond_angles[0] -= np.deg2rad(6.0)
        self.bond_angles[N // 2] += np.deg2rad(4.0)

        self.torsion_base = np.full(N, np.deg2rad(180.0), dtype=float)
        # seed secondary-structure-ish pattern
        for i in range(N):
            self.torsion_base[i] = np.deg2rad(180.0 if i % 3 else -60.0)
        self.torsion_base[0] = np.deg2rad(-60.0)
        self.torsion_base[1] = np.deg2rad(-45.0)
        self.torsion_base[N // 3] = np.deg2rad(70.0)

        # Free torsion indices spaced around the cycle (6-DOF Coutsias motif)
        # Classic loop closure uses 6 torsional DOF for SE(3) end-effector.
        spaced = np.linspace(1, N - 2, self.n_free, dtype=int)
        self.free_idx = sorted(set(int(i) for i in spaced))
        while len(self.free_idx) < self.n_free:
            for j in range(1, N - 1):
                if j not in self.free_idx:
                    self.free_idx.append(j)
                if len(self.free_idx) >= self.n_free:
                    break
        self.free_idx = self.free_idx[: self.n_free]
        self.n_free = len(self.free_idx)

    def torsions_from_free(self, free: np.ndarray) -> np.ndarray:
        tau = self.torsion_base.copy()
        for i, idx in enumerate(self.free_idx):
            tau[idx % self.N] = float(free[i])
        return tau

    def build_open_chain(self, free: np.ndarray):
        tau = self.torsions_from_free(free)
        pos = np.zeros(3)
        x = np.array([1.0, 0.0, 0.0])
        y = np.array([0.0, 1.0, 0.0])
        z = np.array([0.0, 0.0, 1.0])
        x0, y0, z0 = x.copy(), y.copy(), z.copy()
        pts = [pos.copy()]
        for i in range(self.N):
            pos, x, y, z = _frame_step(
                pos, x, y, z, self.bond_length, self.bond_angles[i], tau[i]
            )
            pts.append(pos.copy())
        return np.asarray(pts), (x0, y0, z0), (x, y, z)

    def closure_energy(self, free: np.ndarray) -> float:
        pts, (x0, y0, z0), (xf, yf, zf) = self.build_open_chain(free)
        pos_err = np.linalg.norm(pts[-1]) / self.bond_length
        R0 = np.column_stack([x0, y0, z0])
        Rf = np.column_stack([xf, yf, zf])
        H = R0.T @ Rf
        U, _, Vt = np.linalg.svd(H)
        H = U @ Vt
        if np.linalg.det(H) < 0:
            U[:, -1] *= -1
            H = U @ Vt
        orient_err = np.linalg.norm(H - np.eye(3), ord="fro")
        return float(pos_err + 0.5 * orient_err)

    @staticmethod
    def soft_close_positions(pts: np.ndarray) -> np.ndarray:
        """Distribute end-to-start gap along the chain (topology-friendly close)."""
        P = np.asarray(pts, dtype=float).copy()
        if P.shape[0] < 2:
            return P
        gap = P[-1] - P[0]
        n = P.shape[0]
        for i in range(n):
            P[i] = P[i] - gap * (i / max(n - 1, 1))
        P = P - P.mean(axis=0)
        return P

    def holonomy_and_geometry(self, free: np.ndarray) -> ClosedGeometry:
        pts, (x0, y0, z0), (xf, yf, zf) = self.build_open_chain(free)
        pos_err = float(np.linalg.norm(pts[-1]))
        R0 = np.column_stack([x0, y0, z0])
        Rf = np.column_stack([xf, yf, zf])
        H = R0.T @ Rf
        U, _, Vt = np.linalg.svd(H)
        H = U @ Vt
        if np.linalg.det(H) < 0:
            U[:, -1] *= -1
            H = U @ Vt
        orient_err = float(np.linalg.norm(H - np.eye(3), ord="fro"))
        residual = self.closure_energy(free)

        tr = float(np.clip((np.trace(H) - 1.0) / 2.0, -1.0, 1.0))
        hol_ang = float(np.arccos(tr))
        K = 0.5 * (H - H.T)
        axis = np.array([K[2, 1], K[0, 2], K[1, 0]], dtype=float)
        n = np.linalg.norm(axis)
        sign = 1.0
        if n > 1e-12:
            axis /= n
            sign = 1.0 if float(axis[2]) >= 0 else -1.0
        twist = float(sign * hol_ang)
        if abs(twist) < 1e-6:
            tau = self.torsions_from_free(free)
            twist = float(np.sum(tau) % (2 * np.pi) - np.pi)

        # Soft-closed N-atom ring for waypoint / VR topology
        atom_pts = self.soft_close_positions(pts[: self.N])

        half = 0.5 * float(np.clip(free[0], -np.pi + 0.05, np.pi - 0.05))
        root_t = float(np.clip(np.tan(half), -50.0, 50.0))
        return ClosedGeometry(
            root_t=root_t,
            residual=float(residual),
            positions=atom_pts,
            holonomy_R=H,
            holonomy_angle=hol_ang,
            twist_so2=twist,
            position_error=pos_err,
            orientation_error=orient_err,
            free_torsions=tuple(float(x) for x in free),
        )

    def find_real_roots(self) -> list[ClosedGeometry]:
        """Multi-start over n_free torsions; optional DE global seeds."""
        nf = self.n_free
        bounds = [(-np.pi, np.pi)] * nf
        seeds: list[np.ndarray] = []

        # Latin-ish random starts
        for _ in range(self.n_starts):
            seeds.append(self.rng.uniform(-np.pi, np.pi, size=nf))
        # Axis-aligned structured seeds on first 3 coords
        for a in np.linspace(-np.pi, np.pi, 4, endpoint=False):
            for b in np.linspace(-np.pi, np.pi, 3, endpoint=False):
                v = np.zeros(nf)
                v[0], v[1] = a, b
                if nf > 2:
                    v[2] = -0.5 * a
                seeds.append(v)

        # Differential evolution global polish (few iterations) for tighter basins
        if self.use_de and nf <= 6:
            try:
                from scipy.optimize import differential_evolution

                de = differential_evolution(
                    self.closure_energy,
                    bounds=bounds,
                    maxiter=18,
                    popsize=8,
                    seed=int(self.rng.integers(0, 1_000_000)),
                    polish=True,
                    atol=1e-6,
                )
                seeds.insert(0, np.asarray(de.x, dtype=float))
                logger.info("DE seed residual=%.4f", float(de.fun))
            except Exception as exc:  # noqa: BLE001
                logger.info("DE skipped (%s)", exc)

        results: list[ClosedGeometry] = []
        for seed in seeds:
            res = minimize(
                self.closure_energy,
                seed,
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 200, "ftol": 1e-12},
            )
            free = np.asarray(res.x, dtype=float)
            geo = self.holonomy_and_geometry(free)
            results.append(geo)

        results = self._cluster(results)
        results.sort(key=lambda g: g.residual)
        # Prefer true closures; pad with best near-closures
        tight = [g for g in results if g.residual <= self.residual_tol]
        if len(tight) >= 4:
            results = tight[:8]
        else:
            results = results[:8]

        logger.info(
            "Coutsias N=%d n_free=%d: %d sectors (best residual=%.4f, tol=%.3f)",
            self.N,
            nf,
            len(results),
            results[0].residual if results else float("nan"),
            self.residual_tol,
        )
        for i, g in enumerate(results):
            logger.info(
                "  sector[%d] t=%+.4f r=%.4f hol=%.4f twist=%+.4f pos_err=%.3f |free|=%d",
                i + 1,
                g.root_t,
                g.residual,
                g.holonomy_angle,
                g.twist_so2,
                g.position_error,
                len(g.free_torsions),
            )
        return results

    @staticmethod
    def _cluster(
        geoms: list[ClosedGeometry],
        tw_eps: float = 0.15,
        free_eps: float = 0.45,
    ) -> list[ClosedGeometry]:
        geoms = sorted(geoms, key=lambda g: g.residual)
        kept: list[ClosedGeometry] = []
        for g in geoms:
            dup = False
            gv = np.array(g.free_torsions)
            for h in kept:
                hv = np.array(h.free_torsions)
                # pad to compare
                m = max(gv.size, hv.size)
                gvv, hvv = np.zeros(m), np.zeros(m)
                gvv[: gv.size] = gv
                hvv[: hv.size] = hv
                if np.linalg.norm(gvv - hvv) < free_eps:
                    dup = True
                    break
                if abs(g.twist_so2 - h.twist_so2) < tw_eps and abs(g.residual - h.residual) < 0.05:
                    dup = True
                    break
            if not dup:
                kept.append(g)
        return kept


def cyclosporin_roots(N: int = 11, max_roots: int = 8) -> tuple[list[float], list[ClosedGeometry]]:
    kin = CoutsiasKinematics(N=N)
    geoms = kin.find_real_roots()[:max_roots]
    return [g.root_t for g in geoms], geoms
