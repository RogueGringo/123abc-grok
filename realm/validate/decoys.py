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


def _kabsch_rmsd_fixed(P: np.ndarray, Q: np.ndarray) -> float:
    """RMSD after optimal rotation (Kabsch); same length, already scaled/centered optional."""
    P = np.asarray(P, float)
    Q = np.asarray(Q, float)
    if P.shape[0] < 3 or P.shape != Q.shape:
        return 1e9
    P = P - P.mean(axis=0)
    Q = Q - Q.mean(axis=0)
    sp = np.sqrt(np.mean(np.sum(P**2, axis=1))) + 1e-15
    sq = np.sqrt(np.mean(np.sum(Q**2, axis=1))) + 1e-15
    P, Q = P / sp, Q / sq
    H = P.T @ Q
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt = Vt.copy()
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    P_aligned = P @ R
    return float(np.sqrt(np.mean(np.sum((P_aligned - Q) ** 2, axis=1))))


def _resample_ring(xyz: np.ndarray, n: int) -> np.ndarray:
    """Resample closed CA ring to n vertices along index (cyclic lerp)."""
    xyz = np.asarray(xyz, float)
    if xyz.shape[0] == n:
        return xyz.copy()
    # close the loop for interpolation
    closed = np.vstack([xyz, xyz[0]])
    t_src = np.linspace(0.0, 1.0, closed.shape[0])
    t_dst = np.linspace(0.0, 1.0, n, endpoint=False)
    out = np.column_stack([np.interp(t_dst, t_src, closed[:, i]) for i in range(3)])
    return out


def _kabsch_rmsd(P: np.ndarray, Q: np.ndarray, cyclic: bool = True) -> float:
    """RMSD after Kabsch; optional best cyclic start index on P."""
    P = np.asarray(P, float)
    Q = np.asarray(Q, float)
    n = min(P.shape[0], Q.shape[0])
    if n < 3:
        return 1e9
    P = _resample_ring(P, n)
    Q = _resample_ring(Q, n)
    if not cyclic or n > 24:
        return _kabsch_rmsd_fixed(P, Q)
    best = 1e9
    for s in range(n):
        best = min(best, _kabsch_rmsd_fixed(np.roll(P, s, axis=0), Q))
        # reverse orientation
        best = min(best, _kabsch_rmsd_fixed(np.roll(P[::-1], s, axis=0), Q))
    return float(best)


def score_geometry_vs_crit(
    xyz: np.ndarray,
    sector_points: list[np.ndarray],
    top_k: int = 3,
) -> dict[str, Any]:
    """Cyclic Kabsch distance to Crit sector ensemble.

    Uses mean of the *top_k* nearest sector templates (not hard min). The
    Crit mold is a multi-valley sheaf section; averaging the nearest few
    sectors is more stable for native-vs-decoy ranking than a single match.
    """
    if not sector_points:
        return {
            "mean_dist": 1e9,
            "method": "CRIT_KABSCH_TOPK",
            "in_basin": False,
            "n_templates": 0,
        }
    dists = np.sort(
        np.asarray(
            [_kabsch_rmsd(xyz, sp, cyclic=True) for sp in sector_points],
            dtype=float,
        )
    )
    k = max(1, min(int(top_k), dists.size))
    dmean = float(np.mean(dists[:k]))
    dmin = float(dists[0])
    return {
        "mean_dist": dmean,
        "min_dist": dmin,
        "method": "CRIT_KABSCH_TOPK",
        "in_basin": dmean < 0.35,
        "n_templates": len(sector_points),
        "top_k": k,
    }
