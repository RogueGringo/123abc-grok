"""MaxOp waypoint signatures W(C) on Coutsias 3D geometries.

Prefers primed-topology MaxOp (ripser + compute_waypoints). Falls back to a
lightweight H0 single-linkage proxy if MaxOp/ripser are unavailable so the
fire pipeline never dies on a missing optional dep.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform

logger = logging.getLogger(__name__)

_MAXOP_PATHS = [
    Path(__file__).resolve().parents[2] / "primed-topology" / "src",
    Path(r"C:\PRIMEdEV-1\primed-topology\src"),
]


def _import_maxop_waypoints():
    for p in _MAXOP_PATHS:
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        from maxop.filtration import rips_filtration
        from maxop.waypoint import compute_waypoints

        return rips_filtration, compute_waypoints
    except Exception as exc:  # noqa: BLE001
        logger.info("MaxOp waypoints unavailable (%s); using H0 proxy", exc)
        return None, None


rips_filtration, compute_waypoints = _import_maxop_waypoints()


@dataclass(frozen=True)
class GeometryWaypoint:
    state_id: int
    backend: str
    epsilon_star: float
    waypoints: np.ndarray
    derivative_values: np.ndarray
    gini_at_onset: float
    gini_slope_at_onset: float
    vector: np.ndarray
    n_points: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "backend": self.backend,
            "epsilon_star": float(self.epsilon_star),
            "waypoints": self.waypoints.tolist(),
            "derivative_values": self.derivative_values.tolist(),
            "gini_at_onset": float(self.gini_at_onset),
            "gini_slope_at_onset": float(self.gini_slope_at_onset),
            "vector": self.vector.tolist(),
            "n_points": int(self.n_points),
        }


def _h0_proxy_signature(cloud: np.ndarray, n_waypoints: int = 3) -> GeometryWaypoint:
    """Single-linkage merge heights as a cheap H0 persistence proxy."""
    X = np.asarray(cloud, dtype=float)
    if X.ndim != 2 or X.shape[0] < 3:
        z = np.zeros(2 * n_waypoints + 3)
        return GeometryWaypoint(
            state_id=0,
            backend="h0_proxy",
            epsilon_star=0.0,
            waypoints=np.zeros(n_waypoints),
            derivative_values=np.zeros(n_waypoints),
            gini_at_onset=0.0,
            gini_slope_at_onset=0.0,
            vector=z,
            n_points=int(X.shape[0]) if X.ndim == 2 else 0,
        )
    d = pdist(X)
    Z = linkage(d, method="single")
    # Merge heights = H0 death scales
    heights = np.sort(Z[:, 2])
    # epsilon* ~ 95th percentile of finite H0 deaths
    eps_star = float(np.percentile(heights, 95)) if heights.size else 0.0
    # Waypoints: top jumps in merge height
    jumps = np.diff(heights, prepend=0.0)
    order = np.argsort(-jumps)[:n_waypoints]
    wp = np.zeros(n_waypoints)
    wp_v = np.zeros(n_waypoints)
    for i, oi in enumerate(order):
        if oi < heights.size:
            wp[i] = heights[oi]
            wp_v[i] = jumps[oi]
    # Gini of merge heights
    x = np.sort(np.clip(heights, 0, None))
    if x.size and x.sum() > 0:
        n = x.size
        gini = float((2.0 * np.sum(np.arange(1, n + 1) * x)) / (n * x.sum()) - (n + 1) / n)
    else:
        gini = 0.0
    # Crude slope: gini of merges below vs above eps*
    below = heights[heights <= eps_star]
    above = heights[heights > eps_star]
    def _g(a):
        if a.size == 0 or a.sum() == 0:
            return 0.0
        a = np.sort(a)
        n = a.size
        return float((2.0 * np.sum(np.arange(1, n + 1) * a)) / (n * a.sum()) - (n + 1) / n)

    slope = _g(above) - _g(below)
    vec = np.concatenate([[eps_star], wp, wp_v, [gini, slope]])
    return GeometryWaypoint(
        state_id=0,
        backend="h0_proxy",
        epsilon_star=eps_star,
        waypoints=wp,
        derivative_values=wp_v,
        gini_at_onset=gini,
        gini_slope_at_onset=float(slope),
        vector=vec,
        n_points=X.shape[0],
    )


def signature_for_cloud(
    cloud: np.ndarray,
    state_id: int = 0,
    n_waypoints: int = 3,
    max_dim: int = 1,
) -> GeometryWaypoint:
    X = np.asarray(cloud, dtype=float)
    if X.ndim != 2:
        raise ValueError("cloud must be (n, d)")
    # Jitter identical points slightly for ripser stability
    if X.shape[0] >= 2 and float(np.max(pdist(X) if X.shape[0] > 1 else [0])) < 1e-12:
        X = X + 1e-6 * np.random.default_rng(0).normal(size=X.shape)

    if rips_filtration is not None and compute_waypoints is not None:
        try:
            filt = rips_filtration(X, max_dim=max_dim)
            sig = compute_waypoints(filt, k=1, n_waypoints=n_waypoints)
            vec = sig.as_vector()
            logger.info(
                "Waypoint state=%d backend=maxop ε*=%.4f gini=%.4f dim(W)=%d",
                state_id,
                sig.epsilon_star,
                sig.gini_at_onset,
                vec.size,
            )
            return GeometryWaypoint(
                state_id=state_id,
                backend="maxop",
                epsilon_star=float(sig.epsilon_star),
                waypoints=np.asarray(sig.waypoints, dtype=float),
                derivative_values=np.asarray(sig.derivative_values, dtype=float),
                gini_at_onset=float(sig.gini_at_onset),
                gini_slope_at_onset=float(sig.gini_slope_at_onset),
                vector=np.asarray(vec, dtype=float),
                n_points=X.shape[0],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MaxOp waypoint failed (%s); H0 proxy", exc)

    proxy = _h0_proxy_signature(X, n_waypoints=n_waypoints)
    logger.info(
        "Waypoint state=%d backend=h0_proxy ε*=%.4f gini=%.4f",
        state_id,
        proxy.epsilon_star,
        proxy.gini_at_onset,
    )
    return GeometryWaypoint(
        state_id=state_id,
        backend=proxy.backend,
        epsilon_star=proxy.epsilon_star,
        waypoints=proxy.waypoints,
        derivative_values=proxy.derivative_values,
        gini_at_onset=proxy.gini_at_onset,
        gini_slope_at_onset=proxy.gini_slope_at_onset,
        vector=proxy.vector,
        n_points=X.shape[0],
    )


def signatures_for_geometries(geometries, start_id: int = 1) -> list[GeometryWaypoint]:
    out = []
    for i, g in enumerate(geometries):
        # densify cloud slightly: original points + edge midpoints
        pts = np.asarray(g.positions, dtype=float)
        if pts.shape[0] >= 2:
            mids = 0.5 * (pts + np.roll(pts, -1, axis=0))
            cloud = np.vstack([pts, mids])
        else:
            cloud = pts
        out.append(signature_for_cloud(cloud, state_id=start_id + i))
    return out


def pairwise_waypoint_distance(sigs: list[GeometryWaypoint]) -> np.ndarray:
    """Distance matrix on packed W(C) vectors (zero-pad to common length)."""
    if not sigs:
        return np.zeros((0, 0))
    dim = max(s.vector.size for s in sigs)
    M = np.zeros((len(sigs), dim))
    for i, s in enumerate(sigs):
        M[i, : s.vector.size] = s.vector
    # standardize columns
    std = M.std(axis=0)
    std[std < 1e-12] = 1.0
    M = (M - M.mean(axis=0)) / std
    return squareform(pdist(M, metric="euclidean"))
