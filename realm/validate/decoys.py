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
