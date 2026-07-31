"""Graph geometry toolkit (Stalk C).

Transfer from: ACADEMIC Mathematics of Machine Learning
  (kNN, spectral clustering as geometry — not accept gates).

Helpers for multi-channel fiber graphs. Labels/scores are informational only.
Never retunes pin. Never sets SOLVED / ACCEPTANCE.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

KB_SOURCE = "ACADEMIC/Mathematics of Machine Learning (kNN / spectral clustering)"
TRANSFER_NOTE = "fiber graph geometry aid; not pin; not ACCEPTANCE"


def _as_matrix(X: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    a = np.asarray(X, dtype=float)
    if a.ndim == 1:
        a = a.reshape(-1, 1)
    if a.ndim != 2:
        raise ValueError(f"X must be 2-D, got shape {a.shape}")
    return a


def knn_graph(
    X: Sequence[Sequence[float]] | np.ndarray,
    k: int = 5,
    *,
    mutual: bool = False,
) -> dict[str, Any]:
    """Build a k-nearest-neighbor adjacency (unweighted, undirected).

    Uses Euclidean distance. Self-neighbors excluded.
    Returns adjacency list + dense matrix for small n.
    """
    pts = _as_matrix(X)
    n = int(pts.shape[0])
    k = max(1, min(int(k), max(1, n - 1)))
    if n == 0:
        return {
            "n": 0,
            "k": k,
            "adjacency": [],
            "edges": [],
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_graph_not_lambda_eq_gamma",
        }

    # Pairwise squared distances
    # (x-y)^2 = x^2 + y^2 - 2 x·y
    sq = np.sum(pts * pts, axis=1, keepdims=True)
    d2 = sq + sq.T - 2.0 * (pts @ pts.T)
    np.fill_diagonal(d2, np.inf)

    knn_idx = np.argsort(d2, axis=1)[:, :k]
    adj_sets: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in knn_idx[i]:
            j = int(j)
            if j < 0 or j >= n or j == i:
                continue
            if mutual:
                # defer mutual: add directed first
                adj_sets[i].add(j)
            else:
                adj_sets[i].add(j)
                adj_sets[j].add(i)

    if mutual:
        undirected: list[set[int]] = [set() for _ in range(n)]
        for i in range(n):
            for j in adj_sets[i]:
                if i in adj_sets[j]:
                    undirected[i].add(j)
                    undirected[j].add(i)
        adj_sets = undirected

    edges: list[tuple[int, int]] = []
    adj_list: list[list[int]] = []
    for i in range(n):
        nbrs = sorted(adj_sets[i])
        adj_list.append(nbrs)
        for j in nbrs:
            if i < j:
                edges.append((i, j))

    mat = np.zeros((n, n), dtype=float)
    for i, j in edges:
        mat[i, j] = 1.0
        mat[j, i] = 1.0

    return {
        "n": n,
        "k": k,
        "mutual": bool(mutual),
        "adjacency": adj_list,
        "edges": edges,
        "n_edges": len(edges),
        "matrix": mat,
        "not_acceptance": True,
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "ontology": "kb_geometry_graph_not_lambda_eq_gamma",
    }


def spectral_labels(
    adjacency: np.ndarray | dict[str, Any],
    n_clusters: int = 2,
    *,
    seed: int = 0,
) -> dict[str, Any]:
    """Spectral clustering labels from adjacency (info only).

    Uses unnormalized Laplacian L = D - A and k-means on bottom eigenvectors
    (excluding the trivial constant mode when possible).
    """
    if isinstance(adjacency, dict):
        mat = adjacency.get("matrix")
        if mat is None:
            n = int(adjacency.get("n") or 0)
            mat = np.zeros((n, n), dtype=float)
            for i, j in adjacency.get("edges") or []:
                mat[int(i), int(j)] = 1.0
                mat[int(j), int(i)] = 1.0
        A = np.asarray(mat, dtype=float)
    else:
        A = np.asarray(adjacency, dtype=float)

    n = int(A.shape[0]) if A.ndim == 2 else 0
    k = max(1, min(int(n_clusters), max(1, n)))
    if n == 0:
        return {
            "n": 0,
            "n_clusters": k,
            "labels": [],
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_spectral_not_lambda_eq_gamma",
        }
    if n == 1:
        return {
            "n": 1,
            "n_clusters": 1,
            "labels": [0],
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_spectral_not_lambda_eq_gamma",
        }

    A = 0.5 * (A + A.T)
    np.fill_diagonal(A, 0.0)
    deg = np.sum(A, axis=1)
    L = np.diag(deg) - A

    # Eigen-decomposition (symmetric)
    try:
        evals, evecs = np.linalg.eigh(L)
    except np.linalg.LinAlgError:
        return {
            "n": n,
            "n_clusters": k,
            "labels": [0] * n,
            "error": "eigh_failed",
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_spectral_not_lambda_eq_gamma",
        }

    # Bottom k eigenvectors (skip near-zero trivial if k>1 and n>k)
    idx = np.argsort(evals)
    take = idx[:k]
    emb = evecs[:, take]
    # Row-normalize embedding
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    emb = emb / norms

    labels = _kmeans_labels(emb, k, seed=seed)
    return {
        "n": n,
        "n_clusters": k,
        "labels": [int(x) for x in labels],
        "eigenvalues": [float(evals[i]) for i in take],
        "not_acceptance": True,
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "ontology": "kb_geometry_spectral_not_lambda_eq_gamma",
        "disclaimer": "Spectral labels are informational; never set SOLVED/ACCEPTANCE.",
    }


def _kmeans_labels(X: np.ndarray, k: int, *, seed: int = 0, n_iter: int = 25) -> np.ndarray:
    """Minimal k-means (numpy only)."""
    rng = np.random.default_rng(int(seed))
    n = X.shape[0]
    k = max(1, min(k, n))
    # init: random distinct points
    if n <= k:
        return np.arange(n) % k
    centers_idx = rng.choice(n, size=k, replace=False)
    centers = X[centers_idx].copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(n_iter):
        # assign
        d2 = np.sum((X[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(d2, axis=1)
        # update
        new_centers = centers.copy()
        for j in range(k):
            mask = labels == j
            if not np.any(mask):
                new_centers[j] = X[rng.integers(0, n)]
            else:
                new_centers[j] = X[mask].mean(axis=0)
        if np.allclose(new_centers, centers, atol=1e-8):
            break
        centers = new_centers
    return labels


def series_point_cloud(
    channels: dict[str, Sequence[float]],
    *,
    max_points: int = 64,
) -> np.ndarray:
    """Stack aligned channel series into (n, d) point cloud (subsampled)."""
    keys = sorted(channels.keys())
    if not keys:
        return np.zeros((0, 0), dtype=float)
    cols = []
    n = min(len(channels[k]) for k in keys)
    if n <= 0:
        return np.zeros((0, len(keys)), dtype=float)
    for k in keys:
        arr = np.asarray(list(channels[k])[:n], dtype=float)
        cols.append(arr)
    X = np.column_stack(cols)
    # replace nan with col mean
    for j in range(X.shape[1]):
        col = X[:, j]
        m = np.nanmean(col) if np.any(np.isfinite(col)) else 0.0
        col = np.where(np.isfinite(col), col, m)
        X[:, j] = col
    if X.shape[0] > max_points:
        idx = np.linspace(0, X.shape[0] - 1, max_points, dtype=int)
        X = X[idx]
    return X
