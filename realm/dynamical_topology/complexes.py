"""Per-stage kNN complex builders for dynamical topology (dual spine).

Informational only. Never retunes pin. Never ACCEPTANCE / soft_T.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from realm.kb_geometry.graph import knn_graph


def knn_adjacency(
    points: Sequence[Sequence[float]] | np.ndarray,
    k: int = 5,
) -> np.ndarray:
    """Return dense undirected kNN adjacency matrix for a point cloud.

    Thin wrapper over ``realm.kb_geometry.graph.knn_graph`` matrix field.
    Empty / single-point clouds yield a zero matrix of matching size.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    if pts.ndim != 2:
        raise ValueError(f"points must be 2-D, got shape {pts.shape}")
    n = int(pts.shape[0])
    if n == 0:
        return np.zeros((0, 0), dtype=float)
    if n == 1:
        return np.zeros((1, 1), dtype=float)
    g = knn_graph(pts, k=k)
    mat = g.get("matrix")
    if mat is None:
        return np.zeros((n, n), dtype=float)
    return np.asarray(mat, dtype=float)
