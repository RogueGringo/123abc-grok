"""CA decoys + mold ranking helpers (FALLBACK_THETA_PROXY for v1)."""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.lock_key import _circular_dist
from realm.projection import ModuliLandscape


def closure_residual(xyz: np.ndarray) -> float:
    xyz = np.asarray(xyz, dtype=float)
    if xyz.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(xyz[0] - xyz[-1]))


def make_ca_decoys(
    xyz: np.ndarray,
    n: int,
    rng: np.random.Generator,
    noise: float = 0.5,
    max_closure: float = 8.0,
) -> list[np.ndarray]:
    """Jitter CA coords; reject if ring ends far apart."""
    xyz = np.asarray(xyz, dtype=float)
    out: list[np.ndarray] = []
    attempts = 0
    while len(out) < n and attempts < n * 20:
        attempts += 1
        jitter = xyz + rng.normal(0.0, noise, size=xyz.shape)
        # re-center
        jitter = jitter - jitter.mean(axis=0)
        if closure_residual(jitter) <= max_closure:
            out.append(jitter)
    # pad with noisier samples if needed
    while len(out) < n:
        jitter = xyz + rng.normal(0.0, noise * 1.5, size=xyz.shape)
        jitter = jitter - jitter.mean(axis=0)
        out.append(jitter)
    return out


def theta_proxy_from_ca(xyz: np.ndarray) -> float:
    """Map ring shape to [0, 2π) via principal-plane polar angle of centroid chords.

    Labeled FALLBACK_THETA_PROXY in reports — not full holonomy reconstruction.
    """
    xyz = np.asarray(xyz, dtype=float)
    c = xyz.mean(axis=0)
    v = xyz - c
    # PCA plane
    _, _, vt = np.linalg.svd(v, full_matrices=False)
    plane = v @ vt[:2].T
    ang = np.arctan2(plane[:, 1], plane[:, 0])
    # mean resultant angle
    m = np.mean(np.exp(1j * ang))
    th = float(np.angle(m) % (2 * np.pi))
    return th


def score_geometry_on_mold(
    xyz: np.ndarray,
    landscape: ModuliLandscape,
    basin: float | None = None,
) -> dict[str, Any]:
    th = theta_proxy_from_ca(xyz)
    valleys = landscape.valleys or []
    if not valleys:
        return {
            "theta_proxy": th,
            "mean_dist": float(np.pi),
            "in_basin": False,
            "method": "FALLBACK_THETA_PROXY",
        }
    dists = [_circular_dist(th, float(v["theta"])) for v in valleys]
    dmin = float(min(dists))
    if basin is None:
        # reuse occupancy test scale if present
        basin = float(np.pi / len(valleys))
    return {
        "theta_proxy": th,
        "mean_dist": dmin,
        "in_basin": dmin <= basin,
        "method": "FALLBACK_THETA_PROXY",
        "basin": basin,
    }


def _kabsch_rmsd(P: np.ndarray, Q: np.ndarray) -> float:
    """RMSD after optimal rotation (Kabsch); centers both clouds."""
    P = np.asarray(P, float)
    Q = np.asarray(Q, float)
    n = min(P.shape[0], Q.shape[0])
    if n < 3:
        return 1e9
    # resample Q to n points along index if lengths differ
    if P.shape[0] != n:
        idx = np.linspace(0, P.shape[0] - 1, n).astype(int)
        P = P[idx]
    if Q.shape[0] != n:
        idx = np.linspace(0, Q.shape[0] - 1, n).astype(int)
        Q = Q[idx]
    P = P - P.mean(axis=0)
    Q = Q - Q.mean(axis=0)
    # scale to unit RMS so score is shape not size
    sp = np.sqrt(np.mean(np.sum(P**2, axis=1))) + 1e-15
    sq = np.sqrt(np.mean(np.sum(Q**2, axis=1))) + 1e-15
    P, Q = P / sp, Q / sq
    H = P.T @ Q
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    P_aligned = P @ R
    return float(np.sqrt(np.mean(np.sum((P_aligned - Q) ** 2, axis=1))))


def score_geometry_vs_crit(
    xyz: np.ndarray,
    sector_points: list[np.ndarray],
) -> dict[str, Any]:
    """Min Kabsch RMSD to Crit-induced sector geometries (shape match)."""
    if not sector_points:
        return {"mean_dist": 1e9, "method": "CRIT_KABSCH", "in_basin": False}
    dists = [_kabsch_rmsd(xyz, sp) for sp in sector_points]
    dmin = float(min(dists))
    return {
        "mean_dist": dmin,
        "method": "CRIT_KABSCH",
        "in_basin": dmin < 0.35,
        "n_templates": len(sector_points),
    }
