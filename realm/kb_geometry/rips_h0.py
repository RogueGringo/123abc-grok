"""Vietoris–Rips H0 + graph algebraic connectivity (Parent KB H1).

Audit decision (parent KB):
  - PYTHON CODE LIBRARY-6/persistent_homology.py: H0 union-find is incomplete
    (bars born at 0 die at inf without scale tracking) → **reimplement**, do not import.
  - sheaf_laplacian_calibration_v0.3: λ1 monitoring idea is useful → thin **reimplement**
    on our knn adjacency (no YAML hypergraph dependency).
  - sheaf_engine.py: codebase-as-manifold consciousness stack → **do not import**
    (different product; MaxOp sheaf in realm/sheaf_backend remains operational L).

Informational only. Never retunes pin. Never ACCEPTANCE.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

KB_SOURCE = (
    "Parent KB audit: LIBRARY-6 persistent_homology + sheaf_laplacian_calibration "
    "(patterns only; cleaned reimplementation)"
)
TRANSFER_NOTE = (
    "VR H0 with proper elder-rule births/deaths; λ1 of channel graph Laplacian"
)


def _pairwise_dist(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    # squared distances then sqrt
    sq = np.sum(X * X, axis=1, keepdims=True)
    d2 = np.maximum(sq + sq.T - 2.0 * (X @ X.T), 0.0)
    np.fill_diagonal(d2, 0.0)
    return np.sqrt(d2)


def vietoris_rips_h0(
    points: Sequence[Sequence[float]] | np.ndarray,
    *,
    long_frac: float = 0.25,
) -> dict[str, Any]:
    """0-dimensional Vietoris–Rips persistence (union-find, elder rule).

    Edges sorted by length; components merge with younger death at merge scale.
    Essential components die at diameter (finite stand-in for +∞).
    """
    X = np.asarray(points, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    n = int(X.shape[0])
    if n == 0:
        return {
            "kind": "vietoris_rips_h0",
            "n": 0,
            "bars": [],
            "n_long": 0,
            "n_short": 0,
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_rips_h0_not_lambda_eq_gamma",
        }
    if n == 1:
        return {
            "kind": "vietoris_rips_h0",
            "n": 1,
            "bars": [{"birth": 0.0, "death": 0.0, "persistence": 0.0, "long": False}],
            "n_long": 0,
            "n_short": 1,
            "diameter": 0.0,
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_rips_h0_not_lambda_eq_gamma",
        }

    D = _pairwise_dist(X)
    diameter = float(D.max()) if n > 1 else 0.0
    edges: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            edges.append((float(D[i, j]), i, j))
    edges.sort(key=lambda t: t[0])

    parent = list(range(n))
    rank = [0] * n
    birth = [0.0] * n  # all points born at scale 0
    deaths: list[tuple[float, float]] = []

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for d, i, j in edges:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        bi, bj = birth[ri], birth[rj]
        # elder rule
        if bi < bj or (bi == bj and ri < rj):
            parent[rj] = ri
            deaths.append((bj, d))
            if rank[ri] == rank[rj]:
                rank[ri] += 1
        else:
            parent[ri] = rj
            deaths.append((bi, d))
            if rank[rj] == rank[ri]:
                rank[rj] += 1

    roots = {find(i) for i in range(n)}
    # essential: die at diameter + eps (finite)
    death_inf = diameter + max(diameter * 0.01, 1e-9)
    for r in roots:
        deaths.append((birth[r], death_inf))

    thr = float(long_frac) * max(diameter, 1e-15)
    bars = []
    n_long = 0
    for b, dth in deaths:
        p = float(dth - b)
        long = p > thr
        if long:
            n_long += 1
        bars.append(
            {
                "birth": float(b),
                "death": float(dth),
                "persistence": p,
                "long": long,
                "dim": 0,
            }
        )

    return {
        "kind": "vietoris_rips_h0",
        "n": n,
        "diameter": diameter,
        "long_threshold": thr,
        "bars": bars,
        "n_bars": len(bars),
        "n_long": int(n_long),
        "n_short": len(bars) - n_long,
        "n_essential": len(roots),
        "not_acceptance": True,
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "ontology": "kb_geometry_rips_h0_not_lambda_eq_gamma",
        "disclaimer": "VR H0 informational; never ACCEPTANCE / never pin retune.",
    }


def algebraic_connectivity(
    adjacency: np.ndarray | dict[str, Any],
) -> dict[str, Any]:
    """λ1 of unnormalized graph Laplacian L = D - A (second-smallest eigenvalue).

    Calibration idea from parent sheaf_laplacian_calibration (relative trends);
    we compute on knn channel graphs only — not wormhole hypergraph YAML.
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
    if n < 2:
        return {
            "n": n,
            "lambda_1": 0.0,
            "lambda_0": 0.0,
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_lambda1_not_lambda_eq_gamma",
        }

    A = 0.5 * (A + A.T)
    np.fill_diagonal(A, 0.0)
    deg = np.sum(A, axis=1)
    L = np.diag(deg) - A
    try:
        evals = np.sort(np.real(np.linalg.eigvalsh(L)))
    except np.linalg.LinAlgError:
        return {
            "n": n,
            "lambda_1": None,
            "error": "eigvalsh_failed",
            "not_acceptance": True,
            "kb_source": KB_SOURCE,
            "transfer_note": TRANSFER_NOTE,
            "ontology": "kb_geometry_lambda1_not_lambda_eq_gamma",
        }

    # λ0 ~ 0 for connected graph; λ1 = algebraic connectivity
    lam0 = float(evals[0]) if len(evals) else 0.0
    lam1 = float(evals[1]) if len(evals) > 1 else 0.0
    return {
        "n": n,
        "lambda_0": lam0,
        "lambda_1": lam1,
        "spectrum_head": [float(x) for x in evals[: min(5, len(evals))]],
        "not_acceptance": True,
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "ontology": "kb_geometry_lambda1_not_lambda_eq_gamma",
        "disclaimer": (
            "λ1 is graph algebraic connectivity on channel knn — "
            "not dual-gate pin; not ACCEPTANCE; not λ=γ ontology."
        ),
        "threshold_note": (
            "Parent KB provisional floors were synthetic; prefer relative "
            "trend of λ1 across cycles over absolute floors."
        ),
    }
