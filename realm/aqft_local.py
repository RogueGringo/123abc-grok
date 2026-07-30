"""Discrete AQFT-inspired local net on Crit monodromies (MaxOp dual).

Continuum algebraic QFT (Haag–Kastler) assigns von Neumann algebras to
spacetime regions with isotony, locality, and covariance. Here we keep only
the *combinatorial skeleton* that fits the sheaf stack:

  base space   = cycle of Crit holonomies θ* on S¹
  local alg.   = finite observables at each sector from L(A(θ))
                 (spectral gap, frustration, log Z)
  connection   = MaxOp cellular sheaf restriction maps on C_N
  covariance   = circular shift of sector labels

This is **not** a full AQFT net. It is a diagnostic dual to projection:
does the operator algebra of preferred holonomies cohere?

Never λ=γ. ζ remains substrate seed only (realm.ontology).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.validate.dual import OperatorFingerprint


def local_observables_from_fingerprint(
    op: OperatorFingerprint,
) -> list[dict[str, float]]:
    """Per-Crit-sector local algebra generators (finite-dimensional proxy)."""
    out: list[dict[str, float]] = []
    n = int(op.thetas.size)
    for i in range(n):
        out.append(
            {
                "theta": float(op.thetas[i]),
                "spectral_gap": float(op.gaps[i]),
                "frustration": float(op.frustrations[i]),
                "logZ": float(op.logZ[i]),
            }
        )
    return out


def net_consistency(op: OperatorFingerprint) -> dict[str, Any]:
    """Isotony/locality proxies on the circular Crit net.

    - adjacent correlation of spectral gaps (circular)
    - gap CV as nonlocality / roughness of the net
    - frustration mean as monodromy strain inventory
    """
    g = np.asarray(op.gaps, float).ravel()
    f = np.asarray(op.frustrations, float).ravel()
    th = np.asarray(op.thetas, float).ravel()
    n = g.size
    if n < 2:
        return {
            "n_regions": n,
            "adjacent_gap_corr": float("nan"),
            "gap_cv": 0.0,
            "mean_frustration": float(np.mean(f)) if f.size else 0.0,
        }
    # order sectors around S¹
    order = np.argsort(th)
    g_o = g[order]
    # circular adjacent pairs
    pairs_a = g_o
    pairs_b = np.roll(g_o, -1)
    if np.std(pairs_a) < 1e-15 or np.std(pairs_b) < 1e-15:
        adj_corr = 0.0
    else:
        adj_corr = float(np.corrcoef(pairs_a, pairs_b)[0, 1])
        if not np.isfinite(adj_corr):
            adj_corr = 0.0
    mean_g = float(np.mean(g))
    return {
        "n_regions": n,
        "adjacent_gap_corr": adj_corr,
        "gap_cv": float(np.std(g) / (mean_g + 1e-15)),
        "mean_gap": mean_g,
        "mean_frustration": float(np.mean(f)),
        "mean_logZ": float(np.mean(op.logZ)),
        "isotony_proxy": "circular_adjacent_gap_correlation",
        "locality_proxy": "sector_support_disjoint_on_S1",
        "note": "discrete Crit net; continuum AQFT not claimed",
    }


def aqft_dual_report(op: OperatorFingerprint) -> dict[str, Any]:
    """Full local-net dual package for a Crit mold."""
    return {
        "framework": "discrete_haag_kastler_proxy_on_crit_cycle",
        "local_observables": local_observables_from_fingerprint(op),
        "net": net_consistency(op),
        "operator": "MaxOp_connection_laplacian_L_eq_delta_star_delta",
        "ontology": "aqft_dual_not_lambda_eq_gamma",
    }
